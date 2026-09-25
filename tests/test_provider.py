"""La validación de la clave al configurar el plugin en Dify: GET /v1/sources, que no cobra."""

from __future__ import annotations

import pytest
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from .fake_api import KEY, FakeApi, Scripted, problem


def provider(registration: PluginRegistration) -> object:
    cls = registration.get_tool_provider_cls("typesearch")
    assert cls is not None
    return cls()


def test_a_valid_key_is_checked_with_a_free_call(registration: PluginRegistration, api: FakeApi) -> None:
    provider(registration).validate_credentials({"typesearch_api_key": f"  {KEY}  "})  # type: ignore[attr-defined]
    assert [(r.method, r.path, r.query) for r in api.requests] == [("GET", "/v1/sources", {})]
    assert api.last.headers["authorization"] == f"Bearer {KEY}"


def test_an_invalid_key_says_so_without_showing_it(registration: PluginRegistration, api: FakeApi) -> None:
    wrong = "ts_live_not_a_real_key_42"
    with pytest.raises(ToolProviderCredentialValidationError) as e:
        provider(registration).validate_credentials({"typesearch_api_key": wrong})  # type: ignore[attr-defined]
    assert str(e.value) == (
        "This typesearch API key does not work (invalid_api_key): The API key is not valid. Check it at app.typesearch.ai."
    )
    assert wrong not in str(e.value)


def test_a_missing_key(registration: PluginRegistration, api: FakeApi) -> None:
    for credentials in ({}, {"typesearch_api_key": ""}, {"typesearch_api_key": None}):
        with pytest.raises(ToolProviderCredentialValidationError, match="Enter your typesearch API key"):
            provider(registration).validate_credentials(credentials)  # type: ignore[attr-defined]
    assert api.requests == []


def test_when_the_api_fails_it_says_it_could_not_check(registration: PluginRegistration, api: FakeApi) -> None:
    api.next(
        Scripted(500, problem(500, "internal_error", "Something failed.")),
        Scripted(500, problem(500, "internal_error", "Something failed.")),
    )
    with pytest.raises(
        ToolProviderCredentialValidationError, match=r"^Could not check the typesearch API key \(internal_error\): Something failed\."
    ):
        provider(registration).validate_credentials({"typesearch_api_key": KEY})  # type: ignore[attr-defined]
