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

面向 ESG 月度监测的 RAG 工作流。默认公司为“中国神华”，资料按 `policy`、`industry`、`company`、`peer` 四类来源组织，覆盖候选召回、网页/PDF 抓取、正文解析、向量入库、证据重排、影响评估和报告导出。

```bash
python main.py --company 中国神华 --anchor-date 2026-06-29 --reset
```

> [!TIP]
> 输出内容适合作为研究和内部评审材料；用于正式披露前，应补充公司内部数据、业务确认和合规审阅。

## Updated in this version

当前版本重点放在证据质量、资料可移植性、报告可读性和运行复现。

| Area | What changed | Why it matters |
|---|---|---|
| **Evidence Quality** | Added `evidence_reranker`: embedding wide retrieval first, then LLM reranking for `company` and `peer` chunks. | Reduces false positives where a chunk is topic-related but cannot actually support the report. |
| **Portable Sources** | `manual_sources.csv` now supports project-relative `local_path` for local HTML/PDF files. | The project can be moved or cloned without breaking local source references. |
| **Source Coverage** | Added and classified local sources across `policy`, `industry`, `company`, and `peer`. | Remote URLs, local HTML, local PDF, and online PDF can enter one unified pipeline. |
| **Report Readability** | Moved dense `[E..]` citations out of the body and into the final evidence index/source appendix. | The generated report reads more like a business monthly report while staying traceable. |
| **Run Hygiene** | Added `RUNBOOK.md`, refreshed `MANIFEST.txt`, and expanded `.gitignore`. | Keeps setup, validation, and delivery cleaner; excludes `.env`, caches, and runtime artifacts. |
| **LangSmith / Studio** | Added `langgraph.json`, `studio_graph`, and LangSmith OpenAI tracing wrapper. | The graph can run in LangGraph Studio and send node/model traces to LangSmith when enabled. |
| **Verified Output** | Synced `examples/` with the latest full run: fetch `35/35`, parse `35/35`, no reranker/assessment/report fallback. | Provides a reproducible reference output for checking expected behavior. |

## Why use this project?

ESG 月报的关键不在于汇总新闻，而在于把外部变化转化为可追溯的管理判断。该工作流重点处理四个问题：资料覆盖、证据质量、报告结构和运行可复查。

- **Evidence-backed generation**：报告生成阶段只读取 `evidence.json` 和 `impact_assessments.json`。
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

This Mermaid graph mirrors the LangGraph Studio node layout and renders directly on GitHub.

```mermaid
flowchart TD
    START(["__start__"]) --> INIT["init_context"]
    INIT --> DISCOVERY["company_discovery"]
    DISCOVERY --> TASKS["build_search_tasks"]

    TASKS --> POLICY["search_policy"]
    TASKS --> INDUSTRY["search_industry"]
    TASKS --> COMPANY["search_company"]
    TASKS --> PEER["search_peer"]

    POLICY --> MERGE["merge_urls"]
    INDUSTRY --> MERGE
    COMPANY --> MERGE
    PEER --> MERGE

    MERGE --> FETCH["fetch_pages"]
    FETCH --> PARSE["parse_documents"]
    PARSE --> INDEX["index_chroma"]
    INDEX --> RETRIEVE["retrieve_evidence"]
    RETRIEVE --> ASSESS["assess_impact"]
    ASSESS --> REPORT["generate_report"]
    REPORT --> EXPORT["export_files"]
    EXPORT --> END(["__end__"])

    classDef terminal fill:#eeeeee,stroke:#8a8a8a,stroke-width:1px,color:#111;
    classDef setup fill:#f4edff,stroke:#9b72cf,stroke-width:1px,color:#5b21b6;
    classDef plan fill:#fff4e6,stroke:#f4a261,stroke-width:1px,color:#9a3412;
    classDef search fill:#ecfdf5,stroke:#55b86a,stroke-width:1px,color:#168821;
    classDef merge fill:#fdf2f8,stroke:#e879f9,stroke-width:1px,color:#be185d;
    classDef parse fill:#faf5ff,stroke:#d8b4fe,stroke-width:1px,color:#7e22ce;
    classDef evidence fill:#fdf2f8,stroke:#f0abfc,stroke-width:1px,color:#be185d;
    classDef writing fill:#eef2ff,stroke:#818cf8,stroke-width:1px,color:#3730a3;

    class START,END terminal;
    class INIT setup;
    class DISCOVERY,TASKS plan;
    class POLICY,INDUSTRY,COMPANY,PEER,FETCH,INDEX,EXPORT search;
    class MERGE merge;
    class PARSE parse;
    class RETRIEVE evidence;
    class ASSESS,REPORT writing;
```

### Graph node format

LangGraph uses `ESGWorkflowState` as the shared state. Each node receives the current state and returns only the fields it wants to update; LangGraph then merges those partial updates into the next state.

```python
def some_node(state: ESGWorkflowState) -> dict:
    return {
        "state_key": value,
        "metrics": {...},
        "errors": [...],
    }
```

The four search branches use a fan-out/fan-in pattern: `build_search_tasks` dispatches to `search_policy`, `search_industry`, `search_company`, and `search_peer`; `merge_urls` waits for all four branches and then builds one unified fetch queue.

| Node | Role | Main state input | Main state output / artifacts |
|---|---|---|---|
| `init_context` | Initialize the reporting run. | `company`, `anchor_date` | `run_id`, `period_start`, `period_end`, `run_paths`, `chroma_path`, `collection_name`, base `metrics`. |
| `company_discovery` | Build the company profile and peer list. | `company` | `company_profile`, `queue/company_profile.json`, peer count metric. |
| `build_search_tasks` | Create section-aware search plans. | `period_start`, `period_end` | `search_tasks`, `queue/search_tasks.json`, search task count metric. |
| `search_policy` | Retrieve ESG policy, rating, and standard candidates. | `search_tasks`, report period | Appends `url_candidates`; writes policy scoring/debug files under `queue/`. |
| `search_industry` | Retrieve sector news and best-practice candidates. | `search_tasks`, report period | Appends `url_candidates`; writes industry scoring/debug files under `queue/`. |
| `search_company` | Retrieve client-company announcements and news. | `search_tasks`, report period | Appends `url_candidates`; writes company scoring/debug files under `queue/`. |
| `search_peer` | Retrieve peer-company ESG action candidates. | `search_tasks`, report period | Appends `url_candidates`; writes peer scoring/debug files under `queue/`. |
| `merge_urls` | Normalize, deduplicate, and rank all URL candidates. | `url_candidates` | `url_queue`, `queue/url_candidates.json`, `queue/url_queue.json`, `queue/url_metrics.json`. |
| `fetch_pages` | Fetch remote URLs and local `file://` sources. | `url_queue` | `fetched_docs`, raw HTML/PDF files, screenshots/metadata when available, `queue/fetched_docs.json`. |
| `parse_documents` | Route HTML to the HTML parser and PDF to MinerU. | `fetched_docs` | `parsed_docs`, discovered PDF attachments, `queue/parsed_docs.json`, `queue/discovered_pdf_candidates.json`. |
| `index_chroma` | Chunk parsed Markdown and write vectors to Chroma. | `parsed_docs`, `chroma_path`, `collection_name` | `chunks`, `queue/chunks_preview.json`, Chroma collection records. |
| `retrieve_evidence` | Retrieve section evidence and optionally run LLM reranking. | `chunks` in Chroma, section retrieval queries | `evidence_pack`, `reports/evidence.json`, `reports/evidence_raw.json`, `reports/evidence_rerank_decisions.json`. |
| `assess_impact` | Convert evidence into ESG impact assessments. | `evidence_pack` | `impact_assessments`, `reports/impact_assessments.json`; uses fallback only if the LLM call fails. |
| `generate_report` | Generate the monthly report from evidence and assessments. | `evidence_pack`, `impact_assessments`, `parsed_docs` | `report_markdown`, report length/fallback metrics. |
| `export_files` | Persist final report package and runtime diagnostics. | `report_markdown`, `evidence_pack`, `impact_assessments`, `metrics`, `errors` | `reports/report.md`, `reports/evidence.json`, `reports/impact_assessments.json`, `reports/metrics.json`, `reports/errors.json`. |

## Project layout

```text
.
├── app.py                         # Streamlit UI
├── main.py                        # CLI entrypoint
├── graph.py                       # LangGraph orchestration
├── config.py                      # Company, model, retrieval, and directory config
├── langgraph.json                 # LangGraph Studio / API server configuration
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
│   ├── langsmith_utils.py
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
conda create -n esg-rag python=3.11
conda activate esg-rag
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

### 5. Run LangGraph Studio / LangSmith tracing

The project includes `langgraph.json`, which exposes the compiled graph as:

```text
esg_monthly_report -> ./graph.py:studio_graph
```

To validate the Studio configuration:

```bash
langgraph validate
```

To start the local LangGraph API server used by Studio:

```bash
langgraph dev --allow-blocking --no-browser --port 2024
```

Then open LangSmith Studio and set the API server URL to:

```text
http://127.0.0.1:2024
```

If Studio shows `Failed to fetch`, the local API server is not running or the browser cannot reach it. Keep the `langgraph dev` process running while using Studio.

Optional LangSmith tracing:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=ESG-RAG-Monthly-Report
```

## Manual source format

`manual_sources.csv` supports remote URLs and project-relative local files:

```csv
url,local_path,section_hint,priority,pinned,expected_date,source_type_hint,source_name_hint,tags,note
```

Local source example:

```csv
,data/manual_sources/company/company_01.html,company,4,false,2026-06-08,html,中国神华样例,中国神华安全生产与绿色运营动态,公司动态 HTML
```

Remote source example:

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

- The generated report is a working draft and does not replace ESG, legal, or disclosure review.
- Manual sources are curated for reproducible runs; production deployments should connect broader policy, announcement, news, and internal data feeds.
- PDF parsing speed depends on MinerU and local hardware.
- LLM and embedding APIs must be available for impact assessment, reranking, and report generation.

---

## Acknowledgements

This project uses LangGraph for stateful workflow orchestration, Chroma for vector retrieval, Playwright for browser-based fetching, MinerU for PDF parsing, and OpenAI-compatible LLM/embedding APIs for evidence selection and report generation.
