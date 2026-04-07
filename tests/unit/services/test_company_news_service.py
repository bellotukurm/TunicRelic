import pytest

from clients.gnews import GNewsClientError
from services.company_news_service import CompanyNewsService, CompanyNewsServiceError


class StubGNewsClient:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = []

    def search_news(self, alias: str):
        self.calls.append(alias)
        if self.error is not None:
            raise self.error
        return self.response


def test_fetch_news_returns_query_and_response():
    client = StubGNewsClient(response={"articles": [{"title": "Story"}]})
    service = CompanyNewsService(client=client)

    result = service.fetch_news("Acme")

    assert result == {
        "query": "Acme",
        "response": {"articles": [{"title": "Story"}]},
    }
    assert client.calls == ["Acme"]


def test_fetch_news_translates_client_errors():
    service = CompanyNewsService(
        client=StubGNewsClient(error=GNewsClientError("boom"))
    )

    with pytest.raises(CompanyNewsServiceError, match="boom"):
        service.fetch_news("Acme")
