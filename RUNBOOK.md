# ESG RAG 运行手册

该手册用于验证从资料源到报告产物的完整链路。架构说明见 `README.md`。

## 1. 环境准备

推荐 Python 3.11。

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

PDF 解析依赖外部命令 `mineru`：

```bash
mineru --help
```

该命令不可用时，PDF 解析分支无法完成。完整运行前先确认 MinerU 可执行。

## 2. 环境变量

创建本地配置：

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

默认使用 `SEARCH_PROVIDER=manual`，资料来自 `manual_sources.csv` 和 `data/manual_sources/`。

## 3. 运行命令

在项目根目录执行：

```bash
python main.py --company 中国神华 --anchor-date 2026-06-29 --reset
```

运行结束后，命令行输出运行摘要、metrics 和产物路径。

## 4. LangGraph Studio / LangSmith

项目根目录包含 `langgraph.json`，Studio 入口：

```text
esg_monthly_report -> ./graph.py:studio_graph
```

校验配置：

```bash
langgraph validate
```

启动本地 LangGraph API server：

```bash
langgraph dev --allow-blocking --no-browser --port 2024
```

在 LangSmith Studio 的 Server connection settings 中填写：

```text
http://127.0.0.1:2024
```

启用 LangSmith Tracing 时，在 `.env` 中配置：

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=ESG-RAG-Monthly-Report
```

Studio 显示 `Failed to fetch` 时，优先检查 `langgraph dev` 是否仍在运行、端口是否为 `2024`、浏览器是否能访问本地 server。

## 5. 成功标准

检查以下文件：

```text
runs/2026-06-29_中国神华/reports/report.md
runs/2026-06-29_中国神华/reports/evidence.json
runs/2026-06-29_中国神华/reports/impact_assessments.json
runs/2026-06-29_中国神华/reports/metrics.json
runs/2026-06-29_中国神华/reports/errors.json
```

完整运行应满足：

```text
fetch_failed_count = 0
parsed_success_count = parsed_doc_count
evidence_rerank_fallback = false
impact_assessment_fallback = false
report_fallback = false
errors.json = []
```

验证样例指标：

```text
examples/metrics_中国神华_2026-06-29.json
```

## 6. 数据源维护

手工资料源集中在：

```text
manual_sources.csv
data/manual_sources/
```

本地文件写入 `local_path`，使用项目相对路径，例如：

```csv
,data/manual_sources/company/company_01.html,company,4,false,2026-06-08,html,中国神华样例,中国神华安全生产与绿色运营动态,公司动态 HTML
```

远程网页写入 `url`，`local_path` 留空。

字段说明：

| 字段 | 用途 |
|---|---|
| `section_hint` | 指定 `policy` / `industry` / `company` / `peer` 分支 |
| `priority` | 手工优先级，0-5 |
| `pinned` | 固定优先级 |
| `expected_date` | 资料日期，用于周期过滤和报告判断 |
| `source_type_hint` | `html` / `pdf` / `url` |
| `tags` | 标题或主题 |
| `note` | 来源备注 |

## 7. 产物说明

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
| `reports/report.md` | 报告正文 |
| `reports/metrics.json` | 运行指标 |
| `reports/errors.json` | 错误记录 |

## 8. 常见问题

`ModuleNotFoundError`：安装 `requirements.txt`，并确认当前 Python 环境正确。

`playwright` 浏览器缺失：执行 `python -m playwright install chromium`。

`LangSmith Studio Failed to fetch`：执行 `langgraph dev --allow-blocking --no-browser --port 2024`，并将 Studio API server 设置为 `http://127.0.0.1:2024`。

PDF 解析失败：确认 `MINERU_CMD` 指向可执行的 MinerU 命令，且 `mineru --help` 可运行。

LLM 或 embedding 报错：检查 `.env` 中 API key、base URL 和模型名是否可用。

报告内容异常：优先检查 `reports/evidence.json` 和 `reports/evidence_rerank_decisions.json`，确认进入写作阶段的证据是否准确。
