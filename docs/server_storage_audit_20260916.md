# 服务器存储清理与 `/data` 迁移记录（2026-09-16）

## 结论

服务器账号 `zhaozirong` 已加入 `factory22-dev` 组，`/data/zhaozirong` 的实际创建、读取、写入、文件锁和原子替换测试均通过。项目的模型与运行输出已迁移到 `/data/zhaozirong`，并通过逐文件 SHA-256 校验。

`/data` 是 NTFS/FUSE 挂载，`chmod` 实测返回 `Operation not permitted`。因此只迁移纯数据；CARLA、Conda 环境、ScenarioRunner、Git 工作区、裸仓库和 SSH 配置继续保留在 ext4 `/home`。把这些 Linux 可执行运行时整体迁入 `/data` 会破坏权限位和运行语义，不执行该操作。

## 权限与文件系统

- 账号：`uid=1009(zhaozirong)`，所属组为 `zhaozirong`、`users`、`factory22-dev`。
- `/data`：NTFS/FUSE，约 `2.8 TB`，迁移后已用约 `929 GB`，剩余约 `1.9 TB`，使用率 `34%`。
- `/data/zhaozirong`：实际读写通过。
- 文件锁：两个文件描述符的排他 `flock` 测试通过。
- 原子替换：临时 JSON 经 `os.replace()` 切换并读回通过。
- Unix 权限：`chmod` 失败，因此 `/data` 不承载 Linux 可执行运行时。

## 清理结果

清理前，`/home/zhaozirong/software/output` 中约有 `1,894,517` 个文件。批量 CARLA/RL 输出中的 PNG、NPY 等原始传感器帧不参与当前风险计算，相关实验也已封存，因此按以下规则清理：

1. 保留 JSON、JSONL、CSV、日志、Shell 记录、模型 checkpoint、replay buffer、sampler 状态和验收摘要。
2. 按“实验目录、传感器类型、扩展名”保留 `60` 个代表帧到 `/data/zhaozirong/evidence_samples/`。
3. 删除其余 `1,755,208` 个 PNG/NPY 等原始媒体文件，共 `393,834,055,013` 字节，失败 `0`。
4. 删除已安装完成的 `CARLA_0.9.16.tar.gz`、旧项目同步包和 pip/Conda/Mamba/NVIDIA GL 下载缓存。
5. 清理三个错误命令产生的空目录和一个零字节文件，未处理不属于本项目或用途不明确的文件。

清理清单：

```text
/data/zhaozirong/migration_manifests/cleanup_20260916_201046.json
```

该清单记录删除数量、容量、按实验分组统计，以及每个代表帧的来源、目标和 SHA-256。

## 迁移结果

| 逻辑用途 | 新物理路径 | 兼容路径 | 校验 |
|---|---|---|---|
| CARLA/RL 输出 | `/data/zhaozirong/software/output` | `/home/zhaozirong/software/output` 软链接 | `139,309` 个文件逐文件 SHA-256 一致 |
| 模型 | `/data/zhaozirong/software/models` | `/home/zhaozirong/software/models` 软链接 | `10` 个文件逐文件 SHA-256 一致 |
| 旧独立输出 | `/data/zhaozirong/outputs` | `/home/zhaozirong/outputs` 软链接 | `151` 个文件逐文件 SHA-256 一致 |

主迁移清单：

```text
/data/zhaozirong/migration_manifests/migration_20260916_201547.json
```

旧独立输出迁移清单：

```text
/data/zhaozirong/migration_manifests/alternate_outputs_20260916_202634.json
```

复制使用不保留 Unix 权限和时间戳的 NTFS 兼容模式；文件内容通过 SHA-256 校验后才切换软链接并删除 `/home` 数据副本。配置中的 `output_root`、`model_root` 和 `gpu_lock` 已改为 `/data/zhaozirong` 物理路径，旧绝对路径仍可经软链接读取历史证据。

## 迁移后验证

- 根分区由约 `81%` 使用率降至 `41%`，可用空间由约 `189 GB` 增至 `570 GB`。
- `/home/zhaozirong` 物理占用约 `62 GB`，主要是 CARLA `44 GB`、项目环境约 `7 GB`、两个 MJX 环境、RKNN 环境、VS Code Server 和源码。
- `Carla666-0916` 环境中的 CARLA Python API、Gymnasium `1.3.0`、Stable-Baselines3 `2.9.0` 和 PyTorch `2.12.1+cu126` 导入通过。
- 经旧 `/home` 路径读取迁移后的风险反馈数据集得到 `117` 行。
- 随机抽取的 SB3 checkpoint ZIP 完整性测试通过，无损坏成员。
- 经 `/home/zhaozirong/software/output` 软链接写入、读取和删除临时文件通过。
- 后台任务脚本由 `bash` 显式解释，不再对 NTFS 任务文件调用不受支持的 `chmod`；对应两项回归测试通过。
- 迁移期间及结束后均无 CARLA、RL、ScenarioRunner 或项目后台任务运行。

## 保留在 `/home` 的目录

以下目录不是遗漏，而是出于 Linux 运行兼容性保留：

- `/home/zhaozirong/software/carla-0.9.16`
- `/home/zhaozirong/software/envs`
- `/home/zhaozirong/software/scenario_runner-0.9.16`
- `/home/zhaozirong/projects`
- `/home/zhaozirong/git`
- `/home/zhaozirong/.ssh`
- `/home/zhaozirong/.vscode-server`

若管理员以后提供 ext4/XFS 等支持 Unix 权限位的数据卷，可以重新评估 CARLA 和环境迁移；在当前 NTFS/FUSE 挂载上不继续扩大迁移范围。
