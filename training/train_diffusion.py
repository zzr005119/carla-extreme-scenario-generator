"""训练轻量条件表格 Diffusion，并按验证噪声损失选择检查点。"""

import argparse
import copy
import importlib.util
import json
import os
import random
import sys
from datetime import datetime

import numpy as np


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def parse_args():
    parser = argparse.ArgumentParser(description="训练条件表格 Diffusion 对照模型")
    data_dir = os.path.join(PROJECT_ROOT, "data", "scenarios", "seed_v1")
    parser.add_argument("--train", default=os.path.join(data_dir, "train.jsonl"))
    parser.add_argument("--validation", default=os.path.join(data_dir, "validation.jsonl"))
    parser.add_argument("--test", default=os.path.join(data_dir, "test.jsonl"))
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "artifacts", "diffusion", "seed_v1"),
    )
    parser.add_argument("--seed", type=int, default=20260823)
    parser.add_argument("--timesteps", type=int, default=32)
    parser.add_argument("--hidden-dim", type=int, default=96)
    parser.add_argument("--time-dim", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=300)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--check-environment", action="store_true")
    return parser.parse_args()


def environment_status():
    torch_available = importlib.util.find_spec("torch") is not None
    print(f"[ENV] Python: {sys.version.split()[0]}")
    print(f"[ENV] NumPy: {np.__version__}")
    print(f"[ENV] PyTorch: {'available' if torch_available else 'missing'}")
    if not torch_available:
        print("[ENV] 安装命令: python -m pip install -r requirements-models.txt")
    return torch_available


def choose_device(torch, requested):
    if requested == "cpu":
        return torch.device("cpu")
    if requested == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("请求 CUDA，但当前 PyTorch 无法使用 CUDA")
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def set_seed(torch, seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def make_loader(torch, dataset, batch_size, shuffle, seed):
    tensor_dataset = torch.utils.data.TensorDataset(
        torch.from_numpy(dataset.features),
        torch.from_numpy(dataset.conditions),
    )
    generator = torch.Generator().manual_seed(seed)
    return torch.utils.data.DataLoader(
        tensor_dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        generator=generator,
    )


def evaluate(torch, model, loader, device):
    total = 0.0
    samples = 0
    model.eval()
    with torch.no_grad():
        for features, conditions in loader:
            features = features.to(device)
            conditions = conditions.to(device)
            # Fixed phases make validation comparable across epochs while covering
            # the full reverse schedule; training still uses random DDPM noise.
            timestep = (
                torch.arange(features.shape[0], device=device, dtype=torch.long)
                % model.timesteps
            )
            phase = torch.arange(
                features.numel(), device=device, dtype=features.dtype
            ).reshape(features.shape)
            noise = torch.sin(phase * 0.37)
            noisy, noise = model.q_sample(features, timestep, noise)
            prediction = model.predict_noise(noisy, conditions, timestep)
            loss = torch.nn.functional.mse_loss(prediction, noise, reduction="sum")
            total += float(loss.item())
            samples += int(features.shape[0])
    return total / max(1, samples * model.feature_dim)


def train_one(torch, model, train_dataset, validation_dataset, args, seed, device):
    set_seed(torch, seed)
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    train_loader = make_loader(torch, train_dataset, args.batch_size, True, seed)
    validation_loader = make_loader(torch, validation_dataset, args.batch_size, False, seed)
    best_state = None
    best_validation = float("inf")
    best_epoch = 0
    stale_epochs = 0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        train_total = 0.0
        train_samples = 0
        for features, conditions in train_loader:
            features = features.to(device)
            conditions = conditions.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = model.diffusion_loss(features, conditions)
            loss.backward()
            optimizer.step()
            train_total += float(loss.item()) * features.shape[0]
            train_samples += int(features.shape[0])
        validation_loss = evaluate(torch, model, validation_loader, device)
        train_loss = train_total / max(1, train_samples)
        history.append(
            {"epoch": epoch, "train_loss": train_loss, "validation_loss": validation_loss}
        )
        if validation_loss < best_validation - 1e-7:
            best_validation = validation_loss
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
        if stale_epochs >= args.patience:
            break
    if best_state is None:
        raise RuntimeError("Diffusion 训练未产生有效检查点")
    model.load_state_dict(best_state)
    return model, {
        "seed": seed,
        "best_epoch": best_epoch,
        "epochs_ran": len(history),
        "train_loss": history[best_epoch - 1]["train_loss"],
        "validation_loss": best_validation,
        "history": history,
    }


def main():
    args = parse_args()
    torch_available = environment_status()
    if args.check_environment:
        return 0
    if not torch_available:
        raise RuntimeError("PyTorch 未安装，先运行: python -m pip install -r requirements-models.txt")

    import torch

    from core.scenario_features import CONDITION_DIM, FEATURE_DIM, FEATURE_NAMES, RISK_LEVELS, WEATHER_TAGS
    from models.conditional_tabular_diffusion import ConditionalTabularDiffusion
    from training.scenario_dataset import ScenarioArrayDataset

    device = choose_device(torch, args.device)
    train_dataset = ScenarioArrayDataset.from_jsonl(os.path.abspath(args.train))
    validation_dataset = ScenarioArrayDataset.from_jsonl(os.path.abspath(args.validation))
    test_dataset = ScenarioArrayDataset.from_jsonl(os.path.abspath(args.test))
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    set_seed(torch, args.seed)
    model = ConditionalTabularDiffusion(
        feature_dim=FEATURE_DIM,
        condition_dim=CONDITION_DIM,
        timesteps=args.timesteps,
        hidden_dim=args.hidden_dim,
        time_dim=args.time_dim,
    )
    model, metrics = train_one(
        torch,
        model,
        train_dataset,
        validation_dataset,
        args,
        args.seed,
        device,
    )
    test_loader = make_loader(torch, test_dataset, args.batch_size, False, args.seed)
    test_loss = evaluate(torch, model, test_loader, device)
    checkpoint_path = os.path.join(output_dir, "best.pt")
    torch.save(
        {
            "format": "conditional_tabular_diffusion_v1",
            "model_config": model.config(),
            "model_state": model.state_dict(),
            "feature_names": list(FEATURE_NAMES),
            "risk_levels": list(RISK_LEVELS),
            "weather_tags": list(WEATHER_TAGS),
            "training_seed": args.seed,
            "training_metrics": {key: value for key, value in metrics.items() if key != "history"},
            "test_loss": test_loss,
        },
        checkpoint_path,
    )
    summary = {
        "format": "conditional_tabular_diffusion_v1",
        "selected_by": "validation_loss",
        "device": str(device),
        "train_records": len(train_dataset),
        "validation_records": len(validation_dataset),
        "test_records": len(test_dataset),
        "hyperparameters": {
            "seed": args.seed,
            "timesteps": args.timesteps,
            "hidden_dim": args.hidden_dim,
            "time_dim": args.time_dim,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "patience": args.patience,
        },
        "training": {key: value for key, value in metrics.items() if key != "history"},
        "test_loss": test_loss,
        "best_checkpoint": checkpoint_path,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    with open(os.path.join(output_dir, "training_summary.json"), "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    print(
        f"[DIFFUSION] device={device} | epoch={metrics['best_epoch']} | "
        f"validation={metrics['validation_loss']:.6f} | test={test_loss:.6f}"
    )
    print(f"[DIFFUSION] 最佳模型: {checkpoint_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
