"""Contracts and factory for company resolution services."""

from abc import ABC, abstractmethod


class CompanyResolverError(Exception):
    """Raised when company resolution cannot be completed."""


class CompanyResolver(ABC):
    """Stable interface for resolving company details."""

    @abstractmethod
    def search_by_name(self, company_name: str) -> list[dict]:
        """Return candidate companies for the supplied company name."""

    @abstractmethod
    def resolve_by_registration_number(self, registration_number: str) -> dict:
        """Return a company record for the supplied registration number."""


def get_company_resolver() -> CompanyResolver:
    """Return the default company resolver implementation."""
    from clients.gov_api import GovApiCompanyResolver

    return GovApiCompanyResolver()
