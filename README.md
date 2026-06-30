<div align="center">
  <h1>ESG RAG Monthly Report Agent</h1>
</div>

<div align="center">
  <h3>Evidence-backed ESG monthly report generation with LangGraph, Chroma, Browser Fetch, MinerU, and LLM reranking.</h3>
</div>

<div align="center">
  <a href="https://www.python.org/" target="_blank"><img src="https://img.shields.io/badge/Python-3.11%2B-blue" alt="Python"></a>
  <a href="https://www.langchain.com/langgraph" target="_blank"><img src="https://img.shields.io/badge/LangGraph-Orchestration-purple" alt="LangGraph"></a>
  <a href="https://www.trychroma.com/" target="_blank"><img src="https://img.shields.io/badge/Vector%20Store-Chroma-green" alt="Chroma"></a>
  <a href="https://playwright.dev/python/" target="_blank"><img src="https://img.shields.io/badge/Browser-Playwright-orange" alt="Playwright"></a>
  <a href="https://github.com/opendatalab/MinerU" target="_blank"><img src="https://img.shields.io/badge/PDF-MinerU-lightgrey" alt="MinerU"></a>
</div>

<br>

本项目是一个面向 ESG 月度监测场景的 RAG Demo。系统以“中国神华”为示例公司，围绕 ESG 政策、客户所属行业动态、客户公司动态和对标企业行动四类信息源，完成资料召回、网页/PDF 抓取、正文解析、向量检索、证据重排、影响评估和月报生成。

```bash
python main.py --company 中国神华 --anchor-date 2026-06-29 --reset
```

> [!TIP]
> 这是一个工程演示项目，报告输出为可追溯草稿。正式使用时仍应结合人工复核、公司内部数据和合规审阅。

## Updated in this version

本轮更新围绕“证据质量、资料可移植性、报告可读性、运行可复现性”四个方向展开。

| Area | What changed | Why it matters |
|---|---|---|
| **Evidence Quality** | Added `evidence_reranker`: embedding wide retrieval first, then LLM reranking for `company` and `peer` chunks. | Reduces false positives where a chunk is topic-related but cannot actually support the report. |
| **Portable Sources** | `manual_sources.csv` now supports project-relative `local_path` for local HTML/PDF files. | The project can be moved or cloned without breaking local source references. |
| **Source Coverage** | Added and classified local sources across `policy`, `industry`, `company`, and `peer`. | Remote URLs, local HTML, local PDF, and online PDF can enter one unified pipeline. |
| **Report Readability** | Moved dense `[E..]` citations out of the body and into the final evidence index/source appendix. | The generated report reads more like a business monthly report while staying traceable. |
| **Run Hygiene** | Added `RUNBOOK.md`, refreshed `MANIFEST.txt`, and expanded `.gitignore`. | Keeps setup, validation, and delivery cleaner; excludes `.env`, caches, and runtime artifacts. |
| **Verified Output** | Synced `examples/` with the latest full run: fetch `35/35`, parse `35/35`, no reranker/assessment/report fallback. | Provides a reproducible reference output for checking expected behavior. |

## Why use this project?

ESG 月报并不是单纯的新闻摘要。一个可用的 ESG RAG 系统需要同时解决资料覆盖、证据质量、报告结构和可追溯性问题。

- **Evidence-backed generation**：报告生成依赖 `evidence.json` 和 `impact_assessments.json`，避免纯模型发挥。
- **Section-aware retrieval**：将资料分为 `policy`、`industry`、`company`、`peer` 四个分支，分别召回和评分。
- **Candidate queue separation**：候选层与抓取队列层分离，方便并行检索、全局去重、排序和调试。
- **Multi-format ingestion**：支持远程网页、本地 HTML、本地 PDF、在线 PDF，并统一解析成 Markdown。
- **Rerank narrow after retrieve wide**：先用 embedding 大范围召回，再用 LLM 判断证据是否真正可支撑报告。
- **Debuggable pipeline**：每个关键中间产物都会落盘，包括候选、抓取、解析、chunk、证据、重排决策和 metrics。

## Architecture

### Workflow

```text
manual_sources.csv / search_api
        ↓
section_candidate_retriever
        ↓
RankedUrlCandidate[]
        ↓
search_policy / search_industry / search_company / search_peer
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
embedding retrieval
        ↓
evidence_reranker
        ↓
impact_assessment
        ↓
report_generator
        ↓
report.md / evidence.json / impact_assessments.json / metrics.json
```

### LangGraph nodes

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

## Project layout

```text
.
├── app.py                         # Streamlit UI
├── main.py                        # CLI entrypoint
├── graph.py                       # LangGraph orchestration
├── config.py                      # Company, model, retrieval, and directory config
├── schemas.py                     # Pydantic / TypedDict schemas
├── manual_sources.csv             # Curated source registry
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variable template
├── .gitignore                     # Excludes secrets, caches, and generated runtime artifacts
├── RUNBOOK.md                     # Run and validation checklist
├── MANIFEST.txt                   # File manifest
├── agents/
│   ├── company_discovery.py
│   ├── search_agents.py
│   ├── agent_reranker.py
│   ├── impact_assessment.py
│   └── report_generator.py
├── services/
│   ├── section_candidate_retriever.py
│   ├── merge_urls_node.py
│   ├── light_crawler.py
│   ├── search_api.py
│   ├── browser_worker.py
│   ├── html_parser.py
│   ├── mineru_parser.py
│   ├── pdf_link_extractor.py
│   ├── chunker.py
│   ├── chroma_store.py
│   ├── embedding_client.py
│   ├── evidence_reranker.py
│   ├── llm_client.py
│   └── exporter.py
├── data/manual_sources/           # Curated HTML/PDF examples by section
├── examples/                      # Verified sample outputs
└── runs/                          # Runtime output directory
```

## Quickstart

### 1. Install dependencies

Python 3.11 is recommended.

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

If using conda:

```bash
conda create -n esg-rag-demo python=3.11
conda activate esg-rag-demo
pip install -r requirements.txt
python -m playwright install chromium
```

PDF parsing depends on the external MinerU CLI:

```bash
mineru --help
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Fill in an OpenAI-compatible LLM and embedding service:

```bash
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=

EMBEDDING_API_KEY=
EMBEDDING_BASE_URL=
EMBEDDING_MODEL=
```

Default source mode:

```bash
SEARCH_PROVIDER=manual
MANUAL_SOURCES_PATH=manual_sources.csv
RERANK_ENABLED=true
RERANK_SECTIONS=company,peer
MINERU_CMD=mineru
```

Do not commit `.env`.

### 3. Run the full pipeline

```bash
python main.py --company 中国神华 --anchor-date 2026-06-29 --reset
```

Expected outputs:

```text
runs/2026-06-29_中国神华/reports/report.md
runs/2026-06-29_中国神华/reports/evidence.json
runs/2026-06-29_中国神华/reports/evidence_raw.json
runs/2026-06-29_中国神华/reports/evidence_rerank_decisions.json
runs/2026-06-29_中国神华/reports/impact_assessments.json
runs/2026-06-29_中国神华/reports/metrics.json
runs/2026-06-29_中国神华/reports/errors.json
```

### 4. Run Streamlit UI

```bash
streamlit run app.py
```

## Manual source format

`manual_sources.csv` supports remote URLs and project-relative local files:

```csv
url,local_path,section_hint,priority,pinned,expected_date,source_type_hint,source_name_hint,tags,note
```

Example local source:

```csv
,data/manual_sources/company/company_01.html,company,4,false,2026-06-08,html,中国神华样例,中国神华安全生产与绿色运营动态,公司动态 HTML
```

Example remote source:

```csv
https://paper.cnstock.com/html/2026-05/29/content_2223245.htm,,company,4,false,2026-05-29,url,上海证券报,中国神华独立非执行董事离任公告,治理事件观察
```

| Field | Purpose |
|---|---|
| `url` | Remote webpage/PDF URL |
| `local_path` | Project-relative local HTML/PDF path |
| `section_hint` | `policy` / `industry` / `company` / `peer` |
| `priority` | Manual priority, 0-5 |
| `pinned` | Whether the source should be prioritized |
| `expected_date` | Source date, `YYYY-MM-DD` |
| `source_type_hint` | `html` / `pdf` / `url` |
| `source_name_hint` | Source name |
| `tags` | Short title or topic |
| `note` | Why the source matters |

## Verified run

The latest verified outputs are stored in `examples/`.

| Metric | Value |
|---|---:|
| URL candidates | 35 |
| URL queue | 35 |
| Fetch success | 35 |
| Parse success | 35 |
| Chunks | 299 |
| Final evidence | 34 |
| Impact assessments | 5 |
| Evidence rerank fallback | false |
| Impact assessment fallback | false |
| Report fallback | false |
| Report length | 5080 |

## Documentation

- `RUNBOOK.md` — operational checklist, success criteria, and troubleshooting.
- `MANIFEST.txt` — project file inventory.
- `examples/generated_report_中国神华_2026-06-29.md` — sample generated report.
- `examples/evidence_中国神华_2026-06-29.json` — final evidence package.
- `examples/metrics_中国神华_2026-06-29.json` — verified run metrics.

## Limitations

- The generated report is a draft and does not replace professional ESG review.
- Manual sources are curated for reproducible demonstration; production use should connect broader policy, announcement, news, and internal data feeds.
- PDF parsing speed depends on MinerU and local hardware.
- LLM and embedding APIs must be available for impact assessment, reranking, and report generation.

---

## Acknowledgements

This project uses LangGraph for stateful workflow orchestration, Chroma for vector retrieval, Playwright for browser-based fetching, MinerU for PDF parsing, and OpenAI-compatible LLM/embedding APIs for evidence selection and report generation.
