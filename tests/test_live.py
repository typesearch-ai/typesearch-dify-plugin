"""Contra la API de verdad: corre sólo con ``TYPESEARCH_LIVE=1`` y ``TYPESEARCH_API_KEY`` en el entorno.

    TYPESEARCH_LIVE=1 TYPESEARCH_API_KEY=ts_live_… uv run pytest tests/test_live.py -v

Gasta muy poco: una búsqueda ``fast`` de 3 resultados y el contenido de una URL; la validación de la clave
y ``check_coverage`` no cobran. ``TYPESEARCH_BASE_URL`` apunta a otra API (local o de prueba).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from dify_plugin.core.plugin_registration import PluginRegistration

from typesearch_plugin import api as api_module

from .conftest import jsons, texts

KEY = os.environ.get("TYPESEARCH_API_KEY") if os.environ.get("TYPESEARCH_LIVE") == "1" else None

pytestmark = pytest.mark.skipif(not KEY, reason="set TYPESEARCH_LIVE=1 and TYPESEARCH_API_KEY to run against the real API")


@pytest.fixture(autouse=True)
def base_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if os.environ.get("TYPESEARCH_BASE_URL"):
        monkeypatch.setattr(api_module, "BASE_URL", os.environ["TYPESEARCH_BASE_URL"])
    yield


def test_the_key_validates_and_coverage_is_free(registration: PluginRegistration) -> None:
    provider = registration.get_tool_provider_cls("typesearch")
    assert provider is not None
    provider().validate_credentials({"typesearch_api_key": KEY})
    tool = registration.get_tool_cls("typesearch", "check_coverage")
    assert tool is not None
    messages = list(tool.from_credentials({"typesearch_api_key": KEY}).invoke({}))
    assert texts(messages)[0].startswith("The index has ")
    assert jsons(messages)[0]["sources"] > 0


def test_search_and_contents(registration: PluginRegistration) -> None:
    search = registration.get_tool_cls("typesearch", "search_news")
    assert search is not None
    messages = list(search.from_credentials({"typesearch_api_key": KEY}).invoke({"query": "inflación", "max_results": 3, "days": 7}))
    assert not texts(messages)[0].startswith("Error"), texts(messages)[0]
    data = jsons(messages)[0]
    assert data["mode"] == "fast" and len(data["results"]) <= 3
    if data["results"]:
        contents = registration.get_tool_cls("typesearch", "get_contents")
        assert contents is not None
        page = list(contents.from_credentials({"typesearch_api_key": KEY}).invoke({"urls": data["results"][0]["url"]}))
        assert jsons(page)[0]["results"][0]["url"] == data["results"][0]["url"]


def test_a_wrong_key_is_explained(registration: PluginRegistration) -> None:
    search = registration.get_tool_cls("typesearch", "search_news")
    assert search is not None
    text = texts(list(search.from_credentials({"typesearch_api_key": "ts_live_invalid"}).invoke({"query": "inflación"})))[0]
    assert text.startswith("Error (invalid_api_key)")
