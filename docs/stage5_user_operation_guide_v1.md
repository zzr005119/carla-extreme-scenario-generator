# 阶段五用户操作说明底稿 V1

_用途：软著说明书和项目演示的操作底稿；当前版本不等同于最终用户手册_

## 1. 使用范围

本系统当前是以 Python 命令行、JSON/CSV 文件和本地只读 Web 管理入口为主的研究原型。推荐先使用 Web 页面或离线最小演示确认接口，再单独运行 CARLA 实机任务。任何真实仿真都必须明确启动，不会由 Web 页面或离线演示隐式触发。

## 2. 环境准备

| 项目 | 要求 |
|---|---|
| 工作目录 | `D:\Xx\竞赛\大创实施ing` |
| Python | `D:\ANACONDA\envs\Carla666-0916\python.exe` |
| CARLA | 0.9.16；实机任务服务器优先 |
| 依赖 | 基础校验依赖；SB3/Gymnasium 只在训练接口任务中需要 |
| 数据 | `data/scenarios/seed_v1/` 和 `data/scenarios/scenario_library_v1/` |

## 3. 推荐演示流程

### 3.1 运行一键离线演示

在项目根目录执行：

```powershell
tools\stage5_demo.cmd
```

成功时会输出 `M01-M08 离线最小链路通过`，并在 `artifacts/stage5_minimal_demo_v1/` 生成：

- `input_record.json`：输入记录副本；
- `compiled_carla_config.json`：编译后的 CARLA 配置；
- `<sample_id>.xosc`：OpenSCENARIO 1.0 最小交换文件；
- `<sample_id>.carla.json`：适配后的 CARLA 配置；
- `<sample_id>.adapter_manifest.json`：适配血缘和限制；
- `demo_manifest.json`：所有步骤状态和证据边界。

查看 `demo_manifest.json` 时，首先确认：

```json
{
  "carla_connected": false,
  "execution_mode": "offline_static_and_evidence"
}
```

这说明本次只是接口和历史证据演示，没有新的 CARLA 风险测量。

### 3.2 查看场景库

启动本地只读页面：

```powershell
tools\web_app.cmd
```

或者只做数据加载检查：

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe tools\web_app.py --validate-only
```

页面支持 Dashboard、场景库筛选、独立详情和历史风险/证据查看；生成、校验、任务和风险分析入口当前为边界占位，不提供写入、删除、提交 CARLA 任务或权限管理。

参数级物理约束检查：

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe tools\check_physical_constraints.py data\scenarios\seed_v1\scenarios.jsonl --output F:\Carla\project-transfer\physical_constraints_v1\seed_report.json --strict
```

该命令只做 CPU 静态参数检查，不启动 CARLA、不占用 GPU；warning 是名义速度下的危险边界提示，不是实测风险。

### 3.3 查询命令行结果

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe tools\query_scenario_library.py --collision yes --sort risk_desc --limit 5
```

查询结果中的 `observed_risk_level` 来自历史 CARLA 运行汇总；`target_risk_levels` 只是生成条件，两者不能互换。

## 4. 单场景静态检查

离线演示已经自动执行一次 Scene 04 静态校验，也可以手动检查配置：

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe scenes\scene_04_parameterized.py --config <config.json> --validate-only
```

输出 `validate-only 完成，未连接 CARLA` 只表示配置结构和字段合法，不表示仿真服务、传感器、路线或风险结果已经通过。

## 5. 单独启动真实 CARLA 运行

只有需要新增实测证据时才执行真实入口。服务器任务必须先确认 CARLA 0.9.16、项目环境、RPC 健康和 GPU1 资源，再运行：

```powershell
D:\ANACONDA\envs\Carla666-0916\python.exe scenes\scene_04_parameterized.py --config <config.json>
```

真实运行至少检查：

1. `metadata.json` 的运行状态为 `completed`；
2. 传感器写盘状态和帧数达到配置要求；
3. CARLA 服务健康；
4. 启用路线控制时路线验收通过；
5. 风险方法和 `observed_risk` 字段可追溯。

命令退出码为 0 不能单独证明以上条件全部满足。

## 6. 常见问题

| 现象 | 判断 | 处理 |
|---|---|---|
| M08 输出 `carla_connected=false` | 正常，默认是离线演示 | 查看静态产物；需要实机时另建任务 |
| `validate-only` 成功但没有风险分 | 正常，静态检查不运行 CARLA | 使用已有场景库风险或单独执行实机 |
| 场景库有 `unknown` CARLA 版本 | 历史条目缺少场景级版本字段 | 保留为证据边界，不补写未知值 |
| SB3 测试跳过 | 本机未安装可选训练依赖 | 不影响基础链路；训练任务使用服务器环境 |
| Dashboard 可打开但不能修改 | 设计如此 | 当前是本地只读原型 |

## 7. 说明书使用边界

本底稿可用于整理软件说明书的操作顺序，但正式提交前必须基于冻结版本重新运行演示、复核截图、统一版本号和模块名称。不能把本底稿中的规划项或后置能力写成当前已实现功能。
