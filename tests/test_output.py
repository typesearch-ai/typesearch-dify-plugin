"""Las utilidades de la salida compacta: las mismas reglas que src/format.ts del MCP."""

from __future__ import annotations

from typesearch_plugin import output, params


def test_compact_drops_what_says_nothing() -> None:
    assert output.compact({"a": None, "b": "", "c": [], "d": 0, "e": False, "f": "x", "g": [1]}) == {"d": 0, "e": False, "f": "x", "g": [1]}


def test_shorten_cuts_at_a_word_with_an_ellipsis() -> None:
    assert output.shorten("  one   two\nthree ", 300) == "one two three"
    text = "word " * 100
    short = output.shorten(text, 300)
    assert len(short) <= 300 and short.endswith("word…")
    assert output.shorten("x" * 400, 300) == "x" * 299 + "…"


def test_dates_to_the_minute_in_utc() -> None:
    assert output.to_minute("2026-09-21T18:05:31.000Z") == "2026-09-21T18:05Z"
    assert output.to_minute("2026-09-21T15:05:31-03:00") == "2026-09-21T18:05Z"
    assert output.to_minute("2026-09-21") == "2026-09-21T00:00Z"
    assert output.to_minute("not a date") == "not a date"
    assert output.to_minute(None) is None and output.to_minute("") is None


def test_rounding_like_javascript() -> None:
    assert output.round2(0.9512) == 0.95
    assert output.round2(0.125) == 0.13  # la mitad sube, como Math.round
    assert output.round2(1) == 1.0


def test_cost_line() -> None:
    assert output.cost({"cost_usd": 0.00111}) == "US$0.0011"
    assert output.cost({"cost_usd": 0.001, "cached": True}) == "cached, free"


def test_dates_are_normalized_for_the_api() -> None:
    assert params._date("2026-09-25", "d") == "2026-09-25"
    assert params._date("2026-09-25T14:00Z", "d") == "2026-09-25T14:00:00Z"
    assert params._date("2026-09-25t14:00:05.5+02:00", "d") == "2026-09-25T14:00:05.5+02:00"


def test_lists_accept_commas_lines_json_and_lists() -> None:
    split = params.LIST_SPLIT_RE
    assert params._items("AR, UY;BR\nCL", "c", split) == ["AR", "UY", "BR", "CL"]
    assert params._items('["es", "pt", "es"]', "c", split) == ["es", "pt"]
    assert params._items(["es", " en "], "c", split) == ["es", "en"]
