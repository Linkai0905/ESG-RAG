# ESG RAG Demo 运行指引

本文件用于快速确认项目能从资料源完整运行到月报产物。详细架构说明见 `README.md`。

## 1. 环境准备

建议使用 Python 3.11。

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

PDF 解析依赖外部命令 `mineru`：

```bash
mineru --help
```

如果该命令不可用，PDF 分支会失败。完整链路运行前应先确认 MinerU 可执行。

## 2. 环境变量

从模板创建本地配置：

```bash
cp .env.example .env
```

至少需要配置：

```bash
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=
EMBEDDING_MODEL=
```

当前默认使用 `SEARCH_PROVIDER=manual`，资料来自 `manual_sources.csv` 和 `data/manual_sources/`。

## 3. 运行命令

在项目根目录执行：

```bash
python main.py --company 中国神华 --anchor-date 2026-06-29 --reset
```

运行完成后，命令行会打印 `=== ESG Demo 完成 ===`、`Metrics` 和输出路径。

## 4. 成功标准

检查以下文件：

```text
runs/2026-06-29_中国神华/reports/report.md
runs/2026-06-29_中国神华/reports/evidence.json
runs/2026-06-29_中国神华/reports/impact_assessments.json
runs/2026-06-29_中国神华/reports/metrics.json
runs/2026-06-29_中国神华/reports/errors.json
```

一次完整成功运行通常应满足：

```text
fetch_failed_count = 0
parsed_success_count = parsed_doc_count
evidence_rerank_fallback = false
impact_assessment_fallback = false
report_fallback = false
errors.json = []
```

当前验证通过的样例指标保存在：

```text
examples/metrics_中国神华_2026-06-29.json
```

## 5. 数据源维护

手工资料源集中在：

```text
manual_sources.csv
data/manual_sources/
```

本地文件建议写入 `local_path`，使用项目相对路径，例如：

```csv
,data/manual_sources/company/company_01.html,company,4,false,2026-06-08,html,中国神华样例,中国神华安全生产与绿色运营动态,公司动态 HTML
```

远程网页写入 `url`，`local_path` 留空。

重要字段：

| 字段 | 用途 |
|---|---|
| `section_hint` | 控制资料进入 `policy` / `industry` / `company` / `peer` 分支 |
| `priority` | 手工优先级，0-5 |
| `pinned` | 是否优先进入候选队列 |
| `expected_date` | 资料日期，用于周期过滤和报告判断 |
| `source_type_hint` | `html` / `pdf` / `url` |
| `tags` | 标题或主题 |
| `note` | 资料用途说明 |

## 6. 产物说明

| 路径 | 说明 |
|---|---|
| `queue/url_candidates.json` | 四个分支召回后的候选资料 |
| `queue/url_queue.json` | 最终抓取队列 |
| `queue/fetched_docs.json` | 抓取结果 |
| `queue/parsed_docs.json` | 解析结果 |
| `queue/chunks_preview.json` | 文档切块预览 |
| `reports/evidence_raw.json` | 宽召回证据 |
| `reports/evidence_rerank_decisions.json` | Reranker 评分与筛选记录 |
| `reports/evidence.json` | 最终证据包 |
| `reports/impact_assessments.json` | 事件影响评估 |
| `reports/report.md` | 月报草稿 |
| `reports/metrics.json` | 运行指标 |
| `reports/errors.json` | 错误记录 |

## 7. 常见问题

`ModuleNotFoundError`：确认已安装 `requirements.txt`，并在正确 Python 环境中运行。

`playwright` 浏览器缺失：执行 `python -m playwright install chromium`。

PDF 解析失败：确认 `MINERU_CMD` 指向可执行的 MinerU 命令，且 `mineru --help` 可运行。

LLM 或 embedding 报错：检查 `.env` 中 API key、base URL 和模型名是否可用。

报告生成但内容质量不稳定：优先检查 `reports/evidence.json` 和 `reports/evidence_rerank_decisions.json`，确认进入写作阶段的证据是否足够准确。
