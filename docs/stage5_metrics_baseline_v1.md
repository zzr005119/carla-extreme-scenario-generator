# 阶段五计划书指标基线 V2

_更新日期：2026-08-24；状态：离线生成 baseline 已补齐，CARLA 时间代理已有同契约对照；计划书原始目标仍未全部实测_

## 定位

计划书阶段五提出了三个原始目标：相较实车路测测试成本降低至少 90%、相较人工规则编辑场景生成效率提升至少 11 倍、极端场景覆盖率从行业不足 15% 提升到至少 90%。计划书原文位于 `大创计划书提交版.pdf` 第 12 页；工程内的阶段计划位于 `项目分阶段实施计划.md` 第 5.2 节。

本版补齐的是可复现的工程侧 baseline，不把离线采样或 CARLA 墙钟时间冒充实车路测、人工操作计时或行业统计。每个相对值都由脚本从原始汇总计算，契约不一致时会返回 `not_assessed`。

入口：`tools/measure_stage5_metrics.py`

本轮固定结果可直接由仓库根目录执行 `tools\run_stage5_metrics_baseline.cmd` 重建；该入口只运行 CPU 离线生成和读取已有 CARLA 元数据，不启动 CARLA 或训练任务。

## 三项测量口径

| 指标 | 当前可测定义 | 当前边界 |
|---|---|---|
| 生成效率 | 同一 Python 进程、同一 CPU、同一 15 维范围、同一风险档配额、同一 Schema 构建/校验契约下，`sum(accepted_count) / sum(elapsed_seconds)` | baseline 是 `uniform_rule_parameter_sampling_v1` 规则参数采样代理，不是人工键盘操作计时；不等于计划书的人工规则编辑效率 |
| 测试成本代理 | 每条严格验收 CARLA 运行的 `result.wall_duration_seconds`，报告总量、均值和中位数 | 是执行时间代理，不是金钱成本；严格验收必须满足传感器、服务、清理、版本和路线门 |
| 条件覆盖代理 | 候选记录覆盖显式参考集的唯一条件签名比例；签名为 `target_risk_level + sorted weather_tags + sorted hazard_tags` | 不是真实道路覆盖率；参考集必须由调用者明确提供 |

## 当前快照

可由以下命令重建（原始产物默认放在 `F:\Carla`，不纳入 Git）：

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe tools\benchmark_stage5_generation_baseline.py `
  --output-dir F:\Carla\project-transfer\stage5_metrics_p1_20260824\generation `
  --count-per-level 512 --repeats 5 --seed 20260824
```

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe tools\measure_stage5_metrics.py `
  --generation-summary F:\Carla\project-transfer\stage5_metrics_p1_20260824\generation\system_lhs_summary.json `
  --baseline-generation-summary F:\Carla\project-transfer\stage5_metrics_p1_20260824\generation\baseline_uniform_rule_summary.json `
  --metadata <同契约的系统侧 metadata.json> `
  --baseline-metadata <同契约的 baseline 侧 metadata.json> `
  --reference data\scenarios\seed_v1\scenarios.jsonl `
  --candidate F:\Carla\project-transfer\stage5_metrics_p1_20260824\generation\system_lhs.jsonl `
  --baseline-candidate F:\Carla\project-transfer\stage5_metrics_p1_20260824\generation\baseline_fixed_template.jsonl `
  --output F:\Carla\project-transfer\stage5_metrics_p1_20260824\metrics_report_full.json
```

本轮报告：`F:\Carla\project-transfer\stage5_metrics_p1_20260824\metrics_report_full.json`；生成 benchmark 的原始记录、汇总和契约位于同目录 `generation`。

| 项目 | 系统侧 | baseline 侧 | 结果与边界 |
|---|---:|---:|---|
| 生成记录 | `10240` 条（输出保留最后 `2048` 条） | `10240` 条（输出保留最后 `2048` 条） | 五次重复、四档各 `512` 条；同一 CPU/15 维/Schema 契约 |
| 生成吞吐 | `3612.599633 条/s` | `3761.787593 条/s` | 系统 / baseline = `0.960341x`（本轮五次重复总 accepted / 总 elapsed）；baseline 不是人工计时，远未达到计划书 11 倍 |
| CARLA 运行时间代理 | `12.9075 s/严格验收运行` | `13.622 s/严格验收运行` | 系统 / baseline = `0.947548`，时间下降 `5.2452%`；来自 0.9.16 同契约 Gymnasium 冒烟，不是实车路测成本 |
| 参考条件签名 | `21` 个 | `21` 个 | 同一 `seed_v1/scenarios.jsonl` 参考全集 |
| 条件覆盖代理 | `21/21 = 100%` | `1/21 = 4.761905%` | baseline 是单一固定规则模板，仅用于覆盖代理；不等于行业当前覆盖率 |

历史快照仍保留在上一版报告和 `F:\Carla\output-0.9.16\migration_v1`，但不再与本轮 baseline 混算。

## Baseline 与目标状态

本轮已传入三类 baseline。离线生成比较已测得系统吞吐低于 `uniform_rule` 代理，不能宣称“11 倍”；CARLA 时间代理仅下降约 `5.25%`，不能宣称“成本降低 90%”。覆盖代理从固定模板的 `4.76%` 到系统侧 `100%`，但参考全集是项目种子条件签名，不能宣称“行业覆盖率达到 90%”。

计划书原始目标的状态：

| 计划书原始目标 | 当前状态 |
|---|---|
| 相较实车路测测试成本降低 ≥90% | `not_assessed`：没有实车路测同口径成本数据；CARLA 墙钟只作执行时间代理 |
| 相较人工规则编辑生成效率提升 ≥11 倍 | `not_met_on_rule_proxy`：当前 LHS 为 `0.960341x` 的同 CPU 规则采样代理；没有人工操作计时 |
| 行业不足 15% → 极端场景覆盖率 ≥90% | `not_assessed`：当前仅有 21 个项目条件签名全集；不能把它当行业分母 |

后续若要把任一原始目标升级为“达成”，必须新增计划书目标对应的真实分母：实车路测成本账单/计时、人工规则编辑的人员操作计时、行业覆盖率定义和数据来源；不能用本工程代理替代。公开资料锚点和区间预估见 `docs/stage5_external_cost_and_coverage_estimate_v1.md`。

## 验证

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe -m unittest tests.test_stage5_metrics
```

当前测试覆盖吞吐计算、契约不一致拒绝、严格验收时间代理和显式条件签名覆盖；benchmark 只使用 CPU，不启动 CARLA，不占用 GPU。CARLA 时间代理复用已存在的服务器严格验收元数据，没有在本轮启动训练或新增在线 CARLA 任务。
