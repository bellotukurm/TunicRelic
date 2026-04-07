import json
from typing import Any

from clients.openrouter import OpenRouterClient, OpenRouterClientError

SYSTEM_PROMPT = """You are doing evidence-based brand identification.

Determine the likely consumer-facing brand name for the legal entity provided.

Rules:
1. Do not guess.
2. First, find evidence that the company trades under a specific consumer-facing name.
3. Prefer official sources over third-party sites.
4. If evidence is insufficient or conflicting, return null.
5. Return JSON only."""

BRAND_IDENTIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "legal_entity": {"type": "string"},
        "brand": {"type": ["string", "null"]},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "url": {"type": "string"},
                    "quote": {"type": "string"}
                },
                "required": ["source", "url", "quote"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["legal_entity", "brand", "evidence"],
    "additionalProperties": False,
}

WEB_SEARCH_TOOL = [
    {
        "type": "openrouter:web_search",
        "parameters": {
            "max_results": 5,
            "max_total_results": 10,
        },
    }
]


class CompanyAliasServiceError(Exception):
    """Raised when brand identification cannot be completed."""


class CompanyAliasService:
    """Minimal wrapper for evidence-based brand identification."""

    def __init__(self, client: OpenRouterClient | None = None):
        self.client = client if client is not None else OpenRouterClient()

    def identify_brand(self, legal_name: str) -> dict[str, Any]:
        legal_name = legal_name.strip()
        if not legal_name:
            raise CompanyAliasServiceError("legal_name is required")

        try:
            raw_result = self.client.create_structured_completion(
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Find the top-level public brand for the legal entity {legal_name}. Return the shortest umbrella/master brand only; do not return division names, business-unit names, or descriptor brands; remove legal suffixes and generic descriptors such as Limited, Ltd, PLC, Inc, LLC, Group, Holdings, Solutions, Services, Technologies, Retail, and Logistics; if the legal entity belongs to a sub-brand like 'X Solutions' but the master public brand is 'X', return 'X'; 'Ocado Solutions' should normalize to 'Ocado'; return JSON only. Include evidence."
                        ),
                    },
                ],
                json_schema=BRAND_IDENTIFICATION_SCHEMA,
                schema_name="brand_identification",
                tools=WEB_SEARCH_TOOL,
            )
        except OpenRouterClientError as exc:
            raise CompanyAliasServiceError(str(exc)) from exc

        return json.loads(raw_result)
