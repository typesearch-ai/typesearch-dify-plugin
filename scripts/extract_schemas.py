"""Extrae del OpenAPI de typesearch los esquemas que usa la API falsa de las pruebas.

    uv run python scripts/extract_schemas.py path/to/openapi.json   # desde un archivo
    uv run python scripts/extract_schemas.py --fetch                # desde la API viva
    uv run python scripts/extract_schemas.py --check path/...       # falla si el fixture quedó viejo

Deja en tests/fixtures/openapi-schemas.json sólo los pedidos y las respuestas de las cuatro rutas que usa
el plugin (y lo que referencian), sin descripciones: un fixture chico que valida los cuerpos que manda el
plugin y los ejemplos que responde la API falsa.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

LIVE = "https://api.typesearch.ai/v1/openapi.json"
OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "openapi-schemas.json"
ROOTS = ["SearchRequest", "SimilarRequest", "ContentsRequest", "SearchResponse", "ContentsResponse", "Sources", "Source", "Problem"]
REF = re.compile(r"#/components/schemas/([\w.-]+)")


def strip(node: Any, *, in_properties: bool = False) -> Any:
    """Sin ``description``, ``examples`` ni extensiones ``x-``; los nombres de propiedades quedan."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            if not in_properties and (key in ("description", "examples", "example", "title") or key.startswith("x-")):
                continue
            out[key] = strip(value, in_properties=(key == "properties" and not in_properties))
        return out
    if isinstance(node, list):
        return [strip(v) for v in node]
    return node


def extract(openapi: dict[str, Any]) -> dict[str, Any]:
    schemas = openapi["components"]["schemas"]
    wanted: list[str] = []
    pending = list(ROOTS)
    while pending:
        name = pending.pop(0)
        if name in wanted:
            continue
        if name not in schemas:
            raise SystemExit(f"The OpenAPI has no schema {name}.")
        wanted.append(name)
        pending.extend(REF.findall(json.dumps(schemas[name])))
    return {
        "_comment": "Extracted by scripts/extract_schemas.py from the typesearch OpenAPI. Do not edit by hand.",
        "openapi_version": openapi.get("info", {}).get("version"),
        "components": {"schemas": {name: strip(schemas[name]) for name in sorted(wanted)}},
    }


def render(fixture: dict[str, Any]) -> str:
    """Un esquema por línea: chico y con diffs legibles."""
    schemas = fixture["components"]["schemas"]
    compact = {"separators": (",", ":"), "sort_keys": True, "ensure_ascii": False}
    lines = [
        "{",
        f' "_comment": {json.dumps(fixture["_comment"])},',
        f' "openapi_version": {json.dumps(fixture["openapi_version"])},',
        ' "components": {"schemas": {',
        ",\n".join(f"  {json.dumps(name)}: {json.dumps(schema, **compact)}" for name, schema in schemas.items()),  # type: ignore[arg-type]
        " }}",
        "}",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", help="an OpenAPI JSON file")
    parser.add_argument("--fetch", action="store_true", help=f"read {LIVE}")
    parser.add_argument("--check", action="store_true", help="fail if the fixture is out of date")
    args = parser.parse_args()
    if args.fetch:
        with urllib.request.urlopen(LIVE, timeout=30) as response:  # noqa: S310 (a fixed https URL)
            openapi = json.load(response)
    elif args.source:
        openapi = json.loads(Path(args.source).read_text(encoding="utf-8"))
    else:
        parser.error("pass an OpenAPI file or --fetch")
    text = render(extract(openapi))
    if args.check:
        if OUT.read_text(encoding="utf-8") != text:
            sys.exit(f"{OUT.name} is out of date: run scripts/extract_schemas.py")
        print(f"{OUT.name} is up to date.")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT} ({len(text) // 1024} KB).")


if __name__ == "__main__":
    main()
