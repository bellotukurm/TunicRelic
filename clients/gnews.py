import os

import requests

from config.app_config import AppConfigError, get_gnews_base_url

GNEWS_API_KEY_NAME = "GNEWS_API_KEY"
TIMEOUT_SECONDS = 15


class GNewsClientError(Exception):
    """Raised when the GNews API cannot be used successfully."""


class GNewsClient:
    """Small synchronous client for GNews search requests."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
    ):
        self.api_key = self._resolve_required_value(api_key, GNEWS_API_KEY_NAME)
        try:
            resolved_base_url = base_url or get_gnews_base_url()
        except AppConfigError as exc:
            raise GNewsClientError(str(exc)) from exc
        self.base_url = resolved_base_url.rstrip("/")

    def _resolve_required_value(
        self,
        provided_value: str | None,
        env_name: str,
    ) -> str:
        value = provided_value or os.getenv(env_name)
        if not value:
            raise GNewsClientError(f"Missing environment variable: {env_name}")
        return value

    def _quote_alias(self, alias: str) -> str:
        return f"\"{alias.replace('\"', '\\\"')}\""

    def search_news(self, alias: str) -> dict:
        alias = alias.strip()
        if not alias:
            raise GNewsClientError("alias is required")

        url = f"{self.base_url}/search"
        headers = {
            "X-Api-Key": self.api_key,
        }
        params = {
            "q": self._quote_alias(alias),
        }

        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise GNewsClientError(f"Request to GNews failed: {exc}") from exc

        if response.status_code == 401:
            raise GNewsClientError("Unauthorized. Check your GNews API key.")

        if response.status_code == 403:
            raise GNewsClientError("Forbidden. GNews rejected the request.")

        if response.status_code == 429:
            raise GNewsClientError("Rate limited by GNews. Try again later.")

        if not response.ok:
            raise GNewsClientError(
                f"GNews request failed: {response.status_code} {response.text}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise GNewsClientError("GNews response was not valid JSON.") from exc
