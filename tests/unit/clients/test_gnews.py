import pytest
import requests

import clients.gnews as gnews_module
from clients.gnews import GNEWS_API_KEY_NAME, GNewsClient, GNewsClientError, TIMEOUT_SECONDS
from config.app_config import AppConfigError


def test_constructor_fails_when_api_key_is_missing():
    with pytest.raises(
        GNewsClientError,
        match=f"Missing environment variable: {GNEWS_API_KEY_NAME}",
    ):
        GNewsClient(base_url="https://gnews.example.com")


def test_constructor_translates_config_lookup_failures(monkeypatch: pytest.MonkeyPatch):
    def raise_config_error():
        raise AppConfigError("bad config")

    monkeypatch.setattr(gnews_module, "get_gnews_base_url", raise_config_error)

    with pytest.raises(GNewsClientError, match="bad config"):
        GNewsClient(api_key="token")


def test_quote_alias_escapes_embedded_quotes():
    client = GNewsClient(api_key="token", base_url="https://gnews.example.com")

    assert client._quote_alias('ACME "Holdings"') == '"ACME \\"Holdings\\""'


def test_search_news_rejects_blank_alias():
    client = GNewsClient(api_key="token", base_url="https://gnews.example.com")

    with pytest.raises(GNewsClientError, match="alias is required"):
        client.search_news("   ")


def test_search_news_sends_expected_request(monkeypatch: pytest.MonkeyPatch, response_factory):
    captured = {}

    def fake_get(url, headers, params, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["params"] = params
        captured["timeout"] = timeout
        return response_factory(json_data={"articles": [{"title": "Story"}]})

    monkeypatch.setattr(gnews_module.requests, "get", fake_get)
    client = GNewsClient(api_key="token", base_url="https://gnews.example.com/")

    result = client.search_news("Acme")

    assert result == {"articles": [{"title": "Story"}]}
    assert captured["url"] == "https://gnews.example.com/search"
    assert captured["headers"] == {"X-Api-Key": "token"}
    assert captured["params"] == {"q": '"Acme"'}
    assert captured["timeout"] == TIMEOUT_SECONDS


def test_search_news_translates_request_exceptions(monkeypatch: pytest.MonkeyPatch):
    def raise_request_error(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr(gnews_module.requests, "get", raise_request_error)
    client = GNewsClient(api_key="token", base_url="https://gnews.example.com")

    with pytest.raises(GNewsClientError, match="Request to GNews failed: network down"):
        client.search_news("Acme")


@pytest.mark.parametrize(
    ("status_code", "text", "message"),
    [
        (401, "unauthorized", "Unauthorized. Check your GNews API key."),
        (403, "forbidden", "Forbidden. GNews rejected the request."),
        (429, "rate limited", "Rate limited by GNews. Try again later."),
        (500, "server error", "GNews request failed: 500 server error"),
    ],
)
def test_search_news_translates_http_errors(
    monkeypatch: pytest.MonkeyPatch,
    response_factory,
    status_code: int,
    text: str,
    message: str,
):
    monkeypatch.setattr(
        gnews_module.requests,
        "get",
        lambda *args, **kwargs: response_factory(status_code=status_code, text=text),
    )
    client = GNewsClient(api_key="token", base_url="https://gnews.example.com")

    with pytest.raises(GNewsClientError, match=message):
        client.search_news("Acme")


def test_search_news_raises_for_invalid_json(monkeypatch: pytest.MonkeyPatch, response_factory):
    monkeypatch.setattr(
        gnews_module.requests,
        "get",
        lambda *args, **kwargs: response_factory(json_error=ValueError("bad json")),
    )
    client = GNewsClient(api_key="token", base_url="https://gnews.example.com")

    with pytest.raises(GNewsClientError, match="GNews response was not valid JSON."):
        client.search_news("Acme")
