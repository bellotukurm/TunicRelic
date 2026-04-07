from clients.gov_api import GovApiCompanyResolver
from services.company_resolver import get_company_resolver


def test_get_company_resolver_returns_gov_api_implementation():
    resolver = get_company_resolver()

    assert isinstance(resolver, GovApiCompanyResolver)
