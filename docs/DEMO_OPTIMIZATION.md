# Demo Optimization Notes

This document lists follow-up work for the current ESG RAG demo. It is based on code review, the existing README/runbook, and sample outputs. The items below are backlog candidates, not implemented features or quality claims.

## Current Scope

The current project is best described as an ESG monthly report MVP built around a fixed LangGraph pipeline. It can read curated ESG sources, fetch HTML/PDF content, parse documents into Markdown, write chunks to Chroma, retrieve evidence, rerank selected evidence, assess ESG impact, and generate a report package.

It is not a production ESG reporting system. It does not fully generalize across companies, does not replace ESG analysts or compliance review, and does not yet include a formal evaluation set, approval workflow, or production crawler controls.

## What Works Today

- A fixed LangGraph DAG coordinates the monthly report pipeline.
- Sources are organized into `policy`, `industry`, `company`, and `peer` sections.
- Remote URLs, local HTML, local PDF, and online PDF sources can enter the same pipeline.
- Intermediate artifacts are written under `runs/`, which makes retrieval and report generation easier to inspect.
- Chroma is used for vector retrieval, and an LLM reranker can be applied to selected evidence sections.
- Example outputs are available under `examples/` for checking the expected file structure.

## Main Gaps

- The project is still tightly coupled to the default company, 中国神华.
- Source trust is not modeled separately from content format.
- The local-file ingestion path needs stricter boundaries before it can be used outside a trusted local environment.
- Current validation mainly checks whether the pipeline runs; it does not measure evidence support, citation accuracy, or unsupported claims.
- PDF parsing, LLM calls, embedding calls, and web fetching depend on external services or tools without a locked runtime.

## P0: Correctness, Safety, and Reproducibility

These items should be addressed before presenting the demo as anything beyond a local MVP.

### 1. Make Company Configuration Pluggable

Current behavior is centered on the default company configuration. The CLI accepts `--company`, but aliases, stock codes, peer companies, industries, and search queries are still configured around 中国神华.

Proposed work:

- Add a company resolver layer.
- Load company aliases, stock codes, industry tags, and peer companies from a structured config file.
- Generate section queries from resolved company metadata instead of hard-coded defaults.
- Add a test case for at least one non-coal company to confirm the pipeline does not keep 中国神华-specific context.

Acceptance check:

- Running with a different company should produce company-specific search tasks, retrieval queries, collection names, and peer lists.

### 2. Fix Chroma Collection Naming for Chinese Company Names

The current collection name helper filters non-ASCII characters. Chinese company names can become empty in the collection slug, which may cause collisions across companies.

Proposed work:

- Include a stable short hash of the company name in the collection name.
- Optionally include stock code when available.
- Add a unit test covering Chinese company names.

Acceptance check:

- Different Chinese company names produce different collection names for the same period and embedding model.

### 3. Separate Source Authority from File Format

`source_type_hint` currently mixes source trust and content format. Values such as `html`, `pdf`, and `url` describe format, not authority.

Proposed work:

- Add `content_format`: `html`, `pdf`, `url`, `markdown`.
- Add `source_authority`: `regulator`, `exchange`, `company_official`, `filing`, `mainstream_media`, `industry_association`, `rating_agency`, `sample`, `unverified`.
- Keep existing CSV fields backward compatible during migration.
- Use authority, not file extension, in ranking and evidence caveats.

Acceptance check:

- A regulator PDF is ranked as a regulator source with PDF format, not as an unknown source.

### 4. Restrict Local File Ingestion

The current pipeline supports `file://` and project-relative local paths. This is useful for a local demo but should be constrained before broader use.

Proposed work:

- Only allow local files under `data/manual_sources/` by default.
- Reject absolute paths unless explicitly enabled by an environment flag.
- Log local file usage in run metadata.
- Convert source paths in exported evidence to project-relative paths where possible.

Acceptance check:

- Evidence output should not expose a developer machine path such as `/Users/...`.

### 5. Make Chroma Writes Idempotent

The current Chroma write path uses `collection.add`. Re-running the same period without reset can produce duplicate ID errors or leave old vectors in place.

Proposed work:

- Use deterministic IDs and `upsert` where supported.
- Clear the run-specific collection before indexing when `--reset` is used.
- Add a smoke test that runs indexing twice for the same fixture.

Acceptance check:

- Re-running the same run ID should not pollute retrieval results or fail because of duplicate vector IDs.

### 6. Add Dependency Locking and a Minimal CI Check

The current dependency file does not pin versions. This makes the demo harder to reproduce over time.

Proposed work:

- Add a lock file through `uv`, `pip-tools`, Poetry, or a Docker image.
- Add CI checks for import, schema validation, and `langgraph validate`.
- Add a smoke test that does not require live LLM credentials.

Acceptance check:

- A clean environment can install deterministic dependency versions and run the non-network smoke checks.

### 7. Preserve Parse Errors in Final Artifacts

Some parsing errors are collected locally but may not reach the final `errors.json`.

Proposed work:

- Audit all `try/except` blocks that call `_merge_errors`.
- Return merged errors from every node where errors are captured.
- Add a fixture that forces a PDF attachment parse failure.

Acceptance check:

- Forced parse failures appear in `reports/errors.json` with stage and source metadata.

## P1: RAG Quality and Evidence Review

These items improve report quality after the basic correctness and safety issues are addressed.

### 8. Rework Chunking Strategy

The current chunk size is short for ESG reports, policies, and company announcements. Short chunks can lose the relationship between fact, condition, and caveat.

Proposed work:

- Split by headings, announcement sections, paragraphs, tables, and PDF page metadata where available.
- Increase default Chinese chunk size and preserve section heading context.
- Keep source page, heading, and paragraph metadata in each chunk.

Acceptance check:

- Retrieved chunks should usually contain a complete event or policy point, not only a fragment.

### 9. Extend Reranking Beyond Company and Peer Evidence

The reranker is currently focused on `company` and `peer` sections. Policy and industry evidence can also be topic-related but not answerable.

Proposed work:

- Add configurable reranking for `policy` and `industry`.
- Keep the default conservative for local cost control.
- Build a small manually reviewed set to calibrate reranker scores.

Acceptance check:

- Reranker decisions include clear `body`, `background`, or `drop` usage labels for each enabled section.

### 10. Add a Small Evaluation Set

Run success metrics are useful, but they do not measure answer quality.

Proposed work:

- Add 30-50 reviewed examples covering company events, policy items, peer comparison, and unsupported questions.
- Track evidence support rate, citation correctness, source authority distribution, and unsupported-claim rate.
- Store evaluation outputs separately from normal `runs/` artifacts.

Acceptance check:

- The project can run an offline evaluation command and produce a quality report.

### 11. Add a Report Verifier Step

The report generator asks the model to stay within evidence, but there is no separate verifier.

Proposed work:

- Add a post-generation checker that extracts factual claims from the report.
- Match each claim to evidence IDs.
- Mark claims as `supported`, `unsupported`, or `needs_review`.
- Optionally produce a revised report draft.

Acceptance check:

- Unsupported claims are listed before the report is treated as ready for review.

### 12. Improve Web Fetching Controls

The current crawler is suitable for a local demo but does not yet have production-grade fetch controls.

Proposed work:

- Add domain allowlist/denylist support.
- Add file size limits and MIME validation.
- Avoid HTTPS-to-HTTP fallback by default.
- Add retry backoff and clearer timeout metadata.
- Record final URL, content type, status code, and download size.

Acceptance check:

- Fetch failures are explicit, auditable, and do not silently downgrade source security.

### 13. Split Provider Adapters for LLM and Embedding APIs

OpenAI-compatible providers often differ in request parameters. A single client path can become brittle.

Proposed work:

- Add provider-specific adapter classes or functions.
- Keep DeepSeek, OpenAI-compatible, and embedding calls behind a common interface.
- Add tests for JSON-mode behavior and unsupported parameter fallback.

Acceptance check:

- Switching provider configuration does not require editing business logic.

### 14. Pin MinerU Runtime Assumptions

PDF parsing depends on the external `mineru` command.

Proposed work:

- Document tested MinerU version and runtime assumptions.
- Add timeout and failure classification by parse stage.
- Add a small PDF fixture for local parser checks.

Acceptance check:

- PDF parsing failures can be diagnosed from metadata without opening raw logs.

## P2: Review Workflow and Product Shape

These items are useful if the demo becomes a team-facing internal tool.

### 15. Add a Review-Oriented UI

The Streamlit app currently runs the pipeline and displays artifacts. It does not manage analyst review.

Proposed work:

- Show evidence next to generated report sections.
- Allow reviewers to mark evidence as accepted, weak, duplicate, or irrelevant.
- Track report versions and reviewer notes.
- Export a review log with the report package.

Acceptance check:

- A reviewer can identify which evidence supports each report section without opening JSON files manually.

### 16. Extract Structured ESG KPIs

The current report is narrative-first. ESG teams often need structured fields.

Proposed work:

- Extract carbon, energy, water, waste, safety, governance, supply-chain, and disclosure-quality fields where evidence supports them.
- Record missing fields explicitly.
- Map fields to relevant disclosure or rating topics where possible.

Acceptance check:

- The output includes both narrative report text and a structured KPI/missing-data table.

### 17. Add Data Retention Rules

The pipeline writes raw HTML, PDFs, screenshots, parsed Markdown, vectors, and report artifacts.

Proposed work:

- Add retention settings for raw and parsed artifacts.
- Add a cleanup command for old runs.
- Document which files may contain source content or local paths.

Acceptance check:

- A user can remove raw source captures while keeping final report artifacts.

## Suggested Implementation Order

1. Fix company-specific configuration and collection naming.
2. Split source authority from content format.
3. Restrict local file reads and sanitize exported paths.
4. Make Chroma indexing idempotent.
5. Add lock file and CI smoke checks.
6. Improve chunking and reranking coverage.
7. Add evaluation fixtures and a report verifier.
8. Improve review UI and structured KPI output.

## Non-Goals for the Current Demo

- Do not present the project as a production ESG reporting platform.
- Do not claim analyst replacement, compliance readiness, or accuracy improvement without evaluation.
- Do not add broad claims about enterprise deployment until authentication, audit logs, permissioning, and data retention are implemented.
