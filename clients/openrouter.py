import os
from typing import Any

import requests

from config.app_config import (
    AppConfigError,
    get_openrouter_base_url,
    get_openrouter_default_model,
)

OPENROUTER_API_KEY_NAME = "OPENROUTER_API_KEY"
TIMEOUT_SECONDS = 30


class OpenRouterClientError(Exception):
    """Raised when OpenRouter cannot be used successfully."""


class OpenRouterClient:
    """Minimal client for structured OpenRouter chat completions."""

    def __init__(
        self,
        api_key: str | None = None,
        default_model: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = api_key or os.getenv(OPENROUTER_API_KEY_NAME)
        if not self.api_key:
            raise OpenRouterClientError(
                f"Missing environment variable: {OPENROUTER_API_KEY_NAME}"
            )

        try:
            self.default_model = default_model or get_openrouter_default_model()
            self.base_url = (base_url or get_openrouter_base_url()).rstrip("/")
        except AppConfigError as exc:
            raise OpenRouterClientError(str(exc)) from exc


    def create_chat_completion(
            self,
            payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not payload.get("messages"):
            raise OpenRouterClientError("payload['messages'] is required")

        final_payload: dict[str, Any] = {
            "model": self.default_model,
            **payload,
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=final_payload,
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
            raise OpenRouterClientError("OpenRouter response was not valid JSON.") from exc


    def create_structured_completion(
        self,
        messages: list[dict[str, str]],
        json_schema: dict[str, Any],
        schema_name: str,
        model: str | None = None,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        if not messages:
            raise OpenRouterClientError("messages is required")

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "stream": False,
            "provider": {
                "require_parameters": True,
            },
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
        if tools is not None:
            payload["tools"] = tools

        response_data = self.create_chat_completion(payload)

        choices = response_data.get("choices", [])
        if not choices:
            raise OpenRouterClientError("OpenRouter response did not include any choices.")

        content = choices[0].get("message", {}).get("content")
        if content:
            return content

        raise OpenRouterClientError(
            "OpenRouter response did not include content."
        )
