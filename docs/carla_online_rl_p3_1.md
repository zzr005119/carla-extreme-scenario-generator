# CARLA 在线 RL P3.1：对抗搜索机制修复

## 目标与边界

P3.1 针对冻结 P3 test 上“工程四门通过，但最终候选平均风险变化为负”的问题修复搜索机制。该阶段不覆盖 P3/V1 配置、模型和证据，不把离线测试或 dev 结果写成泛化证明。

P3.1 已于 2026-09-16 封存：代码、配置、恢复契约、CARLA canary、`2,000` 步 pilot、dev 评估和独立盲测均已完成。工程链路通过，独立盲测在 `best_so_far` 选择下得到小幅正向描述性结果，但不支持总体泛化结论。封存后不继续追加训练，也不使用当前 blind split 调参；关键产物哈希见 `data/scenarios/carla_rl_p3_1_independent_blind_v1/archive_manifest_v1.json`。

## Canary 运行证据

2026-09-03，服务器作业 `carla-rl-p3-1-01-canary_20260903_135717` 在提交 `caeb92f9364858232dd5c48b14ea1b702357b9ed` 上完成，退出码为 `0`：

- SAC 准确训练到 `256/256` 步，训练状态为 `completed`；
- V2 训练质量门 `17/17` 通过，CARLA `0.9.16` 严格执行 `289/289`；
- sampler 只选择 `train` split，共选择 `33` 个不同场景；
- checkpoint 模型、replay buffer 和 sampler state 三件套均存在，连续性门通过；
- 运行根目录为 `/home/zhaozirong/software/output/carla-0.9.16/carla_rl_p3_1_v1/canary_sac_seed_20260903_256`。

该 canary 只证明新训练与恢复证据链可运行，不是策略效果或泛化证据。

## Pilot 运行证据

2026-09-03 至 2026-09-04，服务器作业 `carla-rl-p3-1-02-pilot_20260903_160538` 在提交 `f858fca94a4375d0dc792abea89615bfaf856a55` 上完成，退出码为 `0`：

- SAC 准确训练到 `2,000/2,000` 步；
- V2 训练质量门 `17/17` 通过，CARLA `0.9.16` 严格执行 `2,251/2,251`；
- sampler 只使用 `train` split，覆盖 `66` 个训练场景；
- `1,000` 和 `2,000` 两个 checkpoint 的模型、SAC replay buffer、sampler state 三件套均存在，连续性门通过；
- 运行根目录为 `/home/zhaozirong/software/output/carla-0.9.16/carla_rl_p3_1_v1/pilot_sac_seed_20260903_2000`。

训练日志的最后一条中间记录为 `total_timesteps=1,984`、`ep_rew_mean=-0.196`、`actor_loss=-67.7`、`critic_loss=0.0838`、`ent_coef=0.569`；`ep_rew_mean` 在记录区间内约为 `-0.137` 至 `-0.254`，没有稳定单调上升。对 pilot 的训练轨迹做描述性聚合（不是独立评估）得到 `250` 个完整场景 episode：每个 episode 的 `best_so_far` 候选相对 baseline 平均 `+9.920`、`204/250` 个为正，而最后一个候选平均 `-3.729`、`121/250` 个为正。这说明搜索链路能找到较高风险候选，但不能证明 SAC 策略在未见场景上稳定有效。

该 pilot 本身只证明训练和运行证据链；后续 checkpoint 选择以独立 dev 评估为准。

## Dev 评估与 checkpoint 选择

2026-09-06，服务器作业 `carla-rl-p3-1-03-evaluate-dev_20260906_105620` 在提交 `818ed65a0ab3bad226f50a30bf178d835436d235` 上完成，退出码为 `0`。两个 pilot checkpoint 均使用相同的 dev split、配置和评估种子 `20360903`，每个 checkpoint 覆盖 `27` 个 dev 场景；两个摘要的四项独立工程门均为 `27/27` 通过：baseline 严格验收、候选条件有效性、候选运行严格验收和候选证据完整性。

评估效果为：

- `1,000` 步 checkpoint：baseline 平均风险 `53.640407`，选中候选平均风险 `59.357667`，平均增量 `+5.717259`，中位数增量 `+0.528`，`22/27` 个场景上升（`81.48%`）；
- `2,000` 步 checkpoint：baseline 平均风险 `53.896741`，选中候选平均风险 `58.413963`，平均增量 `+4.517222`，中位数增量 `+0.131`，`16/27` 个场景上升（`59.26%`）。

因此 `dev_checkpoint_selection.json` 的 promotion gate 为 `passed`，按“平均增量、上升比例、候选均值、训练步数”的顺序选择了 `1,000` 步 checkpoint：

`/home/zhaozirong/software/output/carla-0.9.16/carla_rl_p3_1_v1/pilot_sac_seed_20260903_2000/models/sac_seed_20260903_steps_001000.zip`

这个 gate 只用于 P3.1 的 dev 训练决策。它证明修复后的搜索机制在保留的 dev 场景上满足当前阈值，不证明总体泛化、统计显著性或真实道路风险提升；test split 未参与选择。

## 独立盲测计划

独立盲测计划已冻结到 `data/scenarios/carla_rl_p3_1_independent_blind_v1/carla_rl_multiscene_plan_p3_1_blind_v1.json`，计划哈希为：

`28e23ff5c60464ce38e874e04ea09cb22124d52f5d9eb3f54e3239b77c0143c6`

设计口径如下：

- `3` 个生成器分层（`lhs/gmm/cvae`）× `4` 个目标风险档（`low/medium/high/critical`）× 每层 `2` 条，共 `24` 条；
- 生成种子为 `20260906`，基础 train/dev/test 划分种子保持 `20260903`；
- 场景由独立参数空间采样生成，使用新的 `canonical_sample_id` 和 `scenario_hash`，不直接复制现有 `117` 条场景；
- 与旧场景库的 ID/hash 重叠均为 `0`，与旧 train/dev/test 计划也通过全局泄漏校验；最小归一化参数距离为 `0.1006879`；
- baseline 与 RL candidate 在同一盲测场景内成对执行，使用已晋级的 `1,000` 步 SAC checkpoint，不追加训练；
- 结果只作逐场景配对的描述性结论，至少报告四项工程门、平均/中位风险增量、上升比例、分层结果、碰撞/路线失败和 best-so-far 与 last-candidate 差异。

计划生成和本地校验入口：

```cmd
python tools\prepare_carla_rl_p3_1_blind_plan.py
```

CARLA 盲测实机入口：

```cmd
.\tools\server_carla_rl_p3_1_04_evaluate_blind.cmd
```

该入口读取已通过 dev 晋级门的 `dev_checkpoint_selection.json`，不会重新训练。现有 blind split 已用于最终评估并封存，禁止再用于调参或重复筛选 checkpoint。

## 独立盲测实机结果

2026-09-06，服务器作业 `carla-rl-p3-1-04-evaluate-blind_20260906_151941` 在提交 `bd23352a8ac86e160f53ddebc0e59d9f375fdb38` 上完成，退出码为 `0`。结果摘要位于服务器：

`/home/zhaozirong/software/output/carla-0.9.16/carla_rl_p3_1_v1/blind_sac_seed_20260903_steps_001000/test_evaluation_summary.json`

回收副本位于：

`F:\Carla\project-transfer\server-results\blind_sac_seed_20260903_steps_001000_20260906_173315\test_evaluation_summary.json`

摘要 SHA-256：`B1959F5FFD742341BA69DD60CA7E15599A49AD7DF65F6C292AA246FC78B48C1F`。

结果为：

- blind split `24` 条，评估种子 `22260903`，模型为 `1,000` 步 SAC checkpoint；
- 四项工程门全部通过：baseline 严格验收 `24/24`、候选条件有效性 `24/24`、候选运行严格验收 `24/24`、候选证据完整性 `24/24`；候选 transition `104/104` 有效；
- baseline 平均风险 `42.718292`，选中候选平均风险 `43.079208`，配对平均增量 `+0.360917`，中位数 `+0.3045`；`17/24` 上升、`7/24` 下降；
- `best_so_far` 选中候选的最后候选对照增益为 `+1.314125`：最后候选平均增量为 `-0.953208`，说明本结果依赖当前选择机制，不能解读为每一步候选都有效；
- 按生成器的平均增量：`lhs +0.500375`、`gmm +0.419625`、`cvae +0.162750`；按目标风险档：`high +0.608833`、`medium +0.403167`、`low +0.214667`、`critical +0.217000`；
- baseline/candidate 碰撞总数分别为 `573/313`，所有 `24` 个 candidate 均路线、传感器和 CARLA 服务严格通过。

该结果可以支持“在一组预先冻结、未参与 checkpoint 选择的独立场景上，当前 checkpoint 的选中候选平均风险小幅上升”的描述性结论；不能单独升级为跨地图、跨生成分布或总体泛化证明。盲测场景数量有限、候选采用 `best_so_far` 选择，后续论文/结题材料应同时保留最后候选负增量和工程边界。若需要正式统计推断，应预先固定重复场景/交通种子和分层统计方案后再扩展。

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
.\tools\server_carla_rl_p3_1_04_evaluate_blind.cmd
```

执行顺序为：

1. `256` 步 canary，只验证训练、三件套 checkpoint 和严格运行质量门（已完成）；
2. canary 通过后从头运行 `2,000` 步 pilot，保存 `1,000/2,000` 两个 checkpoint（已完成）；
3. pilot 中断时只运行 resume 脚本，不重跑 canary；
4. 对两个 pilot checkpoint 使用完全相同的 dev split、种子和 P3.1 配置评估（已完成）；
5. `tools/select_carla_rl_checkpoint.py` 仅接受四门通过的 dev V2 摘要，先按平均风险增量，再按风险上升比例和候选均值选择 checkpoint（已选择 `1,000` 步 checkpoint）。
6. 使用冻结的独立 blind split 评估已选择 checkpoint（已完成并封存）。

dev 脚本可在中断后重启：已存在摘要只有在模型、配置、计划、评估种子哈希/标识和四项验收全部匹配时才复用，不会无条件重复已完成的 checkpoint 评估。

pilot 晋级门要求所选 checkpoint 在 dev 上同时满足：平均风险增量 `> 0`，且风险上升场景比例 `> 0.5`。这是是否扩大预算的工程决策门，不是统计显著性或泛化证明。未通过时脚本以非零状态结束，不启动新的 `10,000` 步训练。

## 封存状态

- 状态：`frozen`。
- 冻结 checkpoint：`1,000` 步 SAC 模型及其 replay buffer、sampler state。
- 冻结评估：dev checkpoint selection 和 `24` 条独立 blind runtime summary。
- 后续策略：不追加 P3.1 训练，不复用当前 blind split 调参；如重启 RL 研究，建立新的 P3.2 阶段和新的独立评估集。

P3.1 的封存结论是“工程链路通过，独立小样本上存在依赖 `best_so_far` 选择的小幅风险提升”。最终“总体对抗性风险提升或普遍泛化”仍未建立，不能在论文、软著或结题材料中扩大表述。
