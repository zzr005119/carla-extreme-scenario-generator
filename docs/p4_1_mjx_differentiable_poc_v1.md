# P4.1 MJX-JAX 可微刚体 PoC V1

## 目的

P4 当前边界已经证明了 Torch 可微运动学代理、PyBullet 离散接触校验和参数级硬约束可以协同工作。P4.1 进一步验证一个真正的可微刚体后端是否值得接入生成模型训练。主证据采用服务器 Linux CPU 小场景 PoC，并用独立 GPU1 环境做同参数受控复核；两类运行都不启动 CARLA、不启动 SAC。Windows 侧仅保留可选测试入口，不作为正式实验环境。

## 本轮实现

`core/mjx_differentiable_poc.py` 使用 MuJoCo/MJX 建立一个最小一维刚体场景：主车是带滑动关节的刚体，前车是静态刚体，动作是主车执行器力。每个时间步由 MJX 进行刚体动力学和接触求解，输出位置、速度、间距和安全间距软损失。MJX 的 `iterations` 参数可以控制约束求解迭代次数。

正式运行入口（服务器 Linux CPU）：

```bash
tools/run_mjx_differentiable_poc_linux.sh --horizon 16 --force 2.0
```

Windows 的 `tools\run_mjx_differentiable_poc.cmd` 仅用于可选本地开发测试，不作为正式证据来源。

CPU 正式复现使用 Linux 服务器个人环境 `/home/zhaozirong/software/envs/MJXPoC-Linux`，入口显式设置 `JAX_PLATFORMS=cpu` 并清空 `CUDA_VISIBLE_DEVICES`。GPU1 研究入口使用独立环境 `/home/zhaozirong/software/envs/MJXPoC-Linux-GPU1` 和 `tools/run_mjx_differentiable_poc_gpu1.sh`，只暴露物理 GPU1 并将 JAX 显存比例默认限制为 `0.10`；两类证据分开记录。

## 质量门

本轮只检查四件事：

1. MJX 刚体前向 rollout 能运行；
2. JAX 前向模式 `jax.jacfwd` 能得到有限梯度；
3. 该梯度与中心有限差分的相对误差小于 `1e-2`；
4. 同一 MJCF 在原生 MuJoCo CPU 步进和 MJX 轨迹之间的最大位置/间距误差小于 `1e-5 m`。

当前 manifest：`artifacts/p4_1_mjx_differentiable_poc_v1/manifest.json`。

## 当前结果

- `quality_gate=pass_forward_mode_only`；
- 设备为 `cpu:0`；
- 前向梯度有限；
- 高动作输入仍先裁剪到执行器约束区间；梯度探针会将有限差分坐标放在 `±0.8*force_limit` 内，避免边界裁剪造成单边扰动；
- MJX 与原生 MuJoCo 轨迹对齐；
- 当前接触求解器的 `jax.grad` 反向模式触发 JAX 动态 `while_loop` 限制，因此 `reverse_mode_available=false`。

## 绕过限制的对照结果

源码显示：当 `iterations > 1` 时，MJX 约束求解器进入动态 `jax.lax.while_loop`；当 `iterations=1` 时直接执行一次固定求解步骤，不进入该反向模式不支持的动态循环。因此当前有三条路线：

| 路线 | 反向梯度 | 物理求解 | 适用范围 |
|---|---|---|---|
| `jax.jacfwd` | 可用 | 保持正常迭代 | 小参数量 PoC；输入维度越高成本越大 |
| `iterations=1` + `jax.grad` | 可用 | 只做一次约束迭代 | 需要额外验证接触精度，不能直接视为高保真训练 |
| `iterations>1` + `jax.grad` | 当前不可用 | 正常迭代 | 需要自定义反向/隐式微分，暂不作为现成能力 |

对照入口：

```bash
tools/run_mjx_differentiable_poc_linux.sh --horizon 32 --force 4 --compare-workarounds
```

## 自定义 VJP

已经实现 `MJXDifferentiableBackend.loss_with_custom_vjp()`。它保留正常多次迭代 MJX 作为前向函数，在反向规则中使用 `jax.jacfwd` 计算该前向函数的局部 Jacobian，再与上游 cotangent 做收缩。该方法绕开的是 JAX 的反向模式限制，不是伪造梯度；代价是反向计算复杂度随动作维度线性增加。

验证入口（服务器 Linux CPU）：

```bash
tools/run_mjx_differentiable_poc_linux.sh --horizon 32 --force 4 --probe-custom-vjp
```

因此自定义 VJP 可以作为小规模训练或梯度校验方案，但还不能直接用于高维长时序训练。使用前必须测量批量性能、显存/内存和多刚体接触下的梯度稳定性。

服务器 Linux CPU 复现已通过：MJX/JAX 运行在 `cpu:0`，正常 `iterations=4` 的自定义 VJP 与 `jacfwd` 最大绝对差为 `0`。GPU1 受控复现也已通过：进程内设备为 `cuda:0`（物理 GPU1），自定义 VJP 与 `jacfwd` 最大绝对差为 `0`，有限差分相对误差为 `1.42e-10`，JAX 额外显存约 `704 MiB`。CPU 证据文件为服务器 `/home/zhaozirong/outputs/mjx_poc_linux_v1/manifest_server_cpu_custom_vjp.json`，GPU1 证据文件为 `/home/zhaozirong/outputs/mjx_poc_linux_v1/manifest_server_gpu1_custom_vjp_v2.json`；本地回收副本位于 `artifacts/p4_1_mjx_differentiable_poc_v1/`。正式复跑使用内部动作点，不把裁剪边界误差作为梯度证据。

固定一次迭代是“绕过 JAX 限制”的工程试验，不是默认切换。只有在高接触、摩擦和多刚体样例上与正常迭代误差仍满足质量门时，才可以作为可微训练代理；否则继续采用 `jacfwd` 小规模研究或回退当前 Torch + PyBullet 边界。

## GPU1 并发边界

GPU1 当前存在 CARLA/SAC 工作负载，因此 GPU1 入口不允许 JAX 预分配全部显存，只能使用显式上限运行短时冒烟或受控批量测试。`CUDA_VISIBLE_DEVICES=1` 后，JAX 进程内显示为 `CudaDevice(id=0)`，这仍对应物理 GPU1。若显存或利用率出现持续增长，应停止 MJX 任务，不终止其他进程。

GPU1 受控压力入口：

```bash
tools/run_mjx_differentiable_poc_gpu1.sh --horizon 128 --force 5 --compare-workarounds --probe-custom-vjp
```

服务器并发压力结果：CPU/GPU 同口径的损失绝对差为 `2.63e-13`，梯度绝对差为 `9.06e-14`；GPU1 进程额外显存约 `704 MiB`，任务结束后显存回落。该结果支持“可以小规模受控并发”，不支持把 GPU1 当作无上限共享资源。

## CPU/GPU 批量性能基准

基准入口分别为 `tools/run_mjx_performance_benchmark_cpu.sh` 和 `tools/run_mjx_performance_benchmark_gpu1.sh`，统一使用 `horizon=128`、批量 `1/4/16`、3 次稳态重复，并把首次 JAX 编译时间单独记录。结果如下：

| batch | CPU 前向/s | GPU1 前向/s | GPU1/CPU | CPU 自定义 VJP/s | GPU1 自定义 VJP/s | GPU1/CPU |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 53.824 | 13.630 | 0.25x | 5.279 | 8.716 | 1.65x |
| 4 | 104.978 | 69.466 | 0.66x | 6.386 | 27.103 | 4.24x |
| 16 | 372.029 | 241.449 | 0.65x | 10.303 | 109.800 | 10.66x |

结论：当前一维小场景的前向计算受 JAX/MJX 调度开销影响，GPU1 前向吞吐没有超过服务器 CPU；自定义 VJP 梯度在 batch `4/16` 上明显受益于 GPU。GPU1 适合受控批量梯度实验，不应因为利用率有余量就把所有前向任务迁移到 GPU。首次编译约 CPU `4.0–4.7 s`、GPU1 `7.1–7.8 s`，短任务不适合频繁创建新进程。

扩大规模基准（`horizon=256`、batch `32/64`、稳态重复 2 次）结果：

| batch | CPU 前向/s | GPU1 前向/s | GPU1/CPU | CPU 自定义 VJP/s | GPU1 自定义 VJP/s | GPU1/CPU |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 194.245 | 248.722 | 1.28x | 4.762 | 105.833 | 22.22x |
| 64 | 454.756 | 450.410 | 0.99x | 5.587 | 152.138 | 27.23x |

该结果支持将 GPU1 用于批量自定义 VJP 研究；前向任务仍按 batch 和场景规模选择 CPU/GPU，不能仅依据 GPU 利用率调度。两份证据为 `artifacts/p4_1_mjx_differentiable_poc_v1/manifest_server_cpu_performance_h256_b32_b64_v1.json` 和 `manifest_server_gpu1_performance_h256_b32_b64_v1.json`。

## 双动态刚体接触压力测试

新增独立入口 `tools/run_mjx_multibody_probe.py`，场景包含两个带滑动关节的动态刚体，ego 使用恒定力追近 lead。服务器 CPU 与 GPU1 均完成 `horizon=128, force=5` 测试。该首轮结果使用了错误的间距统计口径，已标记为历史诊断，不作为正式物理结论；正式口径使用 `surface_gap_m = initial_gap + lead_qpos - ego_qpos`，不重复扣除刚体半长。

- CPU 最小间距 `-6.104719 m`，GPU1 最小间距 `-6.104719 m`；
- CPU/GPU 损失绝对差 `4.97e-14`，梯度绝对差 `2.31e-16`；
- CPU 有限差分相对误差 `4.84e-8`，GPU1 为 `1.81e-7`；
- 两种设备与原生 MuJoCo 的最大位置误差均小于 `1e-12 m`；
- `iterations=4` 仍触发动态 `while_loop` 反向限制，`iterations=1` 可恢复反向模式。

这组首轮结果只保留为口径错误的诊断记录，不用于判断物理真实性。间距公式已增加单元回归，正式结论以修正后的稳定性筛选为准。

## 接触稳定性筛选

使用 8 组平衡筛选设计，平衡扫描 `force={0.05, 0.20}`、`timestep={0.005, 0.020}`、`initial_gap={4, 6}` 和 `solver_iterations={1, 4}`。稳定性门为：最大穿透不超过 `0.05 m`、前向梯度有限、有限差分相对误差小于 `1e-2`、MJX 与原生 MuJoCo 轨迹误差小于 `1e-5 m`。

- CPU：`8/8` 通过，最小真实间距为 `3.393202 m`；
- GPU1：`8/8` 通过，最小真实间距为 `3.393202 m`；
- CPU/GPU 各组最小间距最大差为 `8.88e-16 m`，有限差分最大误差分别为 `4.28e-10` 和 `6.61e-10`；
- 代表性稳定候选（`force=0.05, timestep=0.02, initial_gap=4, iterations=4`）的 CPU/GPU 自定义 VJP 与 `jacfwd` 最大差均为 `0`，CPU/GPU 梯度差为 `6.78e-21`，有限差分误差为 `2.22e-11`/`1.32e-12`。

这证明在当前受控低力、较大间距的小场景内，可以同时满足接触稳定性、数值一致性和自定义 VJP 校验；仍不等价于车辆动力学真实性，也不构成 CVAE/Diffusion 训练已经可接入。

## 独立相向运动接触边界

为避免重复低力 ego-only 动作对，新增 `tools/scan_mjx_multibody_contact_boundary.py`，让 ego 施加正向力、lead 施加等量反向力，在 `horizon=128`、`timestep=0.02`、`initial_gap=4 m`、`iterations=4` 下扫描 6 组相对闭合力。数值门仍要求梯度有限、有限差分相对误差小于 `1e-2` 且与原生 MuJoCo 轨迹误差小于 `1e-5 m`；接触门要求发生接触且最大穿透不超过 `0.05 m`。

- 服务器 CPU：`6/6` 组数值门通过，`4` 组发生接触，其中 `3` 组接触门通过，接触门通过率 `75%`；
- `ego=3.0, lead=-3.0` 的相向场景最大穿透为 `0.080471 m`，分类为 `contact_penetration_unstable`；
- 其余 `2` 组未接触，分类为 `no_contact_stable`；
- CPU manifest：`artifacts/p4_1_mjx_differentiable_poc_v1/server_cpu_contact_boundary_v1/manifest.json`；
- 服务器 GPU1：同一 `6` 组参数复核完成，JAX 设备显示 `cuda:0`（由 `CUDA_VISIBLE_DEVICES=1` 映射到物理 GPU1），`6/6` 组数值门通过，`4` 组发生接触，其中 `3` 组接触门通过；最大穿透为 `0.080471 m`。
- CPU/GPU1 对比：最大最小间距绝对差 `9.77e-15 m`，最大损失绝对差 `7.02e-14`，最大解析梯度绝对差 `7.65e-14`，6 组分类完全一致；GPU1 与原生 MuJoCo 最大位置误差 `9.55e-14 m`、间距误差 `1.91e-13 m`。
- GPU1 任务 `mjx-contact-boundary-gpu1-v1_20260831_121712` 正常退出并释放项目锁，结束后显存回落至 `916 MiB`；GPU0 显存占用保持 `44052 MiB`，未修改 vLLM 或其他服务。
- CPU manifest：`artifacts/p4_1_mjx_differentiable_poc_v1/server_cpu_contact_boundary_v1/manifest.json`；GPU1 manifest：`artifacts/p4_1_mjx_differentiable_poc_v1/server_gpu1_contact_boundary_v1/manifest.json`；汇总对比：`artifacts/p4_1_mjx_differentiable_poc_v1/manifest_server_cpu_gpu1_contact_boundary_comparison_v1.json`。

因此，本轮证明 CPU/GPU1 在相向运动下的数值路径可复现，并定位了共同的接触穿透边界；整体 `contact_realism_gate_passed=false`，不把局部通过样本写成物理真实性通过。GPU1 复核已完成，但不能据此宣称车辆动力学真实性或训练闭环完成。

## 结论与边界

这证明 MJX-JAX 可以作为后续可微刚体研究后端，并且 CPU/GPU1 前向梯度在最小场景中数值可信；相向运动扫描同时表明接触真实性仍有明确失败区间。当前没有形成可扩展的生成模型训练闭环，不能写成“MJX 已接入 CVAE/Diffusion/RL”或“CARLA 车辆动力学已经可微”。下一步应评估接触稳定性改进与批量反向成本；在此之前继续保留 P4 现有 Torch + PyBullet 边界。

## 复现

可选测试默认跳过，避免全量回归被 JAX 首次编译拖慢。显式运行：

```powershell
$env:RUN_MJX_POC_TESTS = '1'
D:\ANACONDA\envs\Carla666-0916\python.exe -m unittest tests.test_mjx_differentiable_poc -v
```
