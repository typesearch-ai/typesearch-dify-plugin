"""Correr una herramienta: validar los parámetros, llamar a la API y responder con mensajes de Dify.

Cada herramienta (tools/*.py) es una subclase de ``Tool`` que llama a ``run`` con su nombre. Acá no hay
subclases de ``Tool``: dify_plugin carga cada archivo de tools/ buscando exactamente una.

La salida es un mensaje de texto legible (lo que lee el modelo en un agente) y un mensaje JSON con los
mismos datos, compactos (la variable ``json`` de un workflow). Un error es un solo mensaje de texto,
``Error (code): …``, como en el MCP: el agente lo lee y decide; nunca lleva la clave.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from . import api, output, params

CREDENTIAL = "typesearch_api_key"


def _search(client: api.Client, p: Mapping[str, Any]) -> output.Output:
    body = params.search_body(p)
    return output.search_output(client.search(body), body["query"])


def _contents(client: api.Client, p: Mapping[str, Any]) -> output.Output:
    return output.contents_output(client.contents(params.contents_body(p)))


def _similar(client: api.Client, p: Mapping[str, Any]) -> output.Output:
    return output.similar_output(client.similar(params.similar_body(p)))


# Cada herramienta: cómo llama a la API y convierte la respuesta…
TOOLS: dict[str, Callable[[api.Client, Mapping[str, Any]], output.Output]] = {
    "search_news": _search,
    "get_contents": _contents,
    "find_similar": _similar,
}

# …y cómo valida sus parámetros antes de llamar (y antes de pedir la clave).
VALIDATE: dict[str, Callable[[Mapping[str, Any]], object]] = {
    "search_news": params.search_body,
    "get_contents": params.contents_body,
    "find_similar": params.similar_body,
}


def api_key(credentials: Mapping[str, Any] | None) -> str:
    value = (credentials or {}).get(CREDENTIAL)
    return value.strip() if isinstance(value, str) else ""


def check_credentials(credentials: Mapping[str, Any] | None, *, client: Callable[..., api.Client] = api.Client) -> str | None:
    """``None`` si la clave sirve; si no, qué pasa, para mostrarlo en Dify. Usa GET /v1/usage, que no cobra."""
    key = api_key(credentials)
    if not key:
        return f"Enter your typesearch API key. Get one at {api.DASHBOARD}."
    try:
        with client(key, timeout=15.0, budget=30.0) as c:
            c.usage()
    except api.TypesearchError as e:
        if e.status == 401:
            return f"This typesearch API key does not work ({e.code}): {e.message} Check it at {api.DASHBOARD}."
        return f"Could not check the typesearch API key ({e.code}): {e.message}"
    return None


def invoke(
    name: str, parameters: Mapping[str, Any], credentials: Mapping[str, Any] | None, *, client: Callable[[str], api.Client] = api.Client
) -> output.Output:
    """La herramienta ``name`` con esos parámetros. Lanza ``ParameterError`` o ``TypesearchError``."""
    parameters = parameters or {}
    VALIDATE[name](parameters)
    key = api_key(credentials)
    if not key:
        raise api.missing_key()
    with client(key) as c:
        return TOOLS[name](c, parameters)


def run(tool: Tool, name: str, parameters: Mapping[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
    """Lo que hace ``_invoke`` en cada herramienta."""
    try:
        result = invoke(name, parameters, tool.runtime.credentials)
    except params.ParameterError as e:
        yield tool.create_text_message(f"Error (invalid_request): {e}")
        return
    except api.TypesearchError as e:
        yield tool.create_text_message(e.for_model())
        return
    yield tool.create_text_message(result.text)
    yield tool.create_json_message(result.data)
