# 阶段五计划书指标基线 V1

_更新日期：2026-08-23；状态：测量脚本已完成，宣传目标暂未验证_

## 定位

计划书阶段五提出了“测试成本降低、场景生成效率提升、极端场景覆盖率提升”等目标。当前工程没有同一命令、同一硬件、同一场景规模下的人工/随机 baseline，因此本轮只建立可复现的测量口径和当前系统快照，不把快照数字写成目标达成结果。

入口：`tools/measure_stage5_metrics.py`

## 三项测量口径

| 指标 | 当前可测定义 | 当前边界 |
|---|---|---|
| 生成效率 | `sum(accepted_count) / sum(elapsed_seconds)`，单位为条/s；同时报告接受率 | 只反映记录生成进程的墙钟吞吐，不等于完整 CARLA 测试效率，不跨硬件比较 |
| 测试成本代理 | 每条严格验收 CARLA 运行的 `result.wall_duration_seconds`，报告总量、均值和中位数 | 是执行时间代理，不是金钱成本；严格验收必须满足传感器、服务、清理、版本和路线门 |
| 条件覆盖代理 | 候选记录覆盖显式参考集的唯一条件签名比例；签名为 `target_risk_level + sorted weather_tags + sorted hazard_tags` | 不是真实道路覆盖率；参考集必须由调用者明确提供 |

## 当前快照

可由以下命令重建（`artifacts/` 被 Git 忽略）：

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe tools\measure_stage5_metrics.py `
  --generation-summary artifacts\final_evaluation `
  --metadata F:\Carla\output-0.9.16\migration_v1 `
  --reference data\scenarios\seed_v1\scenarios.jsonl `
  --candidate data\scenarios\scenario_library_v1\entries.jsonl `
  --output artifacts\stage5_metrics_baseline_v1\metrics_report.json
```

当前报告：`artifacts/stage5_metrics_baseline_v1/metrics_report.json`。

| 项目 | 当前值 | 证据边界 |
|---|---:|---|
| 生成记录 | `1536` 条 / `7.192140 s` | 12 个历史离线生成汇总，E2；不是 Web 任务或 CARLA 端到端吞吐 |
| 生成吞吐 | `213.566477 条/s` | 同上；接受率 `0.687556` |
| 历史严格验收运行 | `3/3` | CARLA 0.9.16 迁移回归目录，E4 历史证据 |
| 运行时间代理 | 均值 `8.781667 s`，中位数 `9.688 s` | `wall_duration_seconds`；不是经济成本 |
| 参考条件签名 | `21` 个 | 来自 `seed_v1/scenarios.jsonl` |
| 库覆盖条件签名 | `8/21`，`38.095238%` | 仅表示场景库 V1 对该参考签名集合的覆盖代理 |

## Baseline 与目标状态

本次没有传入 `--baseline-generation-summary`、`--baseline-metadata` 或 `--baseline-candidate`，所以报告中的三项相对比较均为 `not_assessed`。计划书中的 90%、11 倍和 90% 不能由当前快照推出，也不能用不同硬件、不同场景规模或不同验收条件拼接计算。

待补充 baseline 时，必须至少固定：同一 Python 入口、同一场景记录数、同一 CPU/GPU 资源说明、同一 CARLA 版本、同一传感器/路线质量门和同一条件签名参考集。补齐后再由脚本计算相对比值和变化，不手填宣传数字。

## 验证

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe -m unittest tests.test_stage5_metrics
```

当前测试覆盖吞吐计算、严格验收时间代理和显式条件签名覆盖；不启动 CARLA，不占用 GPU。
