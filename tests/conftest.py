from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.tool import ToolInvokeMessage

from typesearch_plugin import api as api_module

from .fake_api import FakeApi

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def fake_api() -> Iterator[FakeApi]:
    server = FakeApi()
    yield server
    server.close()


@pytest.fixture
def api(fake_api: FakeApi, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeApi]:
    """La API falsa, limpia, y el plugin apuntando a ella (sin esperar entre reintentos)."""
    fake_api.reset()
    monkeypatch.setattr(api_module, "BASE_URL", fake_api.url)
    monkeypatch.setattr(api_module, "sleep", lambda seconds: None)
    yield fake_api
    fake_api.reset()


@pytest.fixture(scope="session")
def registration() -> Iterator[PluginRegistration]:
    """El plugin cargado como lo carga Dify: manifest.yaml, provider/*.yaml, tools/*.yaml y sus clases."""
    with pytest.MonkeyPatch.context() as mp:
        mp.chdir(ROOT)
        yield PluginRegistration(DifyPluginEnv())


def texts(messages: Iterable[ToolInvokeMessage]) -> list[str]:
    return [m.message.text for m in messages if m.type == ToolInvokeMessage.MessageType.TEXT]  # type: ignore[union-attr]


def jsons(messages: Iterable[ToolInvokeMessage]) -> list[Any]:
    return [m.message.json_object for m in messages if m.type == ToolInvokeMessage.MessageType.JSON]  # type: ignore[union-attr]
