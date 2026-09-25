"""Una API falsa de typesearch, por HTTP de verdad, que cumple el contrato del OpenAPI.

Valida cada pedido contra el esquema de su ruta (como la API, rechaza campos desconocidos con 400
invalid_request) y cada respuesta que manda contra el esquema de la respuesta: las pruebas fallan si el
plugin manda algo que la API no acepta o si un ejemplo se aleja del contrato. Los esquemas salen de
fixtures/openapi-schemas.json (scripts/extract_schemas.py). Medios de ejemplo: dominios ``.example``.

``api.next(...)`` encola respuestas armadas a mano (errores, 429, cortes) que se usan antes que las
normales, en orden.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from jsonschema import Draft202012Validator, FormatChecker

SCHEMAS = json.loads((Path(__file__).resolve().parent / "fixtures" / "openapi-schemas.json").read_text(encoding="utf-8"))
_VALIDATORS: dict[str, Draft202012Validator] = {}

KEY = "ts_test_dify0123456789"


def validator(name: str) -> Draft202012Validator:
    if name not in _VALIDATORS:
        schema = {"components": SCHEMAS["components"], "$ref": f"#/components/schemas/{name}"}
        _VALIDATORS[name] = Draft202012Validator(schema, format_checker=FormatChecker())
    return _VALIDATORS[name]


def check(name: str, body: Any) -> None:
    """Falla si un ejemplo no cumple el esquema del contrato."""
    errors = list(validator(name).iter_errors(body))
    if errors:
        raise AssertionError(f"The example does not match {name}: {errors[0].message} at {list(errors[0].absolute_path)}")


# --- Ejemplos que cumplen el contrato ---------------------------------------------------------


def result(n: int, **extra: Any) -> dict[str, Any]:
    return {
        "url": f"https://diarioejemplo.example/economia/nota-{n}",
        "title": f"El dólar cerró estable por {n}ª rueda",
        "source": "Diario Ejemplo",
        "country": "AR",
        "language": "es",
        "published_at": "2026-09-21T18:05:31.000Z",
        "section": "economia",
        "snippet": "La divisa se mantuvo sin cambios frente al cierre anterior.",
        "score": 0.9612 - n / 100,
        "headline_relevance": 0.91,
        "read": None,
        "highlights": [],
        "tone": None,
        "answers": None,
        "duplicates": [],
        "date_match": None,
        "referenced_date": None,
        "found_in": "index",
        **extra,
    }


def search_response(**extra: Any) -> dict[str, Any]:
    return {
        "id": "req_fakedify1",
        "object": "search",
        "mode": "fast",
        "queries": ["el dólar"],
        "found": True,
        "total": 2,
        "results": [
            result(1),
            result(
                2,
                url="https://reddiaria.example/economia/nota-2",
                source="Red Diaria",
                found_in="discovery",
                highlights=["El dólar mayorista terminó la jornada sin variaciones"],
            ),
        ],
        "groups": None,
        "near_misses": [],
        "rejected": [],
        "diffusion": None,
        "tone": None,
        "essential": None,
        "reference": None,
        "temporal": None,
        "site": None,
        "index": None,
        "usage": {
            "tokens": 1840,
            "calls": 2,
            "cost_usd": 0.00111,
            "headlines": 160,
            "from_memory": 0,
            "pages_direct": 0,
            "pages_browser": 0,
            "duration_ms": 910,
        },
        "budget": None,
        "discovery": None,
        "incomplete": False,
        "cached_at": None,
        "warnings": [],
        **extra,
    }


def problem(status: int, code: str, detail: str | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "type": f"urn:typesearch:error:{code}",
        "title": code,
        "status": status,
        "detail": detail or f"detail of {code}",
        "code": code,
        "request_id": "req_fakeerr1",
        **extra,
    }


EMPTY_PAGE = {
    "title": None,
    "description": None,
    "published_at": None,
    "source": None,
    "excerpt": None,
    "highlights": [],
    "relevance": None,
}


@dataclass
class Scripted:
    status: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    raw: str | None = None
    destroy: bool = False
    delay: float = 0


@dataclass
class Recorded:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: Any


class FakeApi:
    def __init__(self) -> None:
        self.requests: list[Recorded] = []
        self._queue: list[Scripted] = []
        self._lock = threading.Lock()
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                api._handle(self)

            def do_POST(self) -> None:
                api._handle(self)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def next(self, *responses: Scripted) -> FakeApi:
        with self._lock:
            self._queue.extend(responses)
        return self

    def reset(self) -> None:
        with self._lock:
            self.requests.clear()
            self._queue.clear()

    @property
    def last(self) -> Recorded:
        return self.requests[-1]

    # --- Rutas ---------------------------------------------------------------------------

    def _handle(self, h: BaseHTTPRequestHandler) -> None:
        url = urlparse(h.path)
        length = int(h.headers.get("content-length") or 0)
        text = h.rfile.read(length).decode("utf-8") if length else ""
        try:
            body: Any = json.loads(text) if text else None
        except ValueError:
            body = text
        with self._lock:
            self.requests.append(Recorded(h.command, url.path, parse_qs(url.query), {k.lower(): v for k, v in h.headers.items()}, body))
            scripted = self._queue.pop(0) if self._queue else None
        if scripted is not None:
            return self._scripted(h, scripted)

        auth = h.headers.get("authorization") or (f"Bearer {h.headers['x-api-key']}" if h.headers.get("x-api-key") else None)
        if not auth:
            return self._json(h, 401, problem(401, "missing_api_key", "Missing API key."), "Problem")
        if auth != f"Bearer {KEY}":
            return self._json(h, 401, problem(401, "invalid_api_key", "The API key is not valid."), "Problem")

        route = f"{h.command} {url.path}"
        if route == "POST /v1/search":
            return self._search(h, body, "SearchRequest", "search")
        if route == "POST /v1/similar":
            return self._search(h, body, "SimilarRequest", "similar")
        if route == "POST /v1/contents":
            return self._contents(h, body)
        if route == "GET /v1/sources":
            return self._sources(h, parse_qs(url.query))
        return self._json(h, 404, problem(404, "not_found", "Not found."), "Problem")

    def _invalid(self, h: BaseHTTPRequestHandler, body: Any, schema: str) -> bool:
        errors = sorted(validator(schema).iter_errors(body), key=lambda e: list(e.absolute_path))
        if not errors:
            return False
        detail = [{"path": ".".join(str(p) for p in e.absolute_path) or "(body)", "message": e.message} for e in errors]
        self._json(h, 400, problem(400, "invalid_request", f"{detail[0]['path']}: {detail[0]['message']}", errors=detail), "Problem")
        return True

    def _search(self, h: BaseHTTPRequestHandler, body: Any, schema: str, obj: str) -> None:
        if self._invalid(h, body, schema):
            return
        queries = [] if obj == "similar" else ([body["query"]] if isinstance(body["query"], str) else body["query"])
        reference = {"url": body["url"], "title": "Inflación: qué esperan los analistas"} if obj == "similar" else None
        self._json(
            h, 200, search_response(object=obj, mode=body.get("mode", "normal"), queries=queries, reference=reference), "SearchResponse"
        )

    def _contents(self, h: BaseHTTPRequestHandler, body: Any) -> None:
        if self._invalid(h, body, "ContentsRequest"):
            return
        results = []
        for u in body["urls"]:
            if "unreachable" in u:
                results.append(
                    {
                        "url": u,
                        "status": "error",
                        "error": {"code": "site_unreachable", "message": "The site did not answer."},
                        **EMPTY_PAGE,
                    }
                )
                continue
            results.append(
                {
                    "url": u,
                    "status": "ok",
                    "error": None,
                    "title": "Presupuesto 2027: las claves del proyecto",
                    "description": "El Gobierno envió el proyecto al Congreso.",
                    "published_at": "2026-09-16T01:12:00.000Z",
                    "source": "Red Diaria",
                    "excerpt": "El proyecto prevé un superávit primario",
                    "highlights": ["El proyecto prevé un superávit primario"] if body.get("query") else [],
                    "relevance": 0.97 if body.get("query") else None,
                }
            )
        out = {
            "id": "req_fakecont",
            "object": "contents",
            "results": results,
            "usage": {"tokens": 1320, "calls": 1, "cost_usd": 0.0002, "duration_ms": 1840},
        }
        self._json(h, 200, out, "ContentsResponse")

    def _sources(self, h: BaseHTTPRequestHandler, q: dict[str, list[str]]) -> None:
        domain = q.get("domain", [None])[0]
        if domain is None:
            out: dict[str, Any] = {
                "object": "sources",
                "updated_at": "2026-09-22T14:05:02.000Z",
                "total": 1234,
                "articles": 567890,
                "by_country": [{"country": "AR", "sources": 120}, {"country": None, "sources": 4}],
                "by_language": [{"language": "es", "sources": 900}, {"language": "en", "sources": 334}],
            }
            return self._json(h, 200, out, "Sources")
        if domain == "diarioejemplo.example":
            out = {
                "object": "source",
                "domain": domain,
                "covered": True,
                "name": "Diario Ejemplo",
                "country": "AR",
                "languages": ["es"],
                "articles": 1520,
                "last_refreshed_at": "2026-09-22T14:05:02.000Z",
            }
            return self._json(h, 200, out, "Source")
        self._json(h, 200, {"object": "source", "domain": domain, "covered": False}, "Source")

    # --- Salida --------------------------------------------------------------------------

    def _json(self, h: BaseHTTPRequestHandler, status: int, body: Any, schema: str) -> None:
        check(schema, body)
        data = json.dumps(body).encode("utf-8")
        h.send_response(status)
        h.send_header("Content-Type", "application/problem+json; charset=utf-8" if status >= 400 else "application/json; charset=utf-8")
        h.send_header(
            "X-Request-Id", str(body.get("id") or body.get("request_id") or "req_fake0001") if isinstance(body, dict) else "req_fake0001"
        )
        h.send_header("Content-Length", str(len(data)))
        h.end_headers()
        h.wfile.write(data)

    def _scripted(self, h: BaseHTTPRequestHandler, s: Scripted) -> None:
        if s.delay:
            time.sleep(s.delay)
        if s.destroy:
            h.close_connection = True
            return
        if s.raw is not None:
            data = s.raw.encode("utf-8")
            content_type = "text/html"
        else:
            if s.status >= 400 and isinstance(s.body, dict):
                check("Problem", s.body)
            elif isinstance(s.body, dict) and s.body.get("object") in ("search", "similar"):
                check("SearchResponse", s.body)
            data = b"" if s.body is None else json.dumps(s.body).encode("utf-8")
            content_type = "application/problem+json" if s.status >= 400 else "application/json"
        try:
            h.send_response(s.status)
            h.send_header("Content-Type", content_type)
            h.send_header("X-Request-Id", "req_fakescr1")
            h.send_header("Content-Length", str(len(data)))
            for k, v in s.headers.items():
                h.send_header(k, v)
            h.end_headers()
            h.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
