from typing import Any

from clients.gnews import GNewsClient, GNewsClientError


class CompanyNewsServiceError(Exception):
    """Raised when company news cannot be fetched."""


class CompanyNewsService:
    """Service for fetching news for an identified brand or legal name."""

    def __init__(self, client: GNewsClient | None = None):
        self.client = client if client is not None else GNewsClient()

    def fetch_news(self, brand) -> dict[str, Any]:
        try:
            response = self.client.search_news(brand)
        except GNewsClientError as exc:
            raise CompanyNewsServiceError(str(exc)) from exc

        return {
            "query": brand,
            "response": response,
        }
