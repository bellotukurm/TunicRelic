import pytest
import requests

import clients.openrouter as openrouter_module
from clients.openrouter import OPENROUTER_API_KEY_NAME, OpenRouterClient, OpenRouterClientError, TIMEOUT_SECONDS
from config.app_config import AppConfigError


def test_constructor_fails_when_api_key_is_missing():
    with pytest.raises(
        OpenRouterClientError,
        match=f"Missing environment variable: {OPENROUTER_API_KEY_NAME}",
    ):
        OpenRouterClient(default_model="openai/gpt-5.4", base_url="https://openrouter.example.com")


def test_constructor_translates_config_lookup_failures(monkeypatch: pytest.MonkeyPatch):
    def raise_config_error():
        raise AppConfigError("bad config")

    monkeypatch.setattr(openrouter_module, "get_openrouter_default_model", raise_config_error)

    with pytest.raises(OpenRouterClientError, match="bad config"):
        OpenRouterClient(api_key="token")


def test_create_chat_completion_requires_messages():
    client = OpenRouterClient(
        api_key="token",
        default_model="openai/gpt-5.4",
        base_url="https://openrouter.example.com",
    )

    with pytest.raises(OpenRouterClientError, match=r"payload\['messages'\] is required"):
        client.create_chat_completion({})


def test_create_chat_completion_sends_expected_request(monkeypatch: pytest.MonkeyPatch, response_factory):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return response_factory(json_data={"id": "resp_1", "choices": []})

    monkeypatch.setattr(openrouter_module.requests, "post", fake_post)
    client = OpenRouterClient(
        api_key="token",
        default_model="openai/gpt-5.4",
        base_url="https://openrouter.example.com/",
    )

    result = client.create_chat_completion(
        {
            "messages": [{"role": "user", "content": "Hello"}],
            "temperature": 0.3,
        }
    )

    assert result == {"id": "resp_1", "choices": []}
    assert captured["url"] == "https://openrouter.example.com/chat/completions"
    assert captured["headers"] == {
        "Authorization": "Bearer token",
        "Content-Type": "application/json",
    }
    assert captured["json"] == {
        "model": "openai/gpt-5.4",
        "messages": [{"role": "user", "content": "Hello"}],
        "temperature": 0.3,
    }
    assert captured["timeout"] == TIMEOUT_SECONDS


def test_create_chat_completion_translates_request_exceptions(monkeypatch: pytest.MonkeyPatch):
    def raise_request_error(*args, **kwargs):
        raise requests.RequestException("network down")

    monkeypatch.setattr(openrouter_module.requests, "post", raise_request_error)
    client = OpenRouterClient(
        api_key="token",
        default_model="openai/gpt-5.4",
        base_url="https://openrouter.example.com",
    )

    with pytest.raises(
        OpenRouterClientError,
        match="Request to OpenRouter failed: network down",
    ):
        client.create_chat_completion({"messages": [{"role": "user", "content": "Hi"}]})


@pytest.mark.parametrize(
    ("status_code", "text", "message"),
    [
        (401, "unauthorized", "Unauthorized. Check your OpenRouter API key."),
        (500, "server error", "OpenRouter request failed: 500 server error"),
    ],
)
def test_create_chat_completion_translates_http_errors(
    monkeypatch: pytest.MonkeyPatch,
    response_factory,
    status_code: int,
    text: str,
    message: str,
):
    monkeypatch.setattr(
        openrouter_module.requests,
        "post",
        lambda *args, **kwargs: response_factory(status_code=status_code, text=text),
    )
    client = OpenRouterClient(
        api_key="token",
        default_model="openai/gpt-5.4",
        base_url="https://openrouter.example.com",
    )

    with pytest.raises(OpenRouterClientError, match=message):
        client.create_chat_completion({"messages": [{"role": "user", "content": "Hi"}]})


def test_create_chat_completion_raises_for_invalid_json(monkeypatch: pytest.MonkeyPatch, response_factory):
    monkeypatch.setattr(
        openrouter_module.requests,
        "post",
        lambda *args, **kwargs: response_factory(json_error=ValueError("bad json")),
    )
    client = OpenRouterClient(
        api_key="token",
        default_model="openai/gpt-5.4",
        base_url="https://openrouter.example.com",
    )

    with pytest.raises(OpenRouterClientError, match="OpenRouter response was not valid JSON."):
        client.create_chat_completion({"messages": [{"role": "user", "content": "Hi"}]})


def test_create_structured_output_builds_expected_payload(monkeypatch: pytest.MonkeyPatch):
    captured = {}
    client = OpenRouterClient(
        api_key="token",
        default_model="openai/gpt-5.4",
        base_url="https://openrouter.example.com",
    )

    def fake_create_chat_completion(payload):
        captured["payload"] = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"brand":"Acme"}',
                    }
                }
            ]
        }

    monkeypatch.setattr(client, "create_chat_completion", fake_create_chat_completion)

    result = client.create_structured_output(
        messages=[{"role": "user", "content": "Find brand"}],
        json_schema={"type": "object"},
        schema_name="brand_identification",
        model="openai/gpt-5.4-mini",
        max_tokens=123,
        tools=[{"type": "openrouter:web_search"}],
    )

    assert result == '{"brand":"Acme"}'
    assert captured["payload"] == {
        "model": "openai/gpt-5.4-mini",
        "messages": [{"role": "user", "content": "Find brand"}],
        "stream": False,
        "provider": {"require_parameters": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "brand_identification",
                "strict": True,
                "schema": {"type": "object"},
            },
        },
        "max_tokens": 123,
        "tools": [{"type": "openrouter:web_search"}],
    }


@pytest.mark.parametrize(
    ("response_data", "message"),
    [
        ({"choices": []}, "OpenRouter response did not include any choices."),
        (
            {"choices": [{"message": {"content": ""}}]},
            "OpenRouter response did not include content.",
        ),
    ],
)
def test_create_structured_output_rejects_incomplete_responses(
    monkeypatch: pytest.MonkeyPatch,
    response_data: dict,
    message: str,
):
    client = OpenRouterClient(
        api_key="token",
        default_model="openai/gpt-5.4",
        base_url="https://openrouter.example.com",
    )
    monkeypatch.setattr(client, "create_chat_completion", lambda payload: response_data)

    with pytest.raises(OpenRouterClientError, match=message):
        client.create_structured_output(
            messages=[{"role": "user", "content": "Find brand"}],
            json_schema={"type": "object"},
            schema_name="brand_identification",
        )
