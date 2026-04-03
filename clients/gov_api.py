import os
import re

import requests

from services.company_resolver import CompanyResolver, CompanyResolverError

COMPANIES_HOUSE_API_KEY_NAME = "COMPANIES_HOUSE_API_KEY"
BASE_URL = "https://api.company-information.service.gov.uk"
TIMEOUT_SECONDS = 15
FILING_HISTORY_ITEMS_LIMIT = 25
OFFICERS_ITEMS_LIMIT = 100
APPOINTMENTS_ITEMS_LIMIT = 25


class _GovApiError(Exception):
    """Raised when the Companies House API cannot be used successfully."""


def _build_section(items: list[dict], total_count: int | None, error: str | None = None) -> dict:
    return {
        "items": items,
        "total_count": total_count,
        "error": error,
    }


def _get_api_key() -> str:
    api_key = os.getenv(COMPANIES_HOUSE_API_KEY_NAME)
    if not api_key:
        raise _GovApiError(
            f"Missing environment variable: {COMPANIES_HOUSE_API_KEY_NAME}"
        )
    return api_key


def _get(path: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"

    try:
        response = requests.get(
            url,
            params=params,
            auth=(_get_api_key(), ""),
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise _GovApiError(f"Request to Companies House failed: {exc}") from exc

    if response.status_code == 401:
        raise _GovApiError("Unauthorized. Check your Companies House API key.")

    if response.status_code == 404:
        raise _GovApiError("Company not found.")

    if not response.ok:
        raise _GovApiError(
            f"Companies House request failed: {response.status_code} {response.text}"
        )

    return response.json()


def _extract_total_count(data: dict) -> int | None:
    return data.get("total_count", data.get("total_results"))


def _extract_officer_id(officer: dict) -> str | None:
    appointments_path = (
        officer.get("links", {})
        .get("officer", {})
        .get("appointments")
    )

    if not appointments_path:
        return None

    match = re.search(r"/officers/([^/]+)/appointments", appointments_path)
    if not match:
        return None

    return match.group(1)


def _fetch_filing_history(company_number: str) -> dict:
    try:
        data = _get(
            f"/company/{company_number}/filing-history",
            params={"items_per_page": FILING_HISTORY_ITEMS_LIMIT},
        )
    except _GovApiError as exc:
        return _build_section([], None, str(exc))

    return _build_section(
        data.get("items", []),
        _extract_total_count(data),
    )


def _fetch_officers(company_number: str) -> dict:
    try:
        data = _get(
            f"/company/{company_number}/officers",
            params={"items_per_page": OFFICERS_ITEMS_LIMIT},
        )
    except _GovApiError as exc:
        return _build_section([], None, str(exc))

    return _build_section(
        data.get("items", []),
        _extract_total_count(data),
    )


def _fetch_appointments_for_director(officer: dict) -> dict:
    officer_id = _extract_officer_id(officer)
    if not officer_id:
        return {
            "officer_name": officer.get("name"),
            "officer_role": officer.get("officer_role"),
            "appointed_on": officer.get("appointed_on"),
            "officer_id": None,
            "appointments": _build_section(
                [],
                None,
                "Officer appointments link was not available.",
            ),
        }

    try:
        data = _get(
            f"/officers/{officer_id}/appointments",
            params={
                "items_per_page": APPOINTMENTS_ITEMS_LIMIT,
                "filter": "active",
            },
        )
    except _GovApiError as exc:
        appointments = _build_section([], None, str(exc))
    else:
        appointments = _build_section(
            data.get("items", []),
            _extract_total_count(data),
        )

    return {
        "officer_name": officer.get("name"),
        "officer_role": officer.get("officer_role"),
        "appointed_on": officer.get("appointed_on"),
        "officer_id": officer_id,
        "appointments": appointments,
    }


def _fetch_director_appointments(officers_section: dict) -> dict:
    if officers_section.get("error"):
        return _build_section(
            [],
            0,
            "Officers could not be loaded, so director appointments are unavailable.",
        )

    active_directors = [
        officer
        for officer in officers_section.get("items", [])
        if officer.get("officer_role") == "director" and not officer.get("resigned_on")
    ]

    items = [_fetch_appointments_for_director(officer) for officer in active_directors]
    return _build_section(items, len(active_directors))


class GovApiCompanyResolver(CompanyResolver):
    """Companies House-backed resolver implementation."""

    def search_by_name(self, company_name: str) -> list[dict]:
        company_name = company_name.strip()
        if not company_name:
            return []

        try:
            data = _get(
                "/search/companies",
                params={
                    "q": company_name,
                    "items_per_page": 20,
                },
            )
        except _GovApiError as exc:
            raise CompanyResolverError(str(exc)) from exc

        results = []
        for item in data.get("items", []):
            results.append(
                {
                    "company_name": item.get("title"),
                    "registration_number": item.get("company_number"),
                    "jurisdiction": "GB",
                    "company_status": item.get("company_status"),
                    "company_type": item.get("company_type"),
                }
            )

        return results

    def resolve_by_registration_number(self, registration_number: str) -> dict:
        registration_number = registration_number.strip()
        if not registration_number:
            raise CompanyResolverError("Registration number is required.")

        try:
            profile = _get(f"/company/{registration_number}")
        except _GovApiError as exc:
            raise CompanyResolverError(str(exc)) from exc

        company_number = profile.get("company_number", registration_number)
        filing_history = _fetch_filing_history(company_number)
        officers = _fetch_officers(company_number)
        director_appointments = _fetch_director_appointments(officers)

        detailed_company = dict(profile)
        detailed_company["registration_number"] = company_number
        detailed_company["filing_history"] = filing_history
        detailed_company["officers"] = officers
        detailed_company["director_appointments"] = director_appointments

        return detailed_company

