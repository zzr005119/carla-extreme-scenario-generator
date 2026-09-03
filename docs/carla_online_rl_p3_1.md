# CARLA 在线 RL P3.1：对抗搜索机制修复

## 目标与边界

P3.1 针对冻结 P3 test 上“工程四门通过，但最终候选平均风险变化为负”的问题修复搜索机制。该阶段不覆盖 P3/V1 配置、模型和证据，不把离线测试或 dev 结果写成泛化证明。

当前仓库完成的是代码、配置、恢复契约和 CPU 静态回归。尚未运行 P3.1 的 CARLA canary、pilot 或 dev 评估，因此不能宣称策略效果已经改善。

## 独立配置

- 循环配置：`configs/adversarial_loop_multistep_p3_1.json`
- 代理配置：`configs/adversarial_agent_p3_1.json`
- 输出根目录：`carla_rl_p3_1_v1`，不得写入 `carla_rl_multiscene_v1`
- 默认种子：`20260903`
- 动作步长：`0.04`，V1 保持 `0.08`
- 单场景最大动作数：`8`，V1 保持 `16`
- 评估候选：`best_so_far`，V1 默认仍为 `last_successful`

奖励只使用相对 `heuristic_v2` 风险增量作为正向目标。碰撞和事件额外奖励归零，避免和 `heuristic_v2` 重复计权；另加入动作 RMS L2 惩罚和参数边界饱和惩罚。

## 评估证据 V2

`tools/evaluate_carla_rl_multiscene.py` 为每个场景保留：

- baseline、每一步 transition、最后严格候选、最佳严格候选和最终选中候选；
- 动作、reward 分解、风险分、碰撞/事件计数、边界饱和率和运行目录；
- 目标分早停、连续无实质改善早停及其原因；
- 四项独立工程验收和按生成器/目标风险档分组的描述性效果统计。

候选只有同时满足真实运行、严格验收、CARLA 健康且风险方法为 `heuristic_v2` 才能参与最佳候选选择。V2 摘要包含模型、配置和场景计划哈希。

## 可恢复 checkpoint

每个 P3.1 checkpoint 是不可拆分的三件套：

1. SB3 模型 `.zip`；
2. SAC replay buffer `.pkl`；
3. 场景 sampler 的 RNG、排列、游标和选择计数 `.json`。

`checkpoint_manifest.json` 使用 `carla_online_rl_checkpoint_manifest_v2`。恢复入口默认拒绝 V1 manifest、缺少任一必需产物、哈希计划不一致或模型步数不一致的 checkpoint。SAC replay buffer 容量按训练预算受控，最小 `10,000`、最大 `100,000`，不再使用 SB3 的百万级默认值。

该机制恢复 replay 和下一次场景采样位置，但不声称恢复中断瞬间的 CARLA 世界状态；重启后从下一次环境 reset 继续。

## 分阶段运行

所有命令从项目根目录执行。脚本会启动/复用项目 CARLA 服务，但不会停止 GPU0 的 vLLM 或 GPU1 的外部 TensorRT 服务。

```powershell
.\tools\server_carla_rl_p3_1_01_canary.cmd
.\tools\server_carla_rl_p3_1_02_pilot.cmd
.\tools\server_carla_rl_p3_1_02_resume_pilot.cmd
.\tools\server_carla_rl_p3_1_03_evaluate_dev.cmd
```

执行顺序为：

1. `256` 步 canary，只验证训练、三件套 checkpoint 和严格运行质量门；
2. canary 通过后从头运行 `2,000` 步 pilot，保存 `1,000/2,000` 两个 checkpoint；
3. pilot 中断时只运行 resume 脚本，不重跑 canary；
4. 对两个 pilot checkpoint 使用完全相同的 dev split、种子和 P3.1 配置评估；
5. `tools/select_carla_rl_checkpoint.py` 仅接受四门通过的 dev V2 摘要，先按平均风险增量，再按风险上升比例和候选均值选择 checkpoint。

dev 脚本可在中断后重启：已存在摘要只有在模型、配置、计划、评估种子哈希/标识和四项验收全部匹配时才复用，不会无条件重复已完成的 checkpoint 评估。

pilot 晋级门要求所选 checkpoint 在 dev 上同时满足：平均风险增量 `> 0`，且风险上升场景比例 `> 0.5`。这是是否扩大预算的工程决策门，不是统计显著性或泛化证明。未通过时脚本以非零状态结束，不启动新的 `10,000` 步训练。

## 后续判定

- canary 失败：先修工程链路，不进入 pilot。
- pilot 训练门失败：只从最新完整三件套恢复。
- dev 工程门失败：先修证据或运行质量，不进行效果解释。
- dev 晋级门失败：停止扩大 SAC 预算，优先比较非学习搜索或调整状态/动作设计。
- dev 晋级门通过：再单独设计训练预算和新的盲测集；既有 P3 test 已用于诊断，不重复作为 P3.1 最终证明集。

最终“总体对抗性风险提升或普遍泛化”至少需要未参与训练、调参和问题诊断的新盲测场景，并报告逐场景配对结果、均值/中位数、上升比例和不确定性。当前 P3.1 不满足这一证明条件。
