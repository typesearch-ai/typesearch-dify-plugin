"""Los parámetros de cada herramienta: se leen como llegan de Dify y se validan antes de llamar a la API.

Dify manda lo que escribió el modelo o lo que configuró el usuario en un workflow: números como float o
como texto, campos vacíos como ``None`` o ``""``, y las listas (dominios, países, idiomas, URLs) como texto
separado por comas o saltos de línea. Acá se normaliza todo eso y se arma el cuerpo del pedido con los
nombres de la API. Los mensajes de error son los mismos del MCP de typesearch, en inglés: el modelo los
lee y corrige el pedido sin gastar una llamada.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections.abc import Mapping
from typing import Any

MODES = ("ultra", "fast", "normal", "deep")
DEFAULT_MODE = "fast"
DEFAULT_MAX_RESULTS = 10

# El mismo patrón que la API para include_domains y exclude_domains (\w en ASCII, como en JavaScript).
DOMAIN_RE = re.compile(r"^(https?://)?(\*\.)?[\w-]+(\.[\w-]+)+(/\S*)?$", re.IGNORECASE | re.ASCII)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[Tt](\d{2}:\d{2})(:\d{2}(?:\.\d+)?)?([Zz]|[+-]\d{2}:\d{2})$")
URL_RE = re.compile(r"^https?://[^\s/$.?#][^\s]*$", re.IGNORECASE)
# Entre URLs: espacios o saltos de línea, o una coma (o punto y coma) seguida de otra URL.
URL_SPLIT_RE = re.compile(r"\s+|[,;](?=\s*https?://)", re.IGNORECASE)
LIST_SPLIT_RE = re.compile(r"[\s,;]+")


class ParameterError(ValueError):
    """Un parámetro que no sirve. El mensaje, en inglés, es para el modelo."""


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, (list, tuple)) and not value)


def _text(value: Any, field: str) -> str | None:
    if _blank(value):
        return None
    if not isinstance(value, str):
        raise ParameterError(f"{field} must be text.")
    return value.strip()


def _query(value: Any, field: str = "query", *, required: bool = True) -> str | None:
    text = _text(value, field)
    if text is None:
        if required:
            raise ParameterError(f"{field} is required: what to look for, such as a topic, event, person, company or place.")
        return None
    if len(text) < 2:
        raise ParameterError(f"{field} needs at least two letters.")
    if len(text) > 200:
        raise ParameterError(f"{field} is too long: 200 characters at most.")
    return text


def _whole(value: Any, field: str, low: int, high: int, default: int | None = None) -> int | None:
    if _blank(value):
        return default
    message = f"{field} must be a whole number from {low} to {high}."
    number: float
    if isinstance(value, bool):
        raise ParameterError(message)
    if isinstance(value, (int, float)):
        number = value
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            raise ParameterError(message) from None
    else:
        raise ParameterError(message)
    if not float(number).is_integer() or not low <= number <= high:
        raise ParameterError(message)
    return int(number)


def _mode(value: Any) -> str:
    text = _text(value, "mode")
    if text is None:
        return DEFAULT_MODE
    mode = text.lower()
    if mode not in MODES:
        raise ParameterError("mode must be ultra, fast, normal or deep.")
    return mode


def _date(value: Any, field: str) -> str | None:
    """Una fecha (2026-09-25) o una fecha y hora con su zona; sin segundos, se les agrega ``:00``."""
    text = _text(value, field)
    if text is None:
        return None
    message = f"{field} must be a date (2026-09-25) or a date-time with its offset (2026-09-25T14:00:00Z)."
    try:
        if DATE_RE.match(text):
            dt.date.fromisoformat(text)
            return text
        match = DATETIME_RE.match(text)
        if match:
            day, minutes, seconds, zone = match.groups()
            normal = f"{day}T{minutes}{seconds or ':00'}{'Z' if zone in ('Z', 'z') else zone}"
            dt.datetime.fromisoformat(normal.replace("Z", "+00:00"))
            return normal
    except ValueError:
        pass
    raise ParameterError(message)


def _items(value: Any, field: str, split: re.Pattern[str]) -> list[str]:
    """Una lista como texto separado por comas o saltos de línea, como JSON (["a", "b"]) o como lista."""
    raw: list[Any]
    if isinstance(value, (list, tuple)):
        raw = list(value)
    elif isinstance(value, str):
        text = value.strip()
        parsed: Any = None
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
        raw = parsed if isinstance(parsed, list) else split.split(text)
    else:
        raise ParameterError(f"{field} must be text: items separated by commas.")
    items: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ParameterError(f"{field} must be text: items separated by commas.")
        item = item.strip().strip("\"'").strip()
        if item and item not in items:
            items.append(item)
    return items


def _list(
    value: Any, field: str, *, what: str, max_items: int, max_len: int, check: re.Pattern[str] | None = None, example: str = ""
) -> list[str] | None:
    if _blank(value):
        return None
    items = _items(value, field, LIST_SPLIT_RE)
    if not items:
        return None
    if len(items) > max_items:
        raise ParameterError(f"{field}: {max_items} {what} at most.")
    for item in items:
        if len(item) > max_len:
            raise ParameterError(f"{field}: {max_len} characters at most per item.")
        if check is not None and not check.match(item):
            raise ParameterError(f'{field}: "{item}" is not valid; use {example}.')
    return items


def _url(value: str, field: str) -> str:
    if len(value) > 2000:
        raise ParameterError(f"{field}: 2000 characters at most per URL.")
    if not URL_RE.match(value):
        raise ParameterError(f'{field}: "{value}" is not an article URL; use full URLs such as https://example.com/news/article.')
    return value


# --- Un cuerpo por herramienta ------------------------------------------------------------------


def search_body(p: Mapping[str, Any]) -> dict[str, Any]:
    """POST /v1/search: el modo ``fast`` y 10 resultados salvo que se pida otra cosa."""
    body: dict[str, Any] = {
        "query": _query(p.get("query")),
        "mode": _mode(p.get("mode")),
        "max_results": _whole(p.get("max_results"), "max_results", 1, 25, DEFAULT_MAX_RESULTS),
    }
    optional = {
        "days": _whole(p.get("days"), "days", 1, 365),
        "published_after": _date(p.get("published_after"), "published_after"),
        "published_before": _date(p.get("published_before"), "published_before"),
        "include_domains": _domains(p.get("include_domains"), "include_domains"),
        "exclude_domains": _domains(p.get("exclude_domains"), "exclude_domains"),
        "countries": _list(p.get("countries"), "countries", what="codes", max_items=50, max_len=20),
        "languages": _list(p.get("languages"), "languages", what="codes", max_items=20, max_len=35),
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    return body


def contents_body(p: Mapping[str, Any]) -> dict[str, Any]:
    """POST /v1/contents: hasta 10 URLs y, si hay, la consulta que elige el fragmento."""
    if _blank(p.get("urls")):
        raise ParameterError("urls needs at least one URL.")
    urls = [_url(u, "urls") for u in _items(p.get("urls"), "urls", URL_SPLIT_RE)]
    if not urls:
        raise ParameterError("urls needs at least one URL.")
    if len(urls) > 10:
        raise ParameterError("urls: 10 at most.")
    body: dict[str, Any] = {"urls": urls}
    query = _query(p.get("query"), required=False)
    if query is not None:
        body["query"] = query
    return body


def similar_body(p: Mapping[str, Any]) -> dict[str, Any]:
    """POST /v1/similar en modo ``fast``: cuesta lo mismo en ultra, fast y normal, y fast sólo lee la nota de referencia."""
    url = _text(p.get("url"), "url")
    if url is None:
        raise ParameterError("url is required: the article URL whose story to find elsewhere.")
    body: dict[str, Any] = {
        "url": _url(url, "url"),
        "mode": "fast",
        "max_results": _whole(p.get("max_results"), "max_results", 1, 25, DEFAULT_MAX_RESULTS),
    }
    optional = {
        "days": _whole(p.get("days"), "days", 1, 365),
        # Los fija quien arma la app (form: form), no el modelo.
        "countries": _list(p.get("countries"), "countries", what="codes", max_items=50, max_len=20),
        "languages": _list(p.get("languages"), "languages", what="codes", max_items=20, max_len=35),
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    return body


def _domains(value: Any, field: str) -> list[str] | None:
    return _list(
        value,
        field,
        what="domains",
        max_items=20,
        max_len=200,
        check=DOMAIN_RE,
        example="a domain or a path, such as example.com or example.com/sports",
    )
