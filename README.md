# Digital Society Sandbox

数字社会仿真沙盒（Digital Society Sandbox，简称 DSS）是一个从零构建的、可复现的 Agent-Based Simulation 实验平台。它把个人、家庭、企业、商品、货币、住房、劳动市场、教育、社会关系、信息传播和制度规则放进同一个小型虚拟社会中，用于观察宏观现象如何由微观行为逐步涌现。

> **研究边界**：DSS 是实验与教学平台，不是现实社会的准确模型，也不用于预测现实政策后果。所有指标、规则和“年度报告”都必须标记为模拟结果。

## 当前交付内容

- `MiniCity`：100 Citizens、20 Businesses、30 Houses、School、Hospital、Market 等基础设施。
- 可追踪经济：工资、价格、购买、库存、租金、储蓄、简化税收和政府支出。
- 可检查决策：Citizen 和 Business 的行为会记录候选行动、权重及选择原因。
- 社会网络：Familiarity、Trust、Affinity、Conflict、Communication Frequency 分开保存。
- 信息传播：News / Rumor / Event 通过位置、关系和媒体渠道扩散。
- 确定性：所有随机过程使用 seed；相同 seed、场景和规则应产生相同结果。
- 快照、交易账本、年度报告、策略对照实验、健康监控和测试入口。

## 快速开始

需要 Python 3.10+。项目默认只使用标准库；测试和打包工具可按需安装。建议在项目根目录运行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\run_demo.py --days 365 --seed 42 --out artifacts\minicity
```

Linux/macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/run_demo.py --days 365 --seed 42 --out artifacts/minicity
```

运行完成后，`artifacts/minicity` 通常包含：

| 文件 | 用途 |
|---|---|
| `annual_report.json` / `annual_report.md` | 年度宏观指标、异常和模拟声明 |
| `snapshots/` | 每日或每周社会状态快照 |
| `transactions.jsonl` | Buyer、Seller、Amount、Good、Time、Reason |
| `events.jsonl` | 信息与社会事件流水 |
| `health.json` | Money Explosion、NaN、Agent Stuck 等健康检查 |
| `experiment_comparison.json` | 相同 seed 的政策对照结果（如启用） |

也可以直接使用包入口（未安装时先设置 `PYTHONPATH=src`）：

```bash
PYTHONPATH=src python -m dss --days 365 --seed 42 --out artifacts/minicity
```

## 批量实验

以下命令运行相同场景与 seed 的 Tax 5% / Tax 15% 对照。它不会调用任何收费模型 API：

```bash
python scripts/run_policy_comparison.py --seeds 1,2,3,4,5 --days 365 --out artifacts/tax-policy
```

无头模式支持更长批次；建议先用少量 seed 验证再扩展到 `100 Citizens × 365 Days × 100 Seeds`：

```bash
python scripts/run_experiment.py --seeds 1-100 --days 365 --headless --out artifacts/batch-100
```

## 测试与验收

```bash
python -m pytest -q
python scripts/qa_smoke.py --days 30 --seed 42
```

重点测试：确定性、Save/Load、365-day stability、NaN、负库存、Agent Stuck、企业死锁、内存增长、货币守恒（适用范围内）。

## Windows 打包

安装 PyInstaller 后执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

产物位于 `dist\DigitalSocietySandbox.exe`，另有无头命令行版 `dist\DigitalSocietySandboxCLI.exe`。PyInstaller 必须在目标 Windows 环境运行，才能生成 Windows PE `.exe`；Linux CI 中也会验证同名开发版 ELF 二进制。

## 100 Seed 长程验收

```bash
PYTHONPATH=src python scripts/run_100_seed_validation.py \
  --days 365 --seeds 100 --workers 8 \
  --out artifacts/validation_100_seeds
```

输出 `validation.json`、`validation.md` 和 `metrics.csv`，逐 Seed 检查 NaN、负库存、货币爆炸、企业死锁、无交易、Agent Stuck 等异常。

## 设计原则

1. **可检查而非黑箱**：每个 Citizen / Business 决策都尽量保存候选行动、权重、约束和最终原因。
2. **账本优先**：货币和商品移动通过交易、工资、租金、税收或政府支出事件进入可查询流水。
3. **规则可替换**：税率、最低工资、教育成本、交通成本、福利参数和企业规则都是虚拟世界参数。
4. **长时程优先**：地图上移动的“小人”不是完成标准；必须通过健康监控、长时间运行和测试。
5. **不混淆现实**：报告页和导出文件都注明“模拟结果，不代表现实政策预测”。

## 目录结构

```text
src/dss/              Python 包
  core/               数据模型、随机源与模拟核心
  experiments/        批量实验与政策比较
  systems/            经济、劳动力、住房、教育、社会与信息子系统
  ui/                 可视化入口（若启用）
scripts/              演示、实验、QA 与打包脚本
tests/                自动化验收测试
artifacts/            运行时输出（不应提交大文件）
```

## 许可证与数据

本项目默认只使用合成数据。不要将真实个人数据、真实政治立场或未经授权的游戏/商业数据导入模拟。项目内的示例城市、事件与人物均为虚构。
