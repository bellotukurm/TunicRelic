import json
import os
from typing import Any

import requests
from jsonschema import Draft202012Validator, ValidationError

from app_config import AppConfigError, get_openrouter_default_model

OPENROUTER_API_KEY_NAME = "OPENROUTER_API_KEY"
OPENROUTER_BASE_URL_NAME = "OPENROUTER_BASE_URL"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 30


class OpenRouterClientError(Exception):
    """Raised when OpenRouter cannot be used successfully."""


class OpenRouterClient:
    """Small synchronous client for structured OpenRouter completions."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = self._resolve_required_value(
            api_key,
            OPENROUTER_API_KEY_NAME,
        )
        try:
            self.default_model = default_model or get_openrouter_default_model()
        except AppConfigError as exc:
            raise OpenRouterClientError(str(exc)) from exc
        self.base_url = (
            base_url
            or os.getenv(OPENROUTER_BASE_URL_NAME)
            or DEFAULT_OPENROUTER_BASE_URL
        ).rstrip("/")

    def _resolve_required_value(
        self,
        provided_value: str | None,
        env_name: str,
    ) -> str:
        value = provided_value or os.getenv(env_name)
        if not value:
            raise OpenRouterClientError(f"Missing environment variable: {env_name}")
        return value

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise OpenRouterClientError(f"Request to OpenRouter failed: {exc}") from exc

        if response.status_code == 401:
            raise OpenRouterClientError("Unauthorized. Check your OpenRouter API key.")

        if not response.ok:
            raise OpenRouterClientError(
                f"OpenRouter request failed: {response.status_code} {response.text}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise OpenRouterClientError(
                "OpenRouter response was not valid JSON."
            ) from exc

    def _extract_content(self, response_data: dict[str, Any]) -> str | dict[str, Any]:
        choices = response_data.get("choices", [])
        if not choices:
            raise OpenRouterClientError("OpenRouter response did not include any choices.")

        message = choices[0].get("message", {})
        content = message.get("content")
        if isinstance(content, dict):
            return content

        if isinstance(content, str) and content.strip():
            return content

        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    text_parts.append(part["text"])

            joined = "".join(text_parts).strip()
            if joined:
                return joined

        raise OpenRouterClientError(
            "OpenRouter response did not include assistant content."
        )

    def create_structured_completion(
        self,
        messages: list[dict[str, str]],
        json_schema: dict[str, Any],
        schema_name: str,
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        if not messages:
            raise OpenRouterClientError("messages is required")

        try:
            Draft202012Validator.check_schema(json_schema)
        except Exception as exc:
            raise OpenRouterClientError(f"Invalid JSON schema: {exc}") from exc

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": json_schema,
                },
            },
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        response_data = self._post("/chat/completions", payload)
        content = self._extract_content(response_data)

        if isinstance(content, dict):
            parsed_content = content
        else:
            try:
                parsed_content = json.loads(content)
            except json.JSONDecodeError as exc:
                raise OpenRouterClientError(
                    f"Structured response was not valid JSON: {exc}"
                ) from exc

        try:
            Draft202012Validator(json_schema).validate(parsed_content)
        except ValidationError as exc:
            raise OpenRouterClientError(
                f"Structured response did not match schema: {exc.message}"
            ) from exc

        return parsed_content
