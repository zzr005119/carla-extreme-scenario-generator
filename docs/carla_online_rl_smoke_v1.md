# CARLA 在线 RL 链路冒烟 V1

## 运行信息

- 运行日期：2026-08-23
- Git 提交：`38a8ba9`
- 服务器环境：`Carla666-0916`，Python 3.12，CARLA `0.9.16`
- GPU：GPU1；GPU0 的 vLLM 未修改；外部 TensorRT 进程保留
- 算法：Stable-Baselines3 PPO
- 训练预算：`--steps 2`，PPO rollout `n_steps=2`
- 场景：`data/scenarios/seed_v1/example_record.json`
- 远端输出：`/home/zhaozirong/software/output/carla-0.9.16/rl_online_smoke_v2`
- 轻量回收：`F:\Carla\project-transfer\server-results\rl_online_smoke_v2`

## 通过证据

训练脚本返回 `status=completed`，Gymnasium 和 SB3 均可导入，模型产物已保存。真实 CARLA 运行至少包含一条 baseline 和一条 candidate：

| 项目 | baseline | candidate |
|---|---:|---:|
| `metadata.json` | 存在 | 存在 |
| CARLA 客户端/服务端 | 0.9.16 / 0.9.16 | 0.9.16 / 0.9.16 |
| 严格验收 | 通过 | 通过 |
| RGB 帧 | 100 | 100 |
| 服务健康 | healthy | healthy |
| 路线双车在途率 | 1.0 | 1.0 |
| 碰撞事件 | 0 | 0 |
| `heuristic_v2` 风险分 | 36.449 / medium | 36.875 / medium |

CARLA 运行服务已经关闭，GPU1 当前只保留外部 TensorRT 进程。

## 结论边界

这次运行证明“Gymnasium -> SB3 PPO -> CARLA Scene 04 -> 真实遥测/严格验收 -> reward”链路可启动、可落盘、可关闭；它不是训练收敛证明，不支持 SAC/PPO 泛化、风险改善、效率提升或在线策略优越性结论。后续必须用多场景、多随机种子、独立评估集和同口径 baseline 才能形成 RL 实验结论。

## 复现入口

```bash
python tools/train_carla_rl.py \
  --config configs/adversarial_loop_multistep_v1.json \
  --record data/scenarios/seed_v1/example_record.json \
  --output-root /home/zhaozirong/software/output/carla-0.9.16/rl_online_smoke_v2 \
  --algorithm PPO --steps 2 --allow-online-carla
```

运行前必须先启动 CARLA 0.9.16、检查 GPU1 显存和端口，并确认不与外部 TensorRT 服务冲突。训练脚本不会替用户启动 CARLA。
