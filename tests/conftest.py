from __future__ import annotations

from collections.abc import Callable

import pytest

API_ENV_VARS = (
    "GNEWS_API_KEY",
    "OPENROUTER_API_KEY",
    "COMPANIES_HOUSE_API_KEY",
)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data=None,
        text: str = "",
        ok: bool | None = None,
        json_error: Exception | None = None,
    ):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self._ok = ok if ok is not None else 200 <= status_code < 300
        self._json_error = json_error

    @property
    def ok(self) -> bool:
        return self._ok

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


@pytest.fixture(autouse=True)
def clear_api_env(monkeypatch: pytest.MonkeyPatch):
    for env_name in API_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)


@pytest.fixture
def response_factory() -> Callable[..., FakeResponse]:
    def _build_response(**kwargs) -> FakeResponse:
        return FakeResponse(**kwargs)

    return _build_response
