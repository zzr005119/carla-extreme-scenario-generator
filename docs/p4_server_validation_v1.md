# P4 服务器验证记录 V1

_验证日期：2026-08-24；服务器：`factory22-srv`；项目提交：`bf84fa76db53268699a8948fc2fa6b9a2cd8fb87`_

## 验证范围

本轮只验证 P4 的 Torch 代理和 PyBullet 离散适配器，不启动 CARLA、不启动在线 RL、不申请 GPU 训练资源。服务器运行环境为 `Carla666-0916`，PyTorch `2.12.1+cu126`，PyBullet `3.2.7`。

运行入口：

```bash
/home/zhaozirong/software/micromamba-bin/micromamba run \
  -p /home/zhaozirong/software/envs/Carla666-0916 \
  python tools/run_differentiable_closed_loop.py \
  --horizon 128 --profile closing \
  --output artifacts/p4_differentiable_boundary_v1/manifest_server_contact_probe_v2.json
```

## 结果

| 检查项 | 结果 |
|---|---:|
| `quality_gate` | `pass` |
| Torch `gradient_check.finite` | `true` |
| Torch 最小间距 | `-67.3601455688477 m` |
| PyBullet `available` / `validated` | `true` / `true` |
| 负间距步数 | `63` |
| 离散接触点数 | `41` |
| 接触步 | `65–75` |
| `pybullet_native_differentiable` | `false` |
| CARLA 是否连接 | `false` |

短 horizon 的 `closing` 和 `alternating` profile 也分别通过了 PyBullet DIRECT 初始化、轨迹回放和 manifest 生成；由于没有负间距，接触点数为 `0`，这与输入轨迹一致。

## 资源边界

运行前 `nvidia-smi`：GPU0 约 `44066 MiB`，GPU1 约 `7160 MiB`、利用率 `58%`。本轮只运行 CPU/离线 Torch 和 PyBullet DIRECT，不终止或干扰 GPU1 上的外部进程。

## 证据文件

服务器原始 manifest 未进入 Git，已回收到：

`F:\Carla\project-transfer\server-results\p4_differentiable_boundary_v1\manifest_server_contact_probe_v2.json`

SHA-256：`7073DE9D7D81DA4F08B05B8DB1081650FA592994D05A44D27A3E0BB3EE05C852`

该结果只证明“可微运动学代理 + PyBullet 离散几何/接触回放 + 独立硬约束质量门”的接口可运行；不证明 PyBullet 可微刚体训练、CARLA 车辆动力学或生成模型/RL 训练接入。
