"""训练轻量 C-TabCVAE，并仅用验证集选择随机种子。"""

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


def parse_integer_list(value):
    values = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("列表不能为空")
    return values


def parse_args():
    parser = argparse.ArgumentParser(description="训练轻量条件表格 VAE")
    data_dir = os.path.join(PROJECT_ROOT, "data", "scenarios", "seed_v1")
    parser.add_argument("--train", default=os.path.join(data_dir, "train.jsonl"))
    parser.add_argument(
        "--validation",
        default=os.path.join(data_dir, "validation.jsonl"),
    )
    parser.add_argument("--test", default=os.path.join(data_dir, "test.jsonl"))
    parser.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_ROOT, "artifacts", "cvae", "seed_v1"),
    )
    parser.add_argument("--seeds", type=parse_integer_list, default=[11, 29, 47, 71, 97])
    parser.add_argument("--latent-dim", type=int, default=6)
    parser.add_argument("--epochs", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--beta", type=float, default=0.0001)
    parser.add_argument("--kl-warmup-epochs", type=int, default=100)
    parser.add_argument("--patience", type=int, default=50)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--keep-all-checkpoints", action="store_true")
    parser.add_argument("--save-history", action="store_true")
    parser.add_argument("--check-environment", action="store_true")
    return parser.parse_args()


def environment_status():
    torch_available = importlib.util.find_spec("torch") is not None
    print(f"[ENV] Python: {sys.version.split()[0]}")
    print(f"[ENV] NumPy: {np.__version__}")
    print(f"[ENV] PyTorch: {'available' if torch_available else 'missing'}")
    if not torch_available:
        print(
            "[ENV] 安装命令: python -m pip install -r requirements-models.txt"
        )
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


def evaluate(torch, model, loader, device, beta, cvae_loss):
    totals = {"loss": 0.0, "reconstruction": 0.0, "kl": 0.0, "samples": 0}
    model.eval()
    with torch.no_grad():
        for features, conditions in loader:
            features = features.to(device)
            conditions = conditions.to(device)
            mu, log_variance = model.encode(features, conditions)
            reconstruction = model.decode(mu, conditions)
            loss, reconstruction_loss, kl_loss = cvae_loss(
                reconstruction,
                features,
                mu,
                log_variance,
                beta,
            )
            batch_size = features.shape[0]
            totals["loss"] += float(loss.item()) * batch_size
            totals["reconstruction"] += float(reconstruction_loss.item()) * batch_size
            totals["kl"] += float(kl_loss.item()) * batch_size
            totals["samples"] += batch_size
    return {
        name: totals[name] / totals["samples"]
        for name in ("loss", "reconstruction", "kl")
    }


def train_one(
    torch,
    model_class,
    cvae_loss,
    train_dataset,
    validation_dataset,
    args,
    seed,
    device,
):
    set_seed(torch, seed)
    model = model_class(latent_dim=args.latent_dim).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.learning_rate)
    train_loader = make_loader(
        torch,
        train_dataset,
        args.batch_size,
        True,
        seed,
    )
    validation_loader = make_loader(
        torch,
        validation_dataset,
        args.batch_size,
        False,
        seed,
    )
    best_state = None
    best_validation = float("inf")
    best_epoch = 0
    stale_epochs = 0
    history = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        beta = args.beta * min(1.0, epoch / max(1, args.kl_warmup_epochs))
        for features, conditions in train_loader:
            features = features.to(device)
            conditions = conditions.to(device)
            optimizer.zero_grad(set_to_none=True)
            reconstruction, mu, log_variance = model(features, conditions)
            loss, _, _ = cvae_loss(
                reconstruction,
                features,
                mu,
                log_variance,
                beta,
            )
            loss.backward()
            optimizer.step()
        train_metrics = evaluate(
            torch,
            model,
            train_loader,
            device,
            args.beta,
            cvae_loss,
        )
        validation_metrics = evaluate(
            torch,
            model,
            validation_loader,
            device,
            args.beta,
            cvae_loss,
        )
        history.append(
            {
                "epoch": epoch,
                "beta": beta,
                "train": train_metrics,
                "validation": validation_metrics,
            }
        )
        if validation_metrics["loss"] < best_validation - 1e-7:
            best_validation = validation_metrics["loss"]
            best_epoch = epoch
            best_state = copy.deepcopy(model.state_dict())
            stale_epochs = 0
        else:
            stale_epochs += 1
        if stale_epochs >= args.patience:
            break
    model.load_state_dict(best_state)
    train_metrics = evaluate(
        torch,
        model,
        train_loader,
        device,
        args.beta,
        cvae_loss,
    )
    validation_metrics = evaluate(
        torch,
        model,
        validation_loader,
        device,
        args.beta,
        cvae_loss,
    )
    return model, {
        "seed": seed,
        "best_epoch": best_epoch,
        "epochs_ran": len(history),
        "train": train_metrics,
        "validation": validation_metrics,
        "overfit_gap": validation_metrics["reconstruction"]
        - train_metrics["reconstruction"],
        "history": history,
    }


def main():
    args = parse_args()
    torch_available = environment_status()
    if args.check_environment:
        return 0
    if not torch_available:
        raise RuntimeError(
            "PyTorch 未安装，先运行: python -m pip install -r requirements-models.txt"
        )

    import torch

    from core.scenario_features import FEATURE_NAMES, RISK_LEVELS, WEATHER_TAGS
    from models.conditional_tabular_cvae import ConditionalTabularVAE, cvae_loss
    from training.scenario_dataset import ScenarioArrayDataset

    device = choose_device(torch, args.device)
    train_dataset = ScenarioArrayDataset.from_jsonl(os.path.abspath(args.train))
    validation_dataset = ScenarioArrayDataset.from_jsonl(
        os.path.abspath(args.validation)
    )
    test_dataset = ScenarioArrayDataset.from_jsonl(os.path.abspath(args.test))
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)
    print(f"[CVAE] device={device} | train={len(train_dataset)} | validation={len(validation_dataset)}")

    runs = []
    best_run = None
    for seed in args.seeds:
        model, metrics = train_one(
            torch,
            ConditionalTabularVAE,
            cvae_loss,
            train_dataset,
            validation_dataset,
            args,
            seed,
            device,
        )
        history = metrics.pop("history")
        checkpoint_path = None
        if args.keep_all_checkpoints:
            checkpoint_path = os.path.join(output_dir, f"seed_{seed}.pt")
            torch.save(
                {
                    "format": "conditional_tabular_cvae_v1",
                    "model_config": model.config(),
                    "model_state": model.state_dict(),
                    "feature_names": list(FEATURE_NAMES),
                    "risk_levels": list(RISK_LEVELS),
                    "weather_tags": list(WEATHER_TAGS),
                    "training_seed": seed,
                    "training_metrics": metrics,
                },
                checkpoint_path,
            )
        if args.save_history:
            history_path = os.path.join(output_dir, f"seed_{seed}_history.json")
            with open(history_path, "w", encoding="utf-8") as file:
                json.dump(history, file, ensure_ascii=False, indent=2)
        run = {
            **metrics,
            "checkpoint": checkpoint_path,
        }
        runs.append(run)
        if (
            best_run is None
            or metrics["validation"]["loss"] < best_run["validation"]["loss"]
        ):
            best_run = run
            best_model = model
        print(
            f"[CVAE seed={seed}] epoch={metrics['best_epoch']} | "
            f"train={metrics['train']['loss']:.6f} | "
            f"validation={metrics['validation']['loss']:.6f} | "
            f"gap={metrics['overfit_gap']:.6f}"
        )

    test_loader = make_loader(
        torch,
        test_dataset,
        args.batch_size,
        False,
        best_run["seed"],
    )
    test_metrics = evaluate(
        torch,
        best_model,
        test_loader,
        device,
        args.beta,
        cvae_loss,
    )
    best_checkpoint = os.path.join(output_dir, "best.pt")
    torch.save(
        {
            "format": "conditional_tabular_cvae_v1",
            "model_config": best_model.config(),
            "model_state": best_model.state_dict(),
            "feature_names": list(FEATURE_NAMES),
            "risk_levels": list(RISK_LEVELS),
            "weather_tags": list(WEATHER_TAGS),
            "training_seed": best_run["seed"],
            "training_metrics": best_run,
            "test_metrics": test_metrics,
        },
        best_checkpoint,
    )
    summary = {
        "selected_by": "validation.loss",
        "selected_seed": best_run["seed"],
        "device": str(device),
        "train_records": len(train_dataset),
        "validation_records": len(validation_dataset),
        "test_records": len(test_dataset),
        "hyperparameters": {
            "latent_dim": args.latent_dim,
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "beta": args.beta,
            "kl_warmup_epochs": args.kl_warmup_epochs,
            "patience": args.patience,
        },
        "runs": runs,
        "test": test_metrics,
        "best_checkpoint": best_checkpoint,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    summary_path = os.path.join(output_dir, "training_summary.json")
    with open(summary_path, "w", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    print(
        f"[CVAE] selected_seed={best_run['seed']} | "
        f"test={test_metrics['loss']:.6f}"
    )
    print(f"[CVAE] 最佳模型: {best_checkpoint}")
    print(f"[CVAE] 训练汇总: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
