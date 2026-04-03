import json
from typing import Any

from clients.openrouter import OpenRouterClient, OpenRouterClientError

COMPANY_ALIAS_SCHEMA = {
    "type": "object",
    "properties": {
        "news_aliases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "alias": {
                        "type": "string",
                        "minLength": 1,
                        "description": "A company alias likely to appear in news or reports.",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Confidence score between 0 and 1.",
                    },
                    "reason": {
                        "type": "string",
                        "minLength": 1,
                        "description": "Short reason why this alias is plausible.",
                    },
                },
                "required": ["alias", "confidence", "reason"],
                "additionalProperties": False,
            },
            "description": "Likely aliases used in news, press, or scam reports.",
            "maxItems": 10,
        }
    },
    "required": ["news_aliases"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You generate company aliases for news, press, scam reports, and adverse mentions.
Use only aliases supported by the provided data.
Prefer trading names, brand names, legal names, previous names, and domain-derived names that are genuinely plausible.
Do not invent unsupported abbreviations, subsidiaries, or unrelated entities.
Return high-signal aliases only and keep reasons short."""


class CompanyAliasServiceError(Exception):
    """Raised when company aliases cannot be generated."""


class CompanyAliasService:
    """Service for generating likely news aliases for a company."""

    def __init__(self, client: OpenRouterClient | None = None):
        self.client = client if client is not None else OpenRouterClient()

    def _normalize_company_input(self, company_input: dict[str, Any]) -> dict[str, Any]:
        legal_name = str(company_input.get("legal_name", "")).strip()
        if not legal_name:
            raise CompanyAliasServiceError("legal_name is required")

        previous_names = company_input.get("previous_names") or []
        if not isinstance(previous_names, list):
            raise CompanyAliasServiceError("previous_names must be a list")

        normalized_previous_names = [
            str(name).strip()
            for name in previous_names
            if str(name).strip()
        ]

        def _optional_string(field_name: str) -> str | None:
            value = company_input.get(field_name)
            if value is None:
                return None

            stripped = str(value).strip()
            return stripped or None

        return {
            "legal_name": legal_name,
            "registration_number": _optional_string("registration_number"),
            "domain": _optional_string("domain"),
            "previous_names": normalized_previous_names,
            "country": _optional_string("country"),
        }

    def generate_news_aliases(self, company_input: dict[str, Any]) -> dict[str, Any]:
        normalized_input = self._normalize_company_input(company_input)
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "Generate likely public-facing aliases for this company. "
                    "Sort aliases by confidence descending and include the legal name when useful.\n\n"
                    f"Company data:\n{json.dumps(normalized_input, indent=2)}"
                ),
            },
        ]

        try:
            return self.client.create_structured_completion(
                messages=messages,
                json_schema=COMPANY_ALIAS_SCHEMA,
                schema_name="company_news_aliases",
                temperature=0,
            )
        except OpenRouterClientError as exc:
            raise CompanyAliasServiceError(str(exc)) from exc
