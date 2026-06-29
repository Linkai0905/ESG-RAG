<div align="center">
  <h1>ESG RAG 月报生成系统</h1>
  <h3>基于 LangGraph 的 ESG 资料检索、证据组织与月报生成流程</h3>
</div>

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue" alt="Python 3.11">
  <img src="https://img.shields.io/badge/LangGraph-workflow-green" alt="LangGraph">
  <img src="https://img.shields.io/badge/RAG-evidence--based-orange" alt="RAG">
  <img src="https://img.shields.io/badge/Streamlit-UI-red" alt="Streamlit">
</div>

<br>

本项目面向 ESG 月度监测场景，将政策、行业、公司动态和对标企业信息统一组织为可检索证据，并基于证据生成带来源编号的 ESG 月报草稿。系统支持网页、本地 HTML、本地 PDF、在线 PDF 等资料来源，适合用于 ESG 信息跟踪、报告初稿生成和资料归档。

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

```bash
python main.py --company 中国神华 --anchor-date 2026-06-29 --reset
```

> `examples/generated_report_中国神华_2026-06-29.md` 是一次完整运行后的样例输出。正式使用时应结合公司内部数据、专业判断和合规审阅。

## Why Use This Project?

ESG 月报通常需要处理多类异构资料：监管政策、评级标准、行业新闻、公司公告、同业行动、PDF 报告和网页新闻。手工整理这些资料容易出现来源分散、证据难追溯、报告口径不稳定等问题。

本项目的目标是把这些步骤组织成一条可调试的工程链路：

- **可追溯证据**：报告中的关键判断尽量关联 evidence id，便于回看来源。
- **多源资料接入**：支持人工维护的资料清单，也保留 Tavily 等搜索接口扩展点。
- **网页与 PDF 统一处理**：网页通过 Playwright 抓取，PDF 可通过 MinerU 解析后进入同一套 Markdown、chunk 和向量检索流程。
- **分层检索队列**：先生成候选资料，再统一去重、排序和构建抓取队列，便于观察每一步的质量。
- **结构化中间结果**：候选、抓取、解析、证据、影响评估和运行指标都会落盘，方便排查问题。

## Architecture

### Workflow

```text
manual_sources.csv + search_api
        ↓
section_candidate_retriever
        ↓
RankedUrlCandidate[]
        ↓
search_policy / search_industry / search_company / search_peer
        ↓
url_candidates
        ↓
merge_urls_node
        ↓
url_queue
        ↓
browser_worker
        ↓
HTML / PDF raw files
        ↓
html_parser / mineru_parser
        ↓
Markdown documents
        ↓
chunker
        ↓
Chroma vector store
        ↓
retrieve_evidence
        ↓
impact_assessment
        ↓
report_generator
        ↓
report.md / evidence.json / impact_assessments.json
```

### LangGraph Nodes

`graph.py` 编排了完整的执行流程：

```text
init_context
  ↓
company_discovery
  ↓
build_search_tasks
  ↓
search_policy ┐
search_industry ├─> merge_urls
search_company ┤
search_peer ┘
  ↓
fetch_pages
  ↓
parse_documents
  ↓
index_chroma
  ↓
retrieve_evidence
  ↓
assess_impact
  ↓
generate_report
  ↓
export_files
```

关键约束：

- 检索节点只输出 `url_candidates`。
- `merge_urls_node` 统一生成 `url_queue`。
- Browser Worker 只消费 `url_queue`。
- URL 候选、抓取队列、解析结果和运行指标都会写入 `runs/<run_id>/queue/` 或 `runs/<run_id>/reports/`。

### Candidate Layer vs Queue Layer

| Layer | Data Model | Responsibility |
|---|---|---|
| Candidate | `RankedUrlCandidate` | 保存 section 内召回、评分、pinned、final_score 等信息 |
| Merge | `merge_urls_node` | 全局去重、排序、截断、统计 section 分布 |
| Queue | `UrlQueueItem` | 提供给 Playwright 和 MinerU 的正式抓取任务 |

这种分层可以避免并行检索节点同时写最终抓取队列，也方便观察每条资料为什么被保留或丢弃。

## Project Structure

```text
.
├── app.py                         # Streamlit Web 入口
├── main.py                        # 命令行入口
├── graph.py                       # LangGraph 主流程
├── config.py                      # 公司、模型、检索、目录配置
├── schemas.py                     # Pydantic / TypedDict 数据结构
├── manual_sources.csv             # 人工维护的信息源清单
├── requirements.txt               # Python 依赖
├── .env.example                   # 环境变量模板
├── agents/
│   ├── search_agents.py           # 四类检索节点
│   ├── company_discovery.py       # 公司画像和同行配置
│   ├── agent_reranker.py          # 可选 LLM 辅助重排
│   ├── impact_assessment.py       # ESG 影响评估
│   └── report_generator.py        # 月报生成
├── services/
│   ├── section_candidate_retriever.py  # 候选召回、轻量抓取与评分
│   ├── merge_urls_node.py             # URL 去重、排序和队列生成
│   ├── light_crawler.py               # 轻量抓取标题、正文、日期
│   ├── search_api.py                  # manual / Tavily 检索入口
│   ├── browser_worker.py              # Playwright 正式抓取
│   ├── html_parser.py                 # HTML 正文转 Markdown
│   ├── mineru_parser.py               # PDF 解析
│   ├── chunker.py                     # Markdown 切块
│   ├── chroma_store.py                # Chroma 写入与证据检索
│   ├── embedding_client.py            # embedding 调用
│   ├── llm_client.py                  # LLM 调用
│   └── exporter.py                    # 输出报告和结构化文件
├── data/manual_sources/           # 本地 HTML/PDF 样例源
├── examples/                      # 一次完整运行后的样例输出
└── runs/                          # 运行输出目录，默认只保留 .gitkeep
```

## Quickstart

### 1. Create Environment

建议使用 Python 3.11。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
```

如果需要解析 PDF，请确保 MinerU 命令可用：

```bash
which mineru
mineru --help
```

### 2. Configure Environment Variables

复制模板：

```bash
cp .env.example .env
```

填写模型、检索和解析相关配置：

```bash
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_MODEL=your_model

EMBEDDING_API_KEY=your_embedding_key
EMBEDDING_BASE_URL=https://your-openai-compatible-endpoint/v1
EMBEDDING_MODEL=your_embedding_model

SEARCH_PROVIDER=manual
MANUAL_SOURCES_PATH=manual_sources.csv
USE_AGENT_RERANK=false
MINERU_CMD=mineru
```

### 3. Run From CLI

```bash
python main.py --company 中国神华 --anchor-date 2026-06-29 --reset
```

输出目录：

```text
runs/2026-06-29_中国神华/
├── queue/
├── raw/
├── parsed/
├── chroma/
└── reports/
```

核心输出文件：

```text
runs/2026-06-29_中国神华/reports/report.md
runs/2026-06-29_中国神华/reports/evidence.json
runs/2026-06-29_中国神华/reports/impact_assessments.json
runs/2026-06-29_中国神华/reports/metrics.json
runs/2026-06-29_中国神华/reports/errors.json
```

### 4. Run With Streamlit

```bash
streamlit run app.py
```

页面中输入公司名称、时间节点并运行，即可查看报告、证据、影响评估、运行指标和错误日志。

## Data Sources

`manual_sources.csv` 是当前项目的主要资料入口，字段如下：

```csv
url,section_hint,priority,pinned,expected_date,source_type_hint,source_name_hint,tags,note
```

| Field | Description |
|---|---|
| `url` | 网页 URL 或本地文件的 `file://` 地址 |
| `section_hint` | `policy` / `industry` / `company` / `peer` |
| `priority` | 人工优先级，0-5 |
| `pinned` | 是否优先进入候选 |
| `expected_date` | 资料日期，格式为 `YYYY-MM-DD` |
| `source_type_hint` | 资料类型提示，例如 `html`、`pdf`、`url` |
| `source_name_hint` | 来源名称 |
| `tags` | 标签或标题摘要 |
| `note` | 资料用途说明 |

本地 HTML/PDF 可放在：

```text
data/manual_sources/
```

## Outputs

| File | Description |
|---|---|
| `queue/*_scored_candidates.json` | 各 section 候选评分结果 |
| `queue/*_ranked_url_candidates.json` | 各 section 进入候选层的资料 |
| `queue/url_candidates.json` | 四个检索节点合并后的候选资料 |
| `queue/url_queue.json` | 最终抓取队列 |
| `queue/url_metrics.json` | URL 去重、排序和 section 分布 |
| `queue/fetched_docs.json` | 抓取结果 |
| `queue/parsed_docs.json` | 解析结果 |
| `reports/evidence.json` | 检索出的证据包 |
| `reports/impact_assessments.json` | ESG 影响评估结果 |
| `reports/report.md` | ESG 月报草稿 |
| `reports/metrics.json` | 本次运行指标 |
| `reports/errors.json` | 错误日志 |

## Example Output

仓库附带一次完整运行后的样例输出：

```text
examples/generated_report_中国神华_2026-06-29.md
examples/evidence_中国神华_2026-06-29.json
examples/impact_assessments_中国神华_2026-06-29.json
examples/metrics_中国神华_2026-06-29.json
```

对应运行指标摘要：

| Metric | Value |
|---|---:|
| URL candidates | 17 |
| URL queue | 17 |
| Fetch success | 16 |
| Parsed documents | 16 |
| Chunks | 67 |
| Evidence items | 30 |
| Impact assessments | 7 |
| Report length | 6605 |

## Notes

- 生成内容是月报草稿，不替代 ESG 专业判断、公司内部数据核验或合规审阅。
- `manual_sources.csv` 适合用于固定来源维护；如需实时新闻，可在 `services/search_api.py` 中扩展外部检索服务。
- PDF 解析速度取决于 MinerU、文档页数和本机算力。
- LLM 和 embedding 服务需要保持可用，否则会影响影响评估、报告生成和向量检索。
- 默认 `.gitignore` 会忽略 `.env`、`runs/` 输出、Chroma 数据库和 Python 缓存。

## License

本仓库未指定开源许可证。使用、分发或二次开发前，请先确认授权范围。
