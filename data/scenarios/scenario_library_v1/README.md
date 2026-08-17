# 极端场景库 V1

## 当前内容

- 独立场景：`117` 个；内容哈希已去重。
- 严格验收运行证据：`351` 次。
- 生成器分布：`{"cvae": 39, "gmm": 39, "lhs": 39}`。
- 目标风险分布：`{"critical": 60, "high": 39, "low": 9, "medium": 9}`。
- 实测高风险及以上：`72` 个；碰撞场景：`39` 个。

## 文件

- `entries.jsonl`：完整场景库条目，符合 `schemas/scenario_library_entry.schema.json`。
- `index.csv`：面向筛选和后续检索的扁平索引。
- `summary.json`：数量、风险、质量和证据范围汇总。
- `manifest.json`：输入、Schema 与输出文件哈希。

## 查询示例

```cmd
python tools\query_scenario_library.py --collision yes --sort risk_desc --limit 10
python tools\query_scenario_library.py --generator cvae --target-risk critical --min-score 70
python tools\query_scenario_library.py --evidence-granularity run_level --quality-tier silver
```

## 质量边界

- 可执行性、证据完整性和重复性来自 CARLA 运行与严格验收记录。
- 危险性来自 `heuristic_v2` 实测风险均值，不等同于真实道路事故概率。
- 多样性仅表示当前库内 15 维归一化参数空间的最近邻距离，会随场景库扩展而变化。
- 真实性尚未评估，因为当前没有同口径真实世界参数分布；条目保持 `partial`，不得表述为真实性验证通过。
- `run_level` 条目保留逐次运行、配置与历史元数据路径；`aggregate` 条目只保留 V5 场景级聚合结果和来源文件哈希，不能反向伪造逐次运行路径。
- 当前聚合数据和首批历史运行结果均未在场景级表中记录 CARLA 客户端/服务端版本，因此证据完整性不会被评为满分；这不改变来源批次通过严格验收的事实。
- 当前库是风险反馈驱动的压力测试库，高/临界目标占比较高，不代表真实交通场景自然分布。
