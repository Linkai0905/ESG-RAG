from __future__ import annotations

import hashlib
import operator
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from typing_extensions import Annotated, TypedDict

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


def ensure_date_str(v: Optional[str]) -> Optional[str]:
    """
    统一日期格式：YYYY-MM-DD。
    Search API 有时返回空值，允许 None。
    """
    if v is None or v == "":
        return None

    if isinstance(v, datetime):
        return v.date().isoformat()

    if isinstance(v, date):
        return v.isoformat()

    if isinstance(v, str):
        v = v.strip()
        # 只接受 YYYY-MM-DD，避免后面 metadata filter 混乱
        date.fromisoformat(v)
        return v

    raise ValueError(f"Invalid date value: {v}")


def date_to_int(v: Optional[str]) -> int:
    if not v:
        return 0
    return int(v.replace("-", ""))


def validate_http_url(v: str) -> str:
    if not isinstance(v, str):
        raise ValueError("url must be string")
    v = v.strip()
    if not (
        v.startswith("http://")
        or v.startswith("https://")
        or v.startswith("file://")
    ):
        raise ValueError(f"Only http/https/file URL is supported: {v}")
    return v


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def merge_dicts(left: Dict[str, Any] | None, right: Dict[str, Any] | None) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    if left:
        merged.update(left)
    if right:
        merged.update(right)
    return merged


class StrictModel(BaseModel):
    """
    所有业务 Schema 的基类。
    extra='forbid' 可以尽早发现 Agent 输出字段错误。
    """
    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        use_enum_values=True,
    )


# =========================
# Enums
# =========================

class SectionType(str, Enum):
    POLICY = "policy"       # ESG政策、评级、标准
    INDUSTRY = "industry"   # 行业新闻、最佳实践
    COMPANY = "company"     # 中国神华公司动态
    PEER = "peer"           # 对标企业行动


class SourceType(str, Enum):
    POLICY = "policy"
    STANDARD = "standard"
    RATING = "rating"
    INDUSTRY_NEWS = "industry_news"
    BEST_PRACTICE = "best_practice"
    COMPANY_NEWS = "company_news"
    ANNOUNCEMENT = "announcement"
    PEER_ACTION = "peer_action"
    OFFICIAL = "official"
    UNKNOWN = "unknown"


class CandidateOrigin(str, Enum):
    MANUAL = "manual"
    AI_SEARCH = "ai_search"


class FetchStatus(str, Enum):
    PENDING = "pending"
    FETCHING = "fetching"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ParseStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ParserType(str, Enum):
    HTML = "html"
    MINERU = "mineru"
    FALLBACK_SNIPPET = "fallback_snippet"


class ESGDimension(str, Enum):
    E = "E"
    S = "S"
    G = "G"
    MIXED = "Mixed"
    UNKNOWN = "Unknown"


class ImpactDirection(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"


class Materiality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ActionOwner(str, Enum):
    ESG_DISCLOSURE = "ESG披露"
    ENV_MANAGEMENT = "环境管理"
    SAFETY_PRODUCTION = "安全生产"
    INVESTOR_RELATIONS = "投资者关系"
    COMPLIANCE_GOVERNANCE = "合规治理"
    STRATEGY_MANAGEMENT = "战略管理"
    DATA_MANAGEMENT = "数据管理"
    UNKNOWN = "待确认"


# =========================
# Company / Search
# =========================

class CompanyProfile(StrictModel):
    """
    Company Discovery Agent 输出。
    Demo 阶段可以写死，中国神华先不必动态发现。
    """
    company: str = "中国神华"
    aliases: List[str] = Field(default_factory=list)
    industries: List[str] = Field(default_factory=list)
    peer_companies: List[str] = Field(default_factory=list)
    stock_codes: List[str] = Field(default_factory=list)

    search_keywords: Dict[str, List[str]] = Field(default_factory=dict)


class SearchTask(StrictModel):
    """
    Search Planner 输出。
    每个 Search Agent 根据该任务去调用搜索 API。
    """
    task_id: str
    section: SectionType
    queries: List[str]

    period_start: str
    period_end: str
    top_k_per_query: int = 5

    must_include: List[str] = Field(default_factory=list)
    exclude_keywords: List[str] = Field(default_factory=list)
    preferred_domains: List[str] = Field(default_factory=list)

    @field_validator("period_start", "period_end")
    @classmethod
    def _validate_date(cls, v: str) -> str:
        return ensure_date_str(v) or ""


class RawCandidate(StrictModel):
    """
    manual CSV 或 AI/Search 的原始候选。
    """
    url: str
    title: str = ""
    snippet: str = ""

    section_hint: str = ""
    priority: int = Field(default=0, ge=0, le=5)
    pinned: bool = False

    expected_date: Optional[str] = None
    source_name: str = ""

    tags: List[str] = Field(default_factory=list)
    note: str = ""

    origin: CandidateOrigin
    query: str = ""
    discovered_by: str = ""

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("expected_date")
    @classmethod
    def _validate_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, v):
        if not v:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [x.strip() for x in v.replace("，", ",").split(",") if x.strip()]
        return []


class ManualSourceItem(StrictModel):
    """
    manual CSV/JSON 的人工候选源。
    """
    url: str
    title: str = ""
    snippet: str = ""

    section_hint: str = ""
    source_type_hint: str = ""
    priority: int = Field(default=0, ge=0, le=5)
    pinned: bool = False

    expected_date: Optional[str] = None
    source_name_hint: str = ""

    tags: List[str] = Field(default_factory=list)
    note: str = ""

    query: str = ""
    discovered_by: str = "manual"

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("expected_date")
    @classmethod
    def _validate_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)

    @field_validator("tags", mode="before")
    @classmethod
    def _parse_tags(cls, v):
        if not v:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [x.strip() for x in v.replace("，", ",").split(",") if x.strip()]
        return []


class CrawledContent(StrictModel):
    """
    轻量 crawler 抓取结果，只用于排序和补 metadata。
    不替代后续 Browser Worker。
    """
    url: str
    canonical_url: str

    title: str = ""
    snippet: str = ""
    body_text: str = ""

    publish_date: Optional[str] = None
    source_name: str = ""

    content_type: str = ""
    file_ext: str = ""

    content_hash: str = ""

    crawl_failed: bool = False
    error: str = ""

    @field_validator("url", "canonical_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)


class EnrichedCandidate(StrictModel):
    """
    raw candidate + crawler enrich 后的候选。
    这是算法层打分的输入。
    """
    candidate_id: str

    url: str
    canonical_url: str

    title: str = ""
    snippet: str = ""
    body_text: str = ""

    publish_date: Optional[str] = None
    source_name: str = ""
    source_type: SourceType = SourceType.UNKNOWN

    section_hint: str = ""
    priority: int = Field(default=0, ge=0, le=5)
    pinned: bool = False

    origin: CandidateOrigin
    query: str = ""
    discovered_by: str = ""

    content_type: str = ""
    file_ext: str = ""
    content_hash: str = ""

    tags: List[str] = Field(default_factory=list)

    duplicate_url: bool = False
    duplicate_content: bool = False

    crawl_failed: bool = False
    error: str = ""

    @field_validator("url", "canonical_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)


class ScoreResult(StrictModel):
    """
    规则层打分结果。
    """
    candidate: EnrichedCandidate

    algorithm_score: float
    score_breakdown: Dict[str, float]

    agent_score: Optional[float] = None
    final_score: Optional[float] = None
    agent_reason: str = ""

    selected_by: str = "rule_scorer"


class AgentRerankDecision(StrictModel):
    candidate_id: str

    semantic_relevance: int = Field(ge=1, le=5)
    section_fit: int = Field(ge=1, le=5)
    evidence_strength: int = Field(ge=1, le=5)
    novelty: int = Field(ge=1, le=5)

    agent_score: float = Field(ge=0, le=100)
    reason: str


class EnrichedManualCandidate(EnrichedCandidate):
    """
    manual rule scorer 兼容模型。
    """
    origin: CandidateOrigin = CandidateOrigin.MANUAL

    @property
    def is_manual(self) -> bool:
        return self.origin == CandidateOrigin.MANUAL.value


class RuleScoreResult(StrictModel):
    """
    manual rule scorer 兼容输出。
    """
    candidate: EnrichedManualCandidate

    algorithm_score: float
    score_breakdown: Dict[str, float]

    agent_score: Optional[float] = None
    final_score: Optional[float] = None
    agent_reason: str = ""

    selected_by: str = "rule_scorer"


class RankedUrlCandidate(StrictModel):
    """
    Search Agent 的标准输出。
    这是 url_candidates 层，不是最终 url_queue。
    """
    candidate_id: str
    url_id: str

    url: str
    canonical_url: str

    title: str = ""
    snippet: str = ""

    section: str
    section_hint: str = ""

    publish_date: Optional[str] = None
    source_name: str = ""
    source_type: SourceType = SourceType.UNKNOWN

    origin: CandidateOrigin

    query: str = ""
    discovered_by: str = ""

    pinned: bool = False
    priority: int = Field(default=0, ge=0, le=5)

    algorithm_score: float = 0.0
    agent_score: Optional[float] = None
    final_score: float = 0.0

    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    agent_reason: str = ""

    tags: str = ""

    crawl_failed: bool = False
    duplicate_url: bool = False
    duplicate_content: bool = False

    content_type: str = ""
    file_ext: str = ""

    @field_validator("url", "canonical_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)


class UrlCandidate(StrictModel):
    """
    四类 Search Agent 的统一输出。
    注意：Agent 只输出 URL 候选，不输出网页正文。
    """
    url: str
    title: str = ""
    snippet: str = ""

    source_name: str = ""
    publish_date: Optional[str] = None

    section: SectionType
    source_type: SourceType = SourceType.UNKNOWN

    query: str
    discovered_by: str
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    requires_browser: bool = True
    requires_mineru: bool = False

    priority: int = Field(default=50, ge=0, le=100)
    reason: str = ""

    # manual / scoring debug fields
    is_manual: bool = False
    pinned: bool = False
    manual_priority: int = Field(default=0, ge=0, le=5)

    algorithm_score: float = 0.0
    agent_score: Optional[float] = None
    final_score: Optional[float] = None

    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    agent_reason: str = ""
    tags: str = ""
    section_tags: str = ""
    merged_candidate_count: int = 1

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_publish_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)


class UrlQueueItem(StrictModel):
    """
    URL Queue 的标准元素。
    Search Agent 输出 UrlCandidate 后，经过 URL Normalizer + Deduper 变成 UrlQueueItem。
    """
    url_id: str

    canonical_url: str
    original_url: str
    parent_url: str = ""

    title: str = ""
    snippet: str = ""

    section: SectionType
    source_type: SourceType = SourceType.UNKNOWN
    source_name: str = ""
    publish_date: Optional[str] = None
    publish_date_int: int = 0

    priority: int = Field(default=50, ge=0, le=100)
    status: FetchStatus = FetchStatus.PENDING
    retry_count: int = Field(default=0, ge=0)

    discovered_by: str
    query: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # 用于追踪 PDF 附件来源、继承 section/source_type
    inherited_from_url_id: str = ""

    # scoring debug fields
    is_manual: bool = False
    pinned: bool = False
    manual_priority: int = Field(default=0, ge=0, le=5)

    algorithm_score: float = 0.0
    agent_score: Optional[float] = None
    final_score: Optional[float] = None

    score_breakdown: Dict[str, float] = Field(default_factory=dict)
    agent_reason: str = ""
    tags: str = ""
    section_tags: str = ""
    merged_candidate_count: int = 1

    @classmethod
    def from_candidate(
        cls,
        candidate: UrlCandidate,
        canonical_url: str,
        parent_url: str = "",
        inherited_from_url_id: str = "",
    ) -> "UrlQueueItem":
        return cls(
            url_id=sha256_text(canonical_url)[:16],
            canonical_url=canonical_url,
            original_url=candidate.url,
            parent_url=parent_url,
            title=candidate.title,
            snippet=candidate.snippet,
            section=candidate.section,
            source_type=candidate.source_type,
            source_name=candidate.source_name,
            publish_date=candidate.publish_date,
            priority=candidate.priority,
            discovered_by=candidate.discovered_by,
            query=candidate.query,
            confidence=candidate.confidence,
            inherited_from_url_id=inherited_from_url_id,
            is_manual=candidate.is_manual,
            pinned=candidate.pinned,
            manual_priority=candidate.manual_priority,
            algorithm_score=candidate.algorithm_score,
            agent_score=candidate.agent_score,
            final_score=candidate.final_score,
            score_breakdown=candidate.score_breakdown,
            agent_reason=candidate.agent_reason,
            tags=candidate.tags,
            section_tags=candidate.section_tags,
            merged_candidate_count=candidate.merged_candidate_count,
        )

    @field_validator("canonical_url", "original_url")
    @classmethod
    def _validate_urls(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("parent_url")
    @classmethod
    def _validate_parent_url(cls, v: str) -> str:
        if not v:
            return ""
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_publish_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)

    @model_validator(mode="after")
    def _fill_publish_date_int(self) -> "UrlQueueItem":
        # 使用 object.__setattr__ 避免 validate_assignment=True 导致的无限递归
        object.__setattr__(self, 'publish_date_int', date_to_int(self.publish_date))
        return self

# =========================
# Browser Fetch Layer
# =========================

class FetchResult(StrictModel):
    """
    Browser Worker 输出。
    该对象只描述“抓到了什么、保存在哪里”，不做业务判断。
    """
    url_id: str

    original_url: str
    canonical_url: str
    final_url: str = ""

    parent_url: str = ""

    section: SectionType
    source_type: SourceType = SourceType.UNKNOWN
    source_name: str = ""
    publish_date: Optional[str] = None
    publish_date_int: int = 0

    status: FetchStatus
    http_status: Optional[int] = None
    content_type: str = ""
    file_ext: str = ""

    title: str = ""

    raw_html_path: str = ""
    official_pdf_path: str = ""
    print_pdf_path: str = ""
    screenshot_path: str = ""
    metadata_path: str = ""

    error: str = ""
    fetched_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    @field_validator("original_url", "canonical_url")
    @classmethod
    def _validate_urls(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("final_url", "parent_url")
    @classmethod
    def _validate_optional_urls(cls, v: str) -> str:
        if not v:
            return ""
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_publish_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)

    @model_validator(mode="after")
    def _fill_publish_date_int(self) -> "FetchResult":
        object.__setattr__(self, 'publish_date_int', date_to_int(self.publish_date))
        return self

    @property
    def is_pdf(self) -> bool:
        return (
            "application/pdf" in self.content_type.lower()
            or self.file_ext.lower() == ".pdf"
            or self.official_pdf_path.endswith(".pdf")
        )

    @property
    def is_html(self) -> bool:
        return (
            "text/html" in self.content_type.lower()
            or self.file_ext.lower() in [".html", ".htm"]
            or bool(self.raw_html_path)
        )


class DiscoveredPdfLink(StrictModel):
    """
    HTML 页面中发现的 PDF 附件。
    建议重新写入 URL Queue，而不是直接送 MinerU。
    """
    url: str
    parent_url: str
    parent_url_id: str

    anchor_text: str = ""

    section: SectionType
    source_type: SourceType = SourceType.UNKNOWN
    source_name: str = ""
    publish_date: Optional[str] = None

    confidence: float = Field(default=0.6, ge=0.0, le=1.0)

    @field_validator("url", "parent_url")
    @classmethod
    def _validate_urls(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_publish_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)


# =========================
# Parser Layer
# =========================

class ParsedDoc(StrictModel):
    """
    MinerU 或 HTML Parser 的统一输出。
    后续 Chunker 不需要关心来源是 PDF 还是 HTML。
    """
    doc_id: str
    url_id: str

    source_url: str
    parent_url: str = ""

    title: str = ""

    section: SectionType
    source_type: SourceType = SourceType.UNKNOWN
    source_name: str = ""
    publish_date: Optional[str] = None
    publish_date_int: int = 0

    parser: ParserType
    status: ParseStatus = ParseStatus.SUCCESS

    markdown_path: str = ""
    json_path: str = ""

    text_length: int = 0

    discovered_pdf_urls: List[str] = Field(default_factory=list)
    error: str = ""

    @field_validator("source_url")
    @classmethod
    def _validate_source_url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("parent_url")
    @classmethod
    def _validate_parent_url(cls, v: str) -> str:
        if not v:
            return ""
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_publish_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)

    @model_validator(mode="after")
    def _fill_publish_date_int(self) -> "ParsedDoc":
        object.__setattr__(self, 'publish_date_int', date_to_int(self.publish_date))
        return self


# =========================
# Chunk / Chroma Layer
# =========================

class ChunkMetadata(StrictModel):
    """
    Chroma metadata 必须尽量保持扁平。
    不建议把 list/dict 放进 metadata。
    """
    run_id: str

    section: SectionType
    source_type: SourceType = SourceType.UNKNOWN

    source_url: str
    parent_url: str = ""

    title: str = ""
    source_name: str = ""

    publish_date: Optional[str] = None
    publish_date_int: int = 0

    company: str = ""
    peer_company: str = ""

    industry: str = ""
    esg_dim: ESGDimension = ESGDimension.UNKNOWN

    parser: ParserType

    doc_id: str
    chunk_index: int = 0

    authority_score: float = Field(default=0.5, ge=0.0, le=1.0)

    # 用字符串承载 tags，避免 Chroma metadata 不支持复杂对象
    tags: str = ""

    @field_validator("source_url")
    @classmethod
    def _validate_source_url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("parent_url")
    @classmethod
    def _validate_parent_url(cls, v: str) -> str:
        if not v:
            return ""
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_publish_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)

    @model_validator(mode="after")
    def _fill_publish_date_int(self) -> "ChunkMetadata":
        object.__setattr__(self, 'publish_date_int', date_to_int(self.publish_date))
        return self


class ChunkItem(StrictModel):
    """
    最终写入 Chroma 的最小单元。
    """
    chunk_id: str
    doc_id: str
    text: str = Field(min_length=20)
    metadata: ChunkMetadata

    @classmethod
    def create(
        cls,
        doc_id: str,
        text: str,
        metadata: ChunkMetadata,
    ) -> "ChunkItem":
        """
        工厂方法：创建 ChunkItem
        自动生成 chunk_id（基于内容 hash）
        """
        chunk_id = sha256_text(f"{doc_id}:{metadata.chunk_index}:{text[:100]}")
        return cls(
            chunk_id=chunk_id,
            doc_id=doc_id,
            text=text,
            metadata=metadata,
        )

    def to_chroma(self) -> Dict[str, Any]:
        """
        转换为 Chroma add() 可直接使用的格式

        Returns:
            {
                "id": str,           # chunk_id
                "document": str,     # text
                "metadata": dict,    # 扁平化的 metadata
            }
        """
        return {
            "id": self.chunk_id,
            "document": self.text,
            "metadata": self.metadata.model_dump(mode="json"),
        }


# =========================
# Evidence / Assessment / Report
# =========================

class EvidenceItem(StrictModel):
    """
    从 Chroma 检索出来并整理后的证据包元素。
    LLM 影响评估和报告生成只能基于 EvidenceItem。
    """
    evidence_id: str

    section: SectionType
    chunk_id: str
    doc_id: str

    title: str = ""
    source_url: str
    source_name: str = ""
    source_type: SourceType = SourceType.UNKNOWN
    publish_date: Optional[str] = None

    esg_dim: ESGDimension = ESGDimension.UNKNOWN

    text: str = Field(min_length=20)

    score: float = 0.0
    rank: int = 0
    authority_score: float = Field(default=0.5, ge=0.0, le=1.0)

    relevance_reason: str = ""

    @field_validator("source_url")
    @classmethod
    def _validate_source_url(cls, v: str) -> str:
        return validate_http_url(v)

    @field_validator("publish_date")
    @classmethod
    def _validate_publish_date(cls, v: Optional[str]) -> Optional[str]:
        return ensure_date_str(v)


class ESGImpactAssessment(StrictModel):
    """
    Impact Assessment Agent 的强约束输出。
    用这个 schema 约束 LLM，不要让模型散写。
    """
    assessment_id: str

    related_evidence_ids: List[str] = Field(min_length=1)

    subject: str
    subject_type: SectionType
    event_summary: str

    esg_dimension: ESGDimension
    impact_direction: ImpactDirection
    materiality: Materiality

    risk: str
    opportunity: str
    recommendation: str

    action_owner: ActionOwner = ActionOwner.UNKNOWN

    confidence: float = Field(ge=0.0, le=1.0)
    caveat: str = ""

class ReportBundle(StrictModel):
    """
    最终导出的报告包。
    """
    run_id: str
    company: str
    period_start: str
    period_end: str

    report_markdown: str
    output_path: str = ""

    evidence_path: str = ""
    assessment_path: str = ""

    evidence_count: int = 0
    assessment_count: int = 0

    @field_validator("period_start", "period_end")
    @classmethod
    def _validate_date(cls, v: str) -> str:
        return ensure_date_str(v) or ""


# =========================
# LangGraph State
# =========================

class ESGDemoState(TypedDict, total=False):
    """
    LangGraph 主状态。
    建议在 State 中存 dict，而不是 Pydantic 对象，
    节点内部用 Model.model_validate() 做校验。
    """

    messages: Annotated[List[BaseMessage], add_messages]

    # run context
    run_id: str
    company: str
    anchor_date: str
    period_start: str
    period_end: str
    run_paths: Dict[str, Any]

    chroma_path: str
    collection_name: str

    # discovery
    company_profile: Dict[str, Any]

    # search planning
    search_tasks: List[Dict[str, Any]]

    # 并行 Search Agent 结果，使用 operator.add 合并
    url_candidates: Annotated[List[Dict[str, Any]], operator.add]

    # normalized queue
    url_queue: List[Dict[str, Any]]

    # browser worker outputs
    fetched_docs: List[Dict[str, Any]]

    # parser outputs
    parsed_docs: List[Dict[str, Any]]
    discovered_pdf_urls: List[Dict[str, Any]]

    # chunk/index
    chunks: List[Dict[str, Any]]

    # retrieval
    evidence_pack: List[Dict[str, Any]]

    # LLM assessment
    impact_assessments: List[Dict[str, Any]]

    # report
    report_markdown: str
    output_paths: Dict[str, str]

    # debug / metrics
    errors: Annotated[List[Dict[str, Any]], operator.add]
    metrics: Dict[str, Any]
