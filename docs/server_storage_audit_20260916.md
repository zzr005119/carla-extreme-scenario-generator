# 服务器存储与 `/data` 权限核验（2026-09-16）

## 结论

服务器使用 Ubuntu，不存在 Windows 的 `C:` 盘。当前项目源码、环境、CARLA 程序和实验输出均位于系统根分区下的 `/home/zhaozirong`，尚未存入 `/data`。

账号 `zhaozirong` 当前可以读取和进入 `/data`，但不能在 `/data` 创建文件；`/data/zhaozirong` 不存在，也没有发现其他属于该账号的 `/data` 子目录。因此在管理员授权前不得迁移或把项目配置改指向 `/data`。

## 实时核验

- 账号：`uid=1009(zhaozirong)`，所属组为 `zhaozirong`、`users`。
- 根分区：ext4，约 `1007 GB`，已用 `759 GB`，剩余 `197 GB`，使用率 `80%`。
- `/data`：NTFS/fuseblk，约 `2.8 TB`，已用 `927 GB`，剩余 `1.9 TB`，使用率 `34%`。
- `/data` 权限：所有者 `yurusong`，组 `factory22-dev`，模式 `775`。
- `zhaozirong` 不在 `factory22-dev` 组中。
- `/data` 访问测试：read=`yes`、execute=`yes`、write=`no`。
- 零字节临时文件写入测试：`denied`；未留下测试文件。
- `/data/zhaozirong`：不存在。
- 在 `/data` 三层目录内未发现名称包含 `zhaozirong` 或所有者为 `zhaozirong` 的目录。

## 当前项目位置与占用

`/home/zhaozirong` 总占用约 `443 GB`，其中：

| 路径 | 用途 | 占用 |
|---|---|---:|
| `/home/zhaozirong/projects/carla-extreme-scenario-generator` | 项目源码和结构化数据 | `758 MB` |
| `/home/zhaozirong/git/carla-extreme-scenario-generator.git` | 内网裸 Git 仓库 | `19 MB` |
| `/home/zhaozirong/software/carla-0.9.16` | CARLA 运行时 | `44 GB` |
| `/home/zhaozirong/software/envs/Carla666-0916` | 项目 Python 环境 | `7.1 GB` |
| `/home/zhaozirong/software/models/carla-extreme-scenario-generator` | 独立模型目录 | `6.4 MB` |
| `/home/zhaozirong/software/output/carla-0.9.16` | CARLA/RL 实验输出 | `373 GB` |
| `/home/zhaozirong/software/packages` | 安装包和同步包 | `7.8 GB` |

输出目录的主要占用为：

| 路径 | 占用 |
|---|---:|
| `carla_rl_multiscene_v1` | `290 GB` |
| `carla_rl_p3_1_v1` | `66 GB` |
| `server_batches` | `6.8 GB` |
| `collision_boundary_multisensor_v1` | `2.7 GB` |
| `feedback_candidate_validation_v1` | `1.7 GB` |
| `adversarial_baseline_carla_comparison_v1` | `1.7 GB` |

其中旧 SAC `10,000` 步目录 `carla_rl_multiscene_v1/sac_seed_20260824_10000` 单独占约 `227 GB`；P3.1 pilot 目录约 `49 GB`。本次只核验，没有删除或迁移任何数据。

## 管理员需处理

推荐由管理员创建专属目录并赋予账号权限，而不是直接开放 `/data` 根目录：

```bash
sudo mkdir -p /data/zhaozirong
sudo chown zhaozirong:zhaozirong /data/zhaozirong
sudo chmod 750 /data/zhaozirong
```

也可以由管理员采用服务器既有的组或 ACL 方案；完成后应再次执行实际写入测试。权限确认后，再制定迁移清单、校验哈希并更新 `configs/server_workflow.json`，不能直接移动正在使用的环境或输出目录。
