# ESG RAG 月报生成 Demo

本项目是一个面向 ESG 月度监测场景的 RAG Demo。系统以“中国神华”为示例公司，围绕政策、行业、公司动态和对标企业四类信息源，完成资料召回、网页/PDF 抓取、正文解析、向量检索、影响评估和月报生成。

> 说明：`examples/generated_report_中国神华_2026-06-29.md` 是一次完整运行后生成的案例报告，仅用于展示系统输出形态和链路能力。正式使用时应结合人工复核、公司内部数据和合规审阅。

## 1. 项目目标

该 Demo 主要展示三件事：

1. 将 ESG 相关资料从 URL、网页、本地 HTML、本地 PDF 中统一组织成可检索证据。
2. 用 LangGraph 串联搜索、抓取、解析、入库、检索、评估和报告生成步骤。
3. 生成带证据编号的 ESG 月报草稿，便于后续人工编辑和业务复核。

适合面试展示的重点不是“一次运行即交付正式报告”，而是完整展示一个可解释、可调试、可扩展的 RAG 工程链路。

## 2. 当前目录结构

```text
.
├── app.py                         # Streamlit 展示入口
├── main.py                        # 命令行运行入口
├── graph.py                       # LangGraph 主流程编排
├── config.py                      # 公司、模型、检索、目录配置
├── schemas.py                     # 全链路 Pydantic / TypedDict 数据结构
├── manual_sources.csv             # 手工维护的信息源清单
├── requirements.txt               # Python 依赖
├── .env.example                   # 环境变量模板，不包含真实密钥
├── agents/
│   ├── search_agents.py           # 四类检索节点入口
│   ├── company_discovery.py       # 公司画像和同行配置
│   ├── agent_reranker.py          # 可选 LLM 辅助重排
│   ├── impact_assessment.py       # ESG 影响评估
│   └── report_generator.py        # 月报生成
├── services/
│   ├── section_candidate_retriever.py  # section 内候选召回与评分
│   ├── merge_urls_node.py             # 全局 URL 去重、排序、生成抓取队列
│   ├── light_crawler.py               # 轻量抓取标题、正文、日期，用于排序
│   ├── search_api.py                  # Tavily/manual 检索入口
│   ├── browser_worker.py              # Playwright 正式抓取网页/PDF
│   ├── html_parser.py                 # HTML 正文转 Markdown
│   ├── mineru_parser.py               # PDF 通过 MinerU 解析
│   ├── chunker.py                     # Markdown 切块
│   ├── chroma_store.py                # Chroma 写入与证据检索
│   ├── embedding_client.py            # OpenAI-compatible embedding 调用
│   ├── llm_client.py                  # OpenAI-compatible LLM 调用
│   └── exporter.py                    # 输出报告、证据、评估结果
├── data/manual_sources/           # 本地 HTML/PDF 示例源
├── examples/                      # 生成案例报告和对应证据
└── runs/                          # 运行输出目录，默认只保留 .gitkeep
```

## 3. 核心架构

### 3.1 总体数据流

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
HTML / PDF 原始文件
        ↓
html_parser / mineru_parser
        ↓
Markdown 文档
        ↓
chunker
        ↓
Chroma 向量库
        ↓
retrieve_evidence
        ↓
impact_assessment
        ↓
report_generator
        ↓
report.md / evidence.json / impact_assessments.json
```

### 3.2 LangGraph 节点

`graph.py` 中的主流程如下：

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

关键设计约束：

- 检索节点只输出 `url_candidates`。
- `merge_urls_node` 是唯一负责生成 `url_queue` 的节点。
- Browser Worker 只消费 `url_queue`。
- `url_candidates.json`、`url_queue.json` 和 `url_metrics.json` 会落盘，便于排查检索质量和去重结果。

### 3.3 候选层与队列层分离

项目中把候选层和抓取队列层拆开，避免并行 search 节点直接写最终队列。

| 层级 | 数据结构 | 主要职责 |
|---|---|---|
| 候选层 | `RankedUrlCandidate` | 保存 section 内召回、评分、pinned、final_score 等信息 |
| 合并层 | `merge_urls_node` | 全局去重、排序、截断、生成 `url_queue` |
| 抓取层 | `UrlQueueItem` | 提供给 Playwright/MinerU 的正式抓取任务 |

这样做的好处是：

- 避免四个并行检索节点同时写 `url_queue`。
- 保留候选召回调试文件，方便判断哪些资料被选入队列。
- 在全局层面处理重复 URL、pinned、section 分布和抓取数量上限。

## 4. 信息源配置

`manual_sources.csv` 使用以下字段：

```csv
url,section_hint,priority,pinned,expected_date,source_type_hint,source_name_hint,tags,note
```

字段说明：

| 字段 | 含义 |
|---|---|
| `url` | 网页 URL 或本地文件的 `file://` 地址 |
| `section_hint` | `policy` / `industry` / `company` / `peer` |
| `priority` | 人工优先级，0-5 |
| `pinned` | 是否强制优先进入候选 |
| `expected_date` | 资料日期，格式 `YYYY-MM-DD` |
| `source_type_hint` | 资料形式或业务类型，可填 `html` / `pdf` / `url` 等 |
| `source_name_hint` | 来源名称 |
| `tags` | 简短标签或标题 |
| `note` | 备注，通常写明该资料为什么有用 |

本地 PDF 和 HTML 示例放在：

```text
data/manual_sources/
```

## 5. 如何运行

### 5.1 准备环境

建议使用 Python 3.11 环境。

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

如果需要解析 PDF，请确保 MinerU 可用：

```bash
which mineru
mineru --help
```

### 5.2 配置环境变量

复制模板：

```bash
cp .env.example .env
```

填写以下变量：

```bash
LLM_API_KEY=你的模型服务key
LLM_BASE_URL=OpenAI兼容接口地址
LLM_MODEL=模型名称

EMBEDDING_API_KEY=你的embedding key
EMBEDDING_BASE_URL=OpenAI兼容embedding接口地址
EMBEDDING_MODEL=embedding模型名称

SEARCH_PROVIDER=manual
MANUAL_SOURCES_PATH=manual_sources.csv
USE_AGENT_RERANK=false
MINERU_CMD=mineru
```

### 5.3 命令行运行

```bash
python main.py --company 中国神华 --anchor-date 2026-06-29 --reset
```

运行完成后，结果位于：

```text
runs/2026-06-29_中国神华/reports/report.md
runs/2026-06-29_中国神华/reports/evidence.json
runs/2026-06-29_中国神华/reports/impact_assessments.json
runs/2026-06-29_中国神华/reports/metrics.json
```

### 5.4 Streamlit 展示

```bash
streamlit run app.py
```

页面中输入公司名称和日期，勾选重新运行后点击生成月报。

## 6. 输出文件说明

| 文件 | 说明 |
|---|---|
| `queue/*_scored_candidates.json` | 各 section 内候选评分结果 |
| `queue/*_ranked_url_candidates.json` | 各 section 进入候选层的资料 |
| `queue/url_candidates.json` | 四个检索节点合并后的候选资料 |
| `queue/url_queue.json` | 最终抓取队列 |
| `queue/url_metrics.json` | URL 去重、排序、section 分布等指标 |
| `queue/fetched_docs.json` | 抓取结果 |
| `queue/parsed_docs.json` | 解析结果 |
| `reports/evidence.json` | 检索出的证据包 |
| `reports/impact_assessments.json` | ESG 影响评估结果 |
| `reports/report.md` | 月报草稿 |
| `reports/metrics.json` | 本次运行指标 |
| `reports/errors.json` | 错误日志 |

## 7. 生成案例

本包附带一次完整运行后的生成案例：

```text
examples/generated_report_中国神华_2026-06-29.md
examples/evidence_中国神华_2026-06-29.json
examples/impact_assessments_中国神华_2026-06-29.json
examples/metrics_中国神华_2026-06-29.json
```

该案例对应的运行指标摘要：

| 指标 | 数值 |
|---|---:|
| URL 候选 | 17 |
| URL 队列 | 17 |
| 抓取成功 | 16 |
| 解析成功 | 16 |
| Chunk 数量 | 67 |
| Evidence 数量 | 30 |
| 影响评估数量 | 7 |
| 报告长度 | 6605 |

## 8. 面试展示建议

建议展示顺序：

1. 先展示 `graph.py`，说明 LangGraph 节点如何串联。
2. 展示 `section_candidate_retriever.py`，说明候选召回、轻量抓取和规则评分。
3. 展示 `merge_urls_node.py`，说明为什么不让并行检索节点直接写 `url_queue`。
4. 展示 `browser_worker.py` 和 `mineru_parser.py`，说明网页和 PDF 如何进入统一解析链路。
5. 展示 `chroma_store.py`，说明证据检索如何支撑报告。
6. 最后打开 `examples/generated_report_中国神华_2026-06-29.md`，说明报告是由证据和影响评估生成的草稿，正式使用前需要人工复核。

推荐强调的工程点：

- 候选层和抓取队列层分离，便于并行、去重和调试。
- 每个关键中间结果都会落盘，方便定位检索、抓取、解析或生成问题。
- 支持网页、本地 HTML、本地 PDF 和在线 PDF。
- 报告中包含证据编号，便于回溯来源。
- Demo 保留人工源配置，便于控制展示质量，同时也支持 Tavily 扩展。

## 9. 当前限制

- 生成报告是草稿，不替代人工 ESG 专业判断。
- 本地 manual sources 主要用于演示链路稳定性，正式项目需要接入更完整的新闻、公告和政策数据源。
- PDF 解析速度取决于 MinerU 和本机算力。
- LLM 与 embedding 接口需保持可用，否则会影响评估和报告生成。

## 10. 一句话介绍

这是一个以 ESG 月报为场景的 RAG 工程 Demo：系统先组织和筛选资料，再抓取解析网页与 PDF，随后将内容写入向量库，最后基于证据生成可追溯的月报草稿。
