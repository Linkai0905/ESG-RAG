# config.py
from __future__ import annotations

import os
import re
from pathlib import Path
from datetime import date
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env", override=True)


# =========================
# Basic Settings
# =========================

RUNS_DIR = PROJECT_ROOT / "runs"

DEFAULT_COMPANY = "中国神华"
DEFAULT_ANCHOR_DATE = "2026-06-29"

SEARCH_PROVIDER = os.getenv("SEARCH_PROVIDER", "manual")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY", "")
MANUAL_SOURCES_PATH = os.getenv("MANUAL_SOURCES_PATH", "manual_sources.csv")
USE_AGENT_RERANK = os.getenv("USE_AGENT_RERANK", "false").lower() == "true"

MINERU_CMD = os.getenv("MINERU_CMD", "mineru")


# =========================
# LLM: DeepSeek / OpenAI-compatible
# =========================

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-pro")

LLM_THINKING = os.getenv("LLM_THINKING", "enabled")  # enabled / disabled
LLM_REASONING_EFFORT = os.getenv("LLM_REASONING_EFFORT", "high")  # high / max
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "8192"))


# =========================
# Embedding: generic OpenAI-compatible
# =========================

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "openai_compatible")

EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_BASE_URL = os.getenv(
    "EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 不写死任何 embedding model
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")

# 可选。某些 embedding 服务支持 dimensions，某些不支持。
_raw_embedding_dim = os.getenv("EMBEDDING_DIM", "").strip()
EMBEDDING_DIM = int(_raw_embedding_dim) if _raw_embedding_dim else None

EMBEDDING_PASS_DIMENSIONS = (
    os.getenv("EMBEDDING_PASS_DIMENSIONS", "false").lower() == "true"
)

EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "10"))
EMBEDDING_ENCODING_FORMAT = os.getenv("EMBEDDING_ENCODING_FORMAT", "float")

CHROMA_DISTANCE = os.getenv("CHROMA_DISTANCE", "cosine")


# =========================
# Company Config
# =========================

COMPANY_CONFIG = {
    "company": "中国神华",
    "aliases": [
        "中国神华",
        "神华能源",
        "China Shenhua",
        "601088",
        "01088",
        "国家能源集团",
    ],
    "industries": [
        "煤炭",
        "火电",
        "能源",
        "运输",
        "港口",
        "煤化工",
    ],
    "stock_codes": [
        "601088",
        "01088",
    ],
    "peer_companies": [
        "中国中煤能源",
        "陕西煤业",
        "兖矿能源",
        "华能国际",
        "华电国际",
        "华润电力",
    ],
}


# =========================
# Query Templates
# =========================

POLICY_QUERIES = [
    "ESG 披露 指引 可持续发展报告 气候披露 上市公司 2026",
    "ESG 评级 煤炭 电力 能源 2026",
    "碳排放 碳市场 绿色低碳 政策 2026",
    "生态环境部 煤电 碳排放 ESG 2026",
    "交易所 可持续发展 披露 指引 2026",
]

INDUSTRY_QUERIES = [
    "煤炭行业 ESG 绿色矿山 安全生产 2026",
    "电力行业 火电 低碳转型 ESG 2026",
    "煤电 CCUS 甲烷治理 生态修复 2026",
    "能源央企 ESG 最佳实践 2026",
    "煤炭企业 可持续发展 最佳实践 2026",
]

COMPANY_QUERIES = [
    "中国神华 ESG 2026",
    "中国神华 公告 2026",
    "中国神华 安全生产 环保 2026",
    "中国神华 低碳 绿色矿山 2026",
    "国家能源集团 中国神华 ESG 2026",
]

PEER_QUERIES = [
    "中国中煤能源 ESG 低碳 安全生产 2026",
    "陕西煤业 ESG 绿色矿山 2026",
    "兖矿能源 ESG 可持续发展 2026",
    "华能国际 ESG 火电 低碳 2026",
    "华电国际 ESG 碳排放 2026",
    "华润电力 ESG 可持续发展 2026",
]

SECTION_QUERIES = {
    "policy": POLICY_QUERIES,
    "industry": INDUSTRY_QUERIES,
    "company": COMPANY_QUERIES,
    "peer": PEER_QUERIES,
}

PRESELECT_K = int(os.getenv("PRESELECT_K", "20"))
TOP_K_PER_SECTION = int(os.getenv("TOP_K_PER_SECTION", "8"))
MIN_ONLINE_URLS_PER_SECTION = int(os.getenv("MIN_ONLINE_URLS_PER_SECTION", "0"))
EVIDENCE_TOP_K_PER_SECTION = int(os.getenv("EVIDENCE_TOP_K_PER_SECTION", "8"))
RERANK_ENABLED = os.getenv("RERANK_ENABLED", "true").lower() == "true"
RERANK_MODEL = os.getenv("RERANK_MODEL", LLM_MODEL)
RERANK_PRESELECT_K = int(os.getenv("RERANK_PRESELECT_K", "20"))
RERANK_TOP_K = int(os.getenv("RERANK_TOP_K", "5"))
RERANK_MIN_SCORE = float(os.getenv("RERANK_MIN_SCORE", "3"))
RERANK_MAX_TEXT_CHARS = int(os.getenv("RERANK_MAX_TEXT_CHARS", "900"))
RERANK_SECTIONS = tuple(
    x.strip()
    for x in os.getenv("RERANK_SECTIONS", "company,peer").split(",")
    if x.strip()
)

SECTION_RETRIEVAL_QUERIES = {
    "policy": "ESG政策 评级 标准 披露 气候 碳市场 上市公司",
    "industry": "煤炭 电力 能源 ESG 绿色矿山 安全生产 低碳转型 最佳实践",
    "company": "中国神华 ESG 公告 低碳 环保 安全生产 合规",
    "peer": "对标企业 ESG 低碳 安全生产 绿色矿山 可持续发展",
}


# =========================
# Helpers
# =========================

def calc_period(anchor_date: str) -> tuple[str, str]:
    end_date = date.fromisoformat(anchor_date)
    start_date = end_date - relativedelta(months=1)
    return start_date.isoformat(), end_date.isoformat()


def make_run_id(company: str, anchor_date: str) -> str:
    safe_company = company.replace(" ", "_")
    return f"{anchor_date}_{safe_company}"


def build_run_dirs(run_id: str) -> dict[str, Path]:
    base = RUNS_DIR / run_id

    paths = {
        "base": base,
        "queue": base / "queue",
        "raw": base / "raw",
        "parsed": base / "parsed",
        "meta": base / "meta",
        "chroma": base / "chroma",
        "reports": base / "reports",
    }

    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)

    return paths


def build_search_queries() -> dict[str, list[str]]:
    return {
        "policy": POLICY_QUERIES,
        "industry": INDUSTRY_QUERIES,
        "company": COMPANY_QUERIES,
        "peer": PEER_QUERIES,
    }


def _slug(text: str) -> str:
    text = text or "embedding"
    text = re.sub(r"[^a-zA-Z0-9_\-]+", "_", text)
    return text.strip("_")[:48]


def make_collection_name(
    company: str,
    period_start: str,
    period_end: str,
) -> str:
    """
    把 embedding model 和 dim 放进 collection name，
    避免切换 embedding 后 Chroma 维度冲突。
    """
    company_part = _slug(company)
    model_part = _slug(EMBEDDING_MODEL)
    dim_part = str(EMBEDDING_DIM or "auto")

    return (
        f"esg_{company_part}_"
        f"{period_start.replace('-', '')}_"
        f"{period_end.replace('-', '')}_"
        f"{model_part}_{dim_part}"
    )
