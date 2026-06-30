# agents/company_discovery.py
from __future__ import annotations

from config import COMPANY_CONFIG
from schemas import CompanyProfile


def discover_company(company: str) -> dict:
    """
    Project profile is configured locally for reproducible runs.
    The same interface can be backed by filings, company sites, or industry datasets.
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
