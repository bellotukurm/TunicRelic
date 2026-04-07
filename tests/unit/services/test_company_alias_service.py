import pytest

from clients.openrouter import OpenRouterClientError
from services.company_alias_service import (
    BRAND_IDENTIFICATION_SCHEMA,
    SYSTEM_PROMPT,
    WEB_SEARCH_TOOL,
    CompanyAliasService,
    CompanyAliasServiceError,
)


class StubOpenRouterClient:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []

    def create_structured_output(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def test_identify_brand_rejects_blank_legal_name():
    service = CompanyAliasService(client=StubOpenRouterClient())

    with pytest.raises(CompanyAliasServiceError, match="legal_name is required"):
        service.identify_brand("   ")


def test_identify_brand_sends_expected_request_contract():
    client = StubOpenRouterClient(
        response='{"legal_entity":"Acme Ltd","brand":"Acme","evidence":[]}'
    )
    service = CompanyAliasService(client=client)

    result = service.identify_brand("  Acme Ltd  ")

    assert result == {
        "legal_entity": "Acme Ltd",
        "brand": "Acme",
        "evidence": [],
    }
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["schema_name"] == "brand_identification"
    assert call["json_schema"] == BRAND_IDENTIFICATION_SCHEMA
    assert call["tools"] == WEB_SEARCH_TOOL
    assert call["messages"][0] == {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }
    assert call["messages"][1]["role"] == "user"
    assert "Find the top-level public brand for the legal entity Acme Ltd." in call["messages"][1]["content"]


def test_identify_brand_translates_openrouter_client_errors():
    service = CompanyAliasService(
        client=StubOpenRouterClient(error=OpenRouterClientError("boom"))
    )

    with pytest.raises(CompanyAliasServiceError, match="boom"):
        service.identify_brand("Acme Ltd")


def test_identify_brand_translates_invalid_json():
    service = CompanyAliasService(client=StubOpenRouterClient(response="not json"))

    with pytest.raises(
        CompanyAliasServiceError,
        match="Brand identification response was not valid JSON.",
    ):
        service.identify_brand("Acme Ltd")


def test_identify_brand_returns_parsed_json():
    service = CompanyAliasService(
        client=StubOpenRouterClient(
            response='{"legal_entity":"Acme Ltd","brand":null,"evidence":[]}'
        )
    )

    assert service.identify_brand("Acme Ltd") == {
        "legal_entity": "Acme Ltd",
        "brand": None,
        "evidence": [],
    }
