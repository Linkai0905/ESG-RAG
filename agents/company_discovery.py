# agents/company_discovery.py
from __future__ import annotations

from config import COMPANY_CONFIG
from schemas import CompanyProfile


def discover_company(company: str) -> dict:
    """
    Demo 阶段写死。
    后续可以改成：搜索公司官网、行业分类、年报、同行企业数据库。
    """
    profile = CompanyProfile(
        company=company,
        aliases=COMPANY_CONFIG["aliases"],
        industries=COMPANY_CONFIG["industries"],
        peer_companies=COMPANY_CONFIG["peer_companies"],
        stock_codes=COMPANY_CONFIG["stock_codes"],
        search_keywords={},
    )

    return profile.model_dump(mode="json")