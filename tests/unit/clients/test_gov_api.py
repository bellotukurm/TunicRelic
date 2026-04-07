import pytest
import requests

import clients.gov_api as gov_api_module
from clients.gov_api import COMPANIES_HOUSE_API_KEY_NAME, GovApiCompanyResolver
from services.company_resolver import CompanyResolverError


def test_get_api_key_fails_when_env_var_is_missing():
    with pytest.raises(
        gov_api_module._GovApiError,
        match=f"Missing environment variable: {COMPANIES_HOUSE_API_KEY_NAME}",
    ):
        gov_api_module._get_api_key()


def test_build_section_returns_expected_shape():
    assert gov_api_module._build_section([{"item": 1}], 3, "boom") == {
        "items": [{"item": 1}],
        "total_count": 3,
        "error": "boom",
    }


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"total_count": 4, "total_results": 2}, 4),
        ({"total_results": 2}, 2),
        ({}, None),
    ],
)
def test_extract_total_count_prefers_total_count_then_total_results(payload: dict, expected):
    assert gov_api_module._extract_total_count(payload) == expected


@pytest.mark.parametrize(
    ("officer", "expected"),
    [
        (
            {"links": {"officer": {"appointments": "/officers/abc123/appointments"}}},
            "abc123",
        ),
        ({"links": {"officer": {}}}, None),
        (
            {"links": {"officer": {"appointments": "/officers/abc123"}}},
            None,
        ),
    ],
)
def test_extract_officer_id_handles_valid_and_invalid_links(officer: dict, expected):
    assert gov_api_module._extract_officer_id(officer) == expected


def test_get_sends_expected_request(monkeypatch: pytest.MonkeyPatch, response_factory):
    captured = {}

    def fake_get(url, params, auth, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["auth"] = auth
        captured["timeout"] = timeout
        return response_factory(json_data={"company_name": "Acme"})

    monkeypatch.setenv(COMPANIES_HOUSE_API_KEY_NAME, "key")
    monkeypatch.setattr(gov_api_module.requests, "get", fake_get)

    result = gov_api_module._get("/company/123", params={"items_per_page": 5})

    assert result == {"company_name": "Acme"}
    assert captured["url"] == f"{gov_api_module.BASE_URL}/company/123"
    assert captured["params"] == {"items_per_page": 5}
    assert captured["auth"] == ("key", "")
    assert captured["timeout"] == gov_api_module.TIMEOUT_SECONDS


def test_get_translates_request_exceptions(monkeypatch: pytest.MonkeyPatch):
    def raise_request_error(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setenv(COMPANIES_HOUSE_API_KEY_NAME, "key")
    monkeypatch.setattr(gov_api_module.requests, "get", raise_request_error)

    with pytest.raises(
        gov_api_module._GovApiError,
        match="Request to Companies House failed: network down",
    ):
        gov_api_module._get("/company/123")


@pytest.mark.parametrize(
    ("status_code", "text", "message"),
    [
        (401, "unauthorized", "Unauthorized. Check your Companies House API key."),
        (404, "missing", "Company not found."),
        (500, "server error", "Companies House request failed: 500 server error"),
    ],
)
def test_get_translates_http_errors(
    monkeypatch: pytest.MonkeyPatch,
    response_factory,
    status_code: int,
    text: str,
    message: str,
):
    monkeypatch.setenv(COMPANIES_HOUSE_API_KEY_NAME, "key")
    monkeypatch.setattr(
        gov_api_module.requests,
        "get",
        lambda *args, **kwargs: response_factory(status_code=status_code, text=text),
    )

    with pytest.raises(gov_api_module._GovApiError, match=message):
        gov_api_module._get("/company/123")


def test_search_by_name_returns_empty_list_for_blank_input():
    resolver = GovApiCompanyResolver()

    assert resolver.search_by_name("   ") == []


def test_search_by_name_maps_api_items(monkeypatch: pytest.MonkeyPatch):
    resolver = GovApiCompanyResolver()
    monkeypatch.setattr(
        gov_api_module,
        "_get",
        lambda path, params=None: {
            "items": [
                {
                    "title": "Acme Ltd",
                    "company_number": "12345678",
                    "jurisdiction": "england-wales",
                    "company_status": "active",
                    "company_type": "ltd",
                }
            ]
        },
    )

    result = resolver.search_by_name("Acme")

    assert result == [
        {
            "company_name": "Acme Ltd",
            "registration_number": "12345678",
            "jurisdiction": "england-wales",
            "company_status": "active",
            "company_type": "ltd",
        }
    ]


def test_search_by_name_translates_gov_api_errors(monkeypatch: pytest.MonkeyPatch):
    resolver = GovApiCompanyResolver()

    def raise_gov_api_error(path, params=None):
        raise gov_api_module._GovApiError("boom")

    monkeypatch.setattr(gov_api_module, "_get", raise_gov_api_error)

    with pytest.raises(CompanyResolverError, match="boom"):
        resolver.search_by_name("Acme")


def test_resolve_by_registration_number_rejects_blank_input():
    resolver = GovApiCompanyResolver()

    with pytest.raises(CompanyResolverError, match="Registration number is required."):
        resolver.resolve_by_registration_number("   ")


def test_resolve_by_registration_number_assembles_company_details(monkeypatch: pytest.MonkeyPatch):
    resolver = GovApiCompanyResolver()

    def fake_get(path, params=None):
        if path == "/company/12345678":
            return {"company_number": "12345678", "company_name": "Acme Ltd"}
        if path == "/company/12345678/filing-history":
            return {"items": [{"type": "AA"}], "total_count": 1}
        if path == "/company/12345678/officers":
            return {
                "items": [
                    {
                        "name": "Jane Director",
                        "officer_role": "director",
                        "appointed_on": "2020-01-01",
                        "links": {
                            "officer": {
                                "appointments": "/officers/abc123/appointments"
                            }
                        },
                    },
                    {
                        "name": "Sam Secretary",
                        "officer_role": "secretary",
                    },
                ],
                "total_results": 2,
            }
        if path == "/officers/abc123/appointments":
            return {"items": [{"appointed_to": {"company_number": "99999999"}}], "total_count": 1}
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(gov_api_module, "_get", fake_get)

    result = resolver.resolve_by_registration_number("12345678")

    assert result["registration_number"] == "12345678"
    assert result["company_name"] == "Acme Ltd"
    assert result["filing_history"] == {
        "items": [{"type": "AA"}],
        "total_count": 1,
        "error": None,
    }
    assert result["officers"]["total_count"] == 2
    assert result["director_appointments"]["total_count"] == 1
    assert result["director_appointments"]["items"] == [
        {
            "officer_name": "Jane Director",
            "officer_role": "director",
            "appointed_on": "2020-01-01",
            "officer_id": "abc123",
            "appointments": {
                "items": [{"appointed_to": {"company_number": "99999999"}}],
                "total_count": 1,
                "error": None,
            },
        }
    ]


def test_resolve_by_registration_number_captures_filing_history_and_appointment_errors(
    monkeypatch: pytest.MonkeyPatch,
):
    resolver = GovApiCompanyResolver()

    def fake_get(path, params=None):
        if path == "/company/12345678":
            return {"company_number": "12345678", "company_name": "Acme Ltd"}
        if path == "/company/12345678/filing-history":
            raise gov_api_module._GovApiError("filing history unavailable")
        if path == "/company/12345678/officers":
            return {
                "items": [
                    {
                        "name": "Jane Director",
                        "officer_role": "director",
                        "appointed_on": "2020-01-01",
                        "links": {
                            "officer": {
                                "appointments": "/officers/abc123/appointments"
                            }
                        },
                    }
                ]
            }
        if path == "/officers/abc123/appointments":
            raise gov_api_module._GovApiError("appointments unavailable")
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(gov_api_module, "_get", fake_get)

    result = resolver.resolve_by_registration_number("12345678")

    assert result["filing_history"] == {
        "items": [],
        "total_count": None,
        "error": "filing history unavailable",
    }
    assert result["director_appointments"]["items"][0]["appointments"] == {
        "items": [],
        "total_count": None,
        "error": "appointments unavailable",
    }


def test_resolve_by_registration_number_captures_officer_errors(monkeypatch: pytest.MonkeyPatch):
    resolver = GovApiCompanyResolver()

    def fake_get(path, params=None):
        if path == "/company/12345678":
            return {"company_number": "12345678", "company_name": "Acme Ltd"}
        if path == "/company/12345678/filing-history":
            return {"items": [], "total_count": 0}
        if path == "/company/12345678/officers":
            raise gov_api_module._GovApiError("officers unavailable")
        raise AssertionError(f"Unexpected path {path}")

    monkeypatch.setattr(gov_api_module, "_get", fake_get)

    result = resolver.resolve_by_registration_number("12345678")

    assert result["officers"] == {
        "items": [],
        "total_count": None,
        "error": "officers unavailable",
    }
    assert result["director_appointments"] == {
        "items": [],
        "total_count": 0,
        "error": "Officers could not be loaded, so director appointments are unavailable.",
    }


def test_fetch_director_appointments_filters_to_active_directors(monkeypatch: pytest.MonkeyPatch):
    seen = []

    def fake_fetch_appointments_for_director(officer):
        seen.append(officer["name"])
        return {"officer_name": officer["name"]}

    monkeypatch.setattr(
        gov_api_module,
        "_fetch_appointments_for_director",
        fake_fetch_appointments_for_director,
    )

    result = gov_api_module._fetch_director_appointments(
        {
            "items": [
                {"name": "Active Director", "officer_role": "director"},
                {
                    "name": "Resigned Director",
                    "officer_role": "director",
                    "resigned_on": "2022-01-01",
                },
                {"name": "Secretary", "officer_role": "secretary"},
            ]
        }
    )

    assert seen == ["Active Director"]
    assert result == {
        "items": [{"officer_name": "Active Director"}],
        "total_count": 1,
        "error": None,
    }


def test_fetch_appointments_for_director_returns_fallback_when_link_is_missing():
    result = gov_api_module._fetch_appointments_for_director(
        {
            "name": "Jane Director",
            "officer_role": "director",
            "appointed_on": "2020-01-01",
        }
    )

    assert result == {
        "officer_name": "Jane Director",
        "officer_role": "director",
        "appointed_on": "2020-01-01",
        "officer_id": None,
        "appointments": {
            "items": [],
            "total_count": None,
            "error": "Officer appointments link was not available.",
        },
    }
