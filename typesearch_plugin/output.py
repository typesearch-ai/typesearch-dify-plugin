"""La salida de cada herramienta: texto breve y legible (lo que lee el modelo) y un JSON con los mismos datos,
sin campos vacíos. Es la misma forma que la del servidor MCP de typesearch (typesearch-mcp, src/format.ts):
un agente ve lo mismo en Dify que por MCP.

Cada función recibe la respuesta de la API tal como llega (un dict) y devuelve ``Output(text, data)``.
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Output:
    text: str
    data: dict[str, Any]


# --- Utilidades ----------------------------------------------------------------------------


def compact(o: Mapping[str, Any]) -> dict[str, Any]:
    """Sin None, sin cadenas vacías y sin listas vacías: lo que no dice nada no gasta tokens."""
    return {k: v for k, v in o.items() if v is not None and v != "" and not (isinstance(v, (list, tuple)) and len(v) == 0)}


def shorten(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    cut = clean.rfind(" ", 0, limit)
    return f"{clean[: cut if cut > limit * 0.6 else limit - 1]}…"


def to_minute(iso: object) -> str | None:
    """ISO al minuto, en UTC: ``2026-09-25T14:05Z``. Lo que no se entiende queda como vino."""
    if not isinstance(iso, str) or not iso:
        return None
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        return iso
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.UTC)
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%MZ")


def round2(x: Any) -> float:
    """Como ``Math.round(x * 100) / 100`` en JavaScript (la mitad sube)."""
    return math.floor(float(x) * 100 + 0.5) / 100


def count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def usd(value: Any) -> str:
    return f"US${float(value or 0):.4f}"


def cost(s: Mapping[str, Any]) -> str:
    return "cached, free" if s.get("cached") else usd(s.get("cost_usd"))


def utc(iso: str) -> str:
    return iso.replace("T", " ", 1).replace("Z", " UTC", 1)


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


# --- Búsqueda y parecidas --------------------------------------------------------------------

WHERE = {
    "homepage": "from the homepage",
    "section": "from a section page",
    "site_search": "from the site's search",
    "discovery": "found beyond the index",
}


def result(r: Mapping[str, Any]) -> dict[str, Any]:
    """Un resultado compacto. El país y el idioma de la fuente llegan con la API que filtra por país e idioma."""
    snippet = r.get("snippet")
    found_in = r.get("found_in")
    return compact(
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "source": r.get("source"),
            "published_at": to_minute(r.get("published_at")),
            "country": r.get("country"),
            "language": r.get("language"),
            "snippet": shorten(snippet, 300) if isinstance(snippet, str) and snippet else None,
            "highlights": _list(r.get("highlights")),
            "score": round2(r.get("score") or 0),
            "found_in": None if found_in == "index" else found_in,
        }
    )


def result_lines(r: Mapping[str, Any], i: int) -> list[str]:
    place = "/".join(x for x in (r.get("country"), r.get("language")) if x)
    published = r.get("published_at")
    meta = " · ".join(
        x
        for x in (
            r.get("source"),
            utc(published) if published else None,
            place or None,
            WHERE.get(r["found_in"], r["found_in"]) if r.get("found_in") else None,
        )
        if x
    )
    return [
        f"{i + 1}. {r.get('title')}",
        *([meta] if meta else []),
        str(r.get("url")),
        *([r["snippet"]] if r.get("snippet") else []),
        *(f"> {h}" for h in r.get("highlights", [])),
    ]


def summarize(r: Mapping[str, Any]) -> dict[str, Any]:
    results = [result(x) for x in _list(r.get("results"))]
    usage = r.get("usage") if isinstance(r.get("usage"), Mapping) else {}
    # `results` va siempre, aunque esté vacía: es lo que dice que no se encontró nada.
    rest = compact(
        {
            "near_misses": [result(x) for x in _list(r.get("near_misses"))[:5]] if not results else [],
            "incomplete": True if r.get("incomplete") else None,
            "cached": True if r.get("cached_at") else None,
            "cost_usd": (usage or {}).get("cost_usd") or 0,
            "warnings": [{"code": w.get("code"), "message": w.get("message")} for w in _list(r.get("warnings")) if isinstance(w, Mapping)],
            "request_id": r.get("id"),
        }
    )
    return {"mode": r.get("mode"), "results": results, **rest}


def search_text(header: str, s: Mapping[str, Any]) -> str:
    parts = [header]
    if s["results"]:
        parts.extend("\n".join(result_lines(x, i)) for i, x in enumerate(s["results"]))
    elif s.get("near_misses"):
        parts.append("Closest articles, which may not be about it:")
        parts.extend("\n".join(result_lines(x, i)) for i, x in enumerate(s["near_misses"]))
    if s.get("incomplete"):
        parts.append("Incomplete: the time or token budget ran out; repeating the search in a minute may bring more.")
    for w in s.get("warnings", []):
        parts.append(f"Note ({w.get('code')}): {w.get('message')}")
    return "\n\n".join(parts)


def search_output(r: Mapping[str, Any], query: str) -> Output:
    s = {"query": query, **summarize(r)}
    found = count(len(s["results"]), "result", "results") if s["results"] else "No results"
    header = f'{found} for "{query}" · {s["mode"]} · {cost(s)}'
    return Output(search_text(header, s), s)


def similar_output(r: Mapping[str, Any]) -> Output:
    ref = r.get("reference") if isinstance(r.get("reference"), Mapping) else None
    s = compact({"reference": {"title": ref.get("title"), "url": ref.get("url")} if ref else None, **summarize(r)})
    s.setdefault("results", [])
    of = f' to "{ref.get("title")}"' if ref else ""
    found = count(len(s["results"]), "similar article", "similar articles") if s["results"] else "No similar articles"
    header = f"{found}{of} · {cost(s)}"
    return Output(search_text(header, s), s)


# --- Contenidos --------------------------------------------------------------------------------


def contents_output(r: Mapping[str, Any]) -> Output:
    results: list[dict[str, Any]] = []
    for x in _list(r.get("results")):
        description = x.get("description")
        excerpt = x.get("excerpt")
        relevance = x.get("relevance")
        error = x.get("error") if isinstance(x.get("error"), Mapping) else None
        results.append(
            compact(
                {
                    "url": x.get("url"),
                    "status": x.get("status"),
                    "title": x.get("title"),
                    "description": shorten(description, 300) if isinstance(description, str) and description else None,
                    "published_at": to_minute(x.get("published_at")),
                    "source": x.get("source"),
                    "excerpt": excerpt,
                    # El fragmento sobre la consulta ya es `excerpt`: highlights sólo si suman algo.
                    "highlights": [h for h in _list(x.get("highlights")) if h != excerpt],
                    "relevance": None if relevance is None else round2(relevance),
                    "error": {"code": error.get("code"), "message": error.get("message")} if error else None,
                }
            )
        )
    usage = r.get("usage") if isinstance(r.get("usage"), Mapping) else {}
    s = {"results": results, "cost_usd": (usage or {}).get("cost_usd") or 0, "request_id": r.get("id")}
    s = {k: v for k, v in s.items() if v is not None}
    ok = sum(1 for x in results if x.get("status") == "ok")
    blocks = []
    for i, x in enumerate(results):
        if x.get("status") == "error":
            e = x.get("error", {})
            blocks.append(f"{i + 1}. {x.get('url')}\nError ({e.get('code')}): {e.get('message')}")
            continue
        published = x.get("published_at")
        meta = " · ".join(v for v in (x.get("source"), utc(published) if published else None) if v)
        lines = [
            f"{i + 1}. {x.get('title') or x.get('url')}",
            *([meta] if meta else []),
            str(x.get("url")),
            *([x["description"]] if x.get("description") else []),
            *([f"> {x['excerpt']}"] if x.get("excerpt") else []),
            *(f"> {h}" for h in x.get("highlights", [])),
            *([f"Relevance to the query: {x['relevance']:g}"] if "relevance" in x else []),
        ]
        blocks.append("\n".join(lines))
    header = f"{ok} of {count(len(results), 'URL', 'URLs')} read · {usd(s.get('cost_usd'))}"
    return Output("\n\n".join([header, *blocks]), s)


# --- Cobertura ---------------------------------------------------------------------------------


def coverage_output(r: Mapping[str, Any]) -> Output:
    if r.get("object") == "source":
        languages = _list(r.get("languages"))
        s = compact(
            {
                "domain": r.get("domain"),
                "covered": r.get("covered"),
                "name": r.get("name"),
                "country": r.get("country"),
                "languages": languages,
                "articles": r.get("articles"),
                "last_refreshed_at": to_minute(r.get("last_refreshed_at")),
            }
        )
        if r.get("covered"):
            place = " · ".join(x for x in (r.get("country"), "/".join(languages) if languages else None) if x)
            name = f" ({r['name']})" if r.get("name") else ""
            articles = f" · {r['articles']:,} articles" if isinstance(r.get("articles"), int) else ""
            refreshed = f" · last refreshed {s['last_refreshed_at']}" if s.get("last_refreshed_at") else ""
            text = f"{r.get('domain')} is covered{name}: {place}{articles}{refreshed}."
        else:
            text = f"{r.get('domain')} is not covered by the index."
        return Output(text, s)

    by_country = [{"country": x.get("country") or "international", "sources": x.get("sources")} for x in _list(r.get("by_country"))]
    by_language = [{"language": x.get("language"), "sources": x.get("sources")} for x in _list(r.get("by_language"))]
    s = compact(
        {
            "sources": r.get("total"),
            "articles": r.get("articles"),
            "updated_at": to_minute(r.get("updated_at")),
            "by_country": by_country,
            "by_language": by_language,
        }
    )

    def listing(xs: Sequence[Mapping[str, Any]], key: str) -> str:
        return ", ".join(f"{x.get(key)} {x.get('sources')}" for x in xs)

    text = "\n".join(
        [
            f"The index has {int(r.get('total') or 0):,} sources and {int(r.get('articles') or 0):,} articles.",
            f"Sources by country: {listing(by_country, 'country')}.",
            f"Sources by language: {listing(by_language, 'language')}.",
        ]
    )
    return Output(text, s)
