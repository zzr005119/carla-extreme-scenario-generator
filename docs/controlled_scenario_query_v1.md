# 受控条件检索 V1

_更新日期：2026-08-23；证据层级：E2（本机离线/HTTP 契约）；只读_

## 定位

`S5-CORE-03` 提供结构化字段和白名单关键词检索，作为场景库和 Web 管理入口的统一查询契约。它不解析自然语言意图，不把自由文本直接转换为风险、天气或 CARLA 参数，也不启动仿真。

## 共享实现

- 查询契约：`core/scenario_query.py`
- 命令入口：`tools/query_scenario_library.py`
- Web API：`GET /api/scenarios/search`
- 数据来源：场景库 `entries.jsonl`，只读
- 测试：`tests/test_scenario_query.py`、`tests/test_scenario_dashboard_http.py`

## 支持字段

| 参数 | 规则 |
|---|---|
| `generator` | 生成器精确匹配 |
| `target_risk` / `observed_risk` | 低/中/高/临界枚举精确匹配；前者是设计条件，后者是历史实测标签 |
| `collision` | `yes/no` |
| `weather_tag` / `hazard_tag` | 可重复参数；要求全部标签存在 |
| `quality_tier`、`evidence_granularity`、`verification_basis` | 枚举精确匹配 |
| `min_score`、`max_score`、`min_diversity` | 数值下限/上限 |
| `keyword` | 可重复或逗号分隔；对样本 ID、库 ID、生成器、风险/天气/危险标签、证据字段和质量层级做大小写不敏感包含匹配，多个词为 AND |
| `sort`、`limit` | `risk_desc`、`risk_asc`、`diversity_desc`、`quality_desc`、`sample_id`；`limit=0` 表示不截断 |

## 命令示例

```powershell
# 高目标、夜间、LHS，按历史实测风险降序取 5 条
D:\ANACONDA\envs\Carla666-0916\python.exe tools\query_scenario_library.py `
  --target-risk high --weather-tag night --generator lhs `
  --sort risk_desc --limit 5 --format jsonl

# 关键词和结构化条件组合
D:\ANACONDA\envs\Carla666-0916\python.exe tools\query_scenario_library.py `
  --keyword "collision" --quality-tier bronze --limit 10
```

## HTTP 示例

```text
GET /api/scenarios/search?target_risk=high&weather_tag=night&keyword=lhs&sort=risk_desc&limit=3
```

返回：

```json
{
  "count": 3,
  "library_count": 117,
  "limit": 3,
  "sort": "risk_desc",
  "filters": {"target_risk": "high", "weather_tag": "night", "keyword": "lhs"},
  "items": []
}
```

不支持的风险值、布尔值、排序方式或数值条件返回 HTTP `400`；场景库路径缺失仍按服务启动错误处理。查询结果不修改索引、不回填 `observed_risk`、不产生新的 CARLA 证据。

## 边界与下一步

- `target_risk` 是生成设计条件；`observed_risk` 才是历史 CARLA 运行测量，两者在响应中保持不同字段。
- 关键词搜索是受控字段匹配，不理解“帮我找最危险的雨夜场景”之类的自然语言句子。
- 自然语言到结构化查询对象的解析作为后续增强，必须经过枚举校验和权限/成本控制后才能接入。
