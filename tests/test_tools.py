"""Cada herramienta, como la llama Dify (la clase que carga PluginRegistration y su ``invoke``), contra la
API falsa: el pedido que sale, la salida (texto y JSON) y los errores."""

from __future__ import annotations

from typing import Any

import pytest
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.tool import ToolInvokeMessage

from .conftest import jsons, texts
from .fake_api import KEY, FakeApi, Scripted, problem, result, search_response

CREDENTIALS = {"typesearch_api_key": KEY}


def call(
    registration: PluginRegistration, tool: str, params: dict[str, Any], credentials: dict[str, Any] | None = None
) -> list[ToolInvokeMessage]:
    cls = registration.get_tool_cls("typesearch", tool)
    assert cls is not None, tool
    return list(cls.from_credentials(CREDENTIALS if credentials is None else credentials).invoke(params))


def only_text(messages: list[ToolInvokeMessage]) -> str:
    assert len(messages) == 1 and not jsons(messages), messages
    return texts(messages)[0]


# --- search_news -------------------------------------------------------------------------------


def test_search_defaults_and_compact_output(registration: PluginRegistration, api: FakeApi) -> None:
    messages = call(registration, "search_news", {"query": "el dólar"})
    assert api.last.method == "POST" and api.last.path == "/v1/search"
    assert api.last.body == {"query": "el dólar", "mode": "fast", "max_results": 10}
    assert api.last.headers["authorization"] == f"Bearer {KEY}"
    assert api.last.headers["user-agent"].startswith("typesearch-dify-plugin/")

    assert [m.type for m in messages] == [ToolInvokeMessage.MessageType.TEXT, ToolInvokeMessage.MessageType.JSON]
    text = texts(messages)[0]
    assert text.split("\n")[0] == '2 results for "el dólar" · fast · US$0.0011'
    assert (
        "1. El dólar cerró estable por 1ª rueda\nDiario Ejemplo · 2026-09-21 18:05 UTC · AR/es\nhttps://diarioejemplo.example/economia/nota-1"
        in text
    )
    assert "found beyond the index" in text
    assert "> El dólar mayorista terminó la jornada sin variaciones" in text

    data = jsons(messages)[0]
    assert data["query"] == "el dólar" and data["mode"] == "fast" and data["cost_usd"] == 0.00111 and data["request_id"] == "req_fakedify1"
    assert data["results"][0] == {
        "title": "El dólar cerró estable por 1ª rueda",
        "url": "https://diarioejemplo.example/economia/nota-1",
        "source": "Diario Ejemplo",
        "published_at": "2026-09-21T18:05Z",
        "country": "AR",
        "language": "es",
        "snippet": "La divisa se mantuvo sin cambios frente al cierre anterior.",
        "score": 0.95,
    }
    assert data["results"][1]["found_in"] == "discovery"
    assert data["results"][1]["highlights"] == ["El dólar mayorista terminó la jornada sin variaciones"]
    assert "near_misses" not in data and "warnings" not in data and "incomplete" not in data


def test_search_passes_every_filter_as_the_api_names_it(registration: PluginRegistration, api: FakeApi) -> None:
    messages = call(
        registration,
        "search_news",
        {
            "query": "inflation",
            "mode": "normal",
            "max_results": 25.0,  # Dify manda los números como float
            "days": "3",  # o como texto, desde una variable de workflow
            "published_after": "2026-09-20",
            "published_before": "2026-09-22T12:00Z",
            "include_domains": "diarioejemplo.example, reddiaria.example/economia",
            "exclude_domains": "otro.example\nhttps://www.tercero.example",
            "countries": "AR, UY",
            "languages": '["es", "pt"]',
        },
    )
    assert len(messages) == 2
    assert api.last.body == {
        "query": "inflation",
        "mode": "normal",
        "max_results": 25,
        "days": 3,
        "published_after": "2026-09-20",
        "published_before": "2026-09-22T12:00:00Z",
        "include_domains": ["diarioejemplo.example", "reddiaria.example/economia"],
        "exclude_domains": ["otro.example", "https://www.tercero.example"],
        "countries": ["AR", "UY"],
        "languages": ["es", "pt"],
    }


def test_search_leaves_out_empty_optional_fields(registration: PluginRegistration, api: FakeApi) -> None:
    # Un workflow manda los campos sin completar como "" o None.
    call(
        registration,
        "search_news",
        {"query": " el dólar ", "mode": "", "max_results": None, "days": "", "countries": " ", "include_domains": None},
    )
    assert api.last.body == {"query": "el dólar", "mode": "fast", "max_results": 10}


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({}, "query is required"),
        ({"query": "x"}, "query needs at least two letters."),
        ({"query": "a" * 201}, "query is too long: 200 characters at most."),
        ({"query": "el dólar", "max_results": 30}, "max_results must be a whole number from 1 to 25."),
        ({"query": "el dólar", "max_results": 2.5}, "max_results must be a whole number from 1 to 25."),
        ({"query": "el dólar", "days": 0}, "days must be a whole number from 1 to 365."),
        ({"query": "el dólar", "mode": "turbo"}, "mode must be ultra, fast, normal or deep."),
        ({"query": "el dólar", "published_after": "yesterday"}, "published_after must be a date"),
        ({"query": "el dólar", "published_before": "2026-02-30"}, "published_before must be a date"),
        ({"query": "el dólar", "published_after": "2026-09-25T14:00:00"}, "published_after must be a date"),
        ({"query": "el dólar", "include_domains": "not a domain"}, 'include_domains: "not" is not valid'),
        ({"query": "el dólar", "exclude_domains": ",".join(f"d{i}.example" for i in range(21))}, "exclude_domains: 20 domains at most."),
        ({"query": "el dólar", "languages": ",".join(f"l{i}" for i in range(21))}, "languages: 20 codes at most."),
    ],
)
def test_search_explains_invalid_parameters_without_calling_the_api(
    registration: PluginRegistration, api: FakeApi, params: dict[str, Any], message: str
) -> None:
    text = only_text(call(registration, "search_news", params))
    assert text.startswith("Error (invalid_request): ")
    assert message in text
    assert api.requests == []


def test_search_nothing_found_near_misses_incomplete_and_cached(registration: PluginRegistration, api: FakeApi) -> None:
    api.next(
        Scripted(
            body=search_response(
                found=False,
                total=0,
                results=[],
                near_misses=[result(1)],
                incomplete=True,
                cached_at="2026-09-22T14:00:00Z",
                warnings=[{"code": "domain_not_indexed", "message": "x.example is not in the index."}],
            )
        )
    )
    messages = call(registration, "search_news", {"query": "el dólar"})
    text = texts(messages)[0]
    assert text.startswith('No results for "el dólar" · fast · cached, free')
    assert "Closest articles, which may not be about it:" in text
    assert "Incomplete:" in text
    assert "Note (domain_not_indexed): x.example is not in the index." in text
    data = jsons(messages)[0]
    assert data["results"] == [] and data["incomplete"] is True and data["cached"] is True
    assert data["near_misses"][0]["url"] == "https://diarioejemplo.example/economia/nota-1"


# --- get_contents, find_similar, check_coverage --------------------------------------------------


def test_contents_each_url_with_its_status(registration: PluginRegistration, api: FakeApi) -> None:
    messages = call(
        registration,
        "get_contents",
        {"urls": "https://reddiaria.example/a,https://unreachable.example/b", "query": "el Presupuesto 2027"},
    )
    assert api.last.path == "/v1/contents"
    assert api.last.body == {"urls": ["https://reddiaria.example/a", "https://unreachable.example/b"], "query": "el Presupuesto 2027"}
    text = texts(messages)[0]
    assert text.split("\n")[0] == "1 of 2 URLs read · US$0.0002"
    assert "> El proyecto prevé un superávit primario\nRelevance to the query: 0.97" in text
    assert "Error (site_unreachable): The site did not answer." in text
    data = jsons(messages)[0]
    assert "highlights" not in data["results"][0]  # el fragmento no se repite
    assert data["results"][1] == {
        "url": "https://unreachable.example/b",
        "status": "error",
        "error": {"code": "site_unreachable", "message": "The site did not answer."},
    }


def test_contents_splits_urls_on_lines_and_keeps_commas_inside_urls(registration: PluginRegistration, api: FakeApi) -> None:
    call(registration, "get_contents", {"urls": "https://reddiaria.example/a,b-c\n https://reddiaria.example/d \n"})
    assert api.last.body == {"urls": ["https://reddiaria.example/a,b-c", "https://reddiaria.example/d"]}


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({}, "urls needs at least one URL."),
        ({"urls": "reddiaria.example/a"}, "is not an article URL"),
        ({"urls": ", ".join(f"https://reddiaria.example/{i}" for i in range(11))}, "urls: 10 at most."),
        ({"urls": "https://reddiaria.example/a", "query": "x"}, "query needs at least two letters."),
    ],
)
def test_contents_invalid_parameters(registration: PluginRegistration, api: FakeApi, params: dict[str, Any], message: str) -> None:
    assert message in only_text(call(registration, "get_contents", params))
    assert api.requests == []


def test_similar_uses_mode_fast_and_shows_the_reference(registration: PluginRegistration, api: FakeApi) -> None:
    messages = call(registration, "find_similar", {"url": "https://diarioejemplo.example/a", "days": 30})
    assert api.last.path == "/v1/similar"
    assert api.last.body == {"url": "https://diarioejemplo.example/a", "mode": "fast", "max_results": 10, "days": 30}
    assert texts(messages)[0].startswith('2 similar articles to "Inflación: qué esperan los analistas" · US$0.0011')
    data = jsons(messages)[0]
    assert data["reference"] == {"title": "Inflación: qué esperan los analistas", "url": "https://diarioejemplo.example/a"}


def test_similar_with_the_countries_and_languages_of_the_app(registration: PluginRegistration, api: FakeApi) -> None:
    call(registration, "find_similar", {"url": "https://diarioejemplo.example/a", "countries": "AR, UY", "languages": "es"})
    assert api.last.body == {
        "url": "https://diarioejemplo.example/a",
        "mode": "fast",
        "max_results": 10,
        "countries": ["AR", "UY"],
        "languages": ["es"],
    }


def test_similar_with_nothing_found(registration: PluginRegistration, api: FakeApi) -> None:
    api.next(
        Scripted(
            body=search_response(
                object="similar",
                found=False,
                total=0,
                results=[],
                reference={"url": "https://diarioejemplo.example/a", "title": "Una nota"},
            )
        )
    )
    messages = call(registration, "find_similar", {"url": "https://diarioejemplo.example/a"})
    assert texts(messages)[0].startswith('No similar articles to "Una nota" · US$0.0011')
    assert jsons(messages)[0]["results"] == []


def test_similar_needs_a_url(registration: PluginRegistration, api: FakeApi) -> None:
    assert "url is required" in only_text(call(registration, "find_similar", {}))
    assert "is not an article URL" in only_text(call(registration, "find_similar", {"url": "not a url"}))
    assert api.requests == []


def test_coverage_one_domain_or_the_aggregate(registration: PluginRegistration, api: FakeApi) -> None:
    yes = call(registration, "check_coverage", {"domain": "diarioejemplo.example"})
    assert api.last.method == "GET" and api.last.query == {"domain": ["diarioejemplo.example"]}
    assert (
        texts(yes)[0] == "diarioejemplo.example is covered (Diario Ejemplo): AR · es · 1,520 articles · last refreshed 2026-09-22T14:05Z."
    )

    no = call(registration, "check_coverage", {"domain": "otro.example"})
    assert texts(no)[0] == "otro.example is not covered by the index."
    assert jsons(no)[0] == {"domain": "otro.example", "covered": False}

    everything = call(registration, "check_coverage", {"domain": ""})
    assert api.last.query == {}
    text = texts(everything)[0]
    assert "The index has 1,234 sources and 567,890 articles." in text
    assert "Sources by country: AR 120, international 4." in text
    assert "Sources by language: es 900, en 334." in text
    assert jsons(everything)[0]["by_language"] == [{"language": "es", "sources": 900}, {"language": "en", "sources": 334}]


# --- Errores -------------------------------------------------------------------------------------


def test_without_a_key_nothing_is_sent(registration: PluginRegistration, api: FakeApi) -> None:
    for credentials in ({}, {"typesearch_api_key": "  "}):
        text = only_text(call(registration, "search_news", {"query": "el dólar"}, credentials))
        assert text.startswith("Error (missing_api_key): Missing API key.")
        assert "Get one at app.typesearch.ai." in text
    assert api.requests == []


def test_api_errors_reach_the_model_with_code_wait_and_request_id_never_the_key(registration: PluginRegistration, api: FakeApi) -> None:
    wrong = "ts_live_wrong_key_123"
    text = only_text(call(registration, "search_news", {"query": "el dólar"}, {"typesearch_api_key": wrong}))
    assert text == "Error (invalid_api_key): The API key is not valid. [request req_fakeerr1]"
    assert wrong not in text

    # 429 con Retry-After corto: reintenta una vez y responde.
    api.next(Scripted(429, problem(429, "rate_limited", "More than 600 requests per minute."), {"Retry-After": "2"}))
    assert len(call(registration, "search_news", {"query": "el dólar"})) == 2

    # 429 con una espera larga: no espera, se lo dice al modelo.
    api.next(Scripted(429, problem(429, "rate_limited", "More than 600 requests per minute."), {"Retry-After": "30"}))
    assert only_text(call(registration, "search_news", {"query": "el dólar"})) == (
        "Error (rate_limited): More than 600 requests per minute. Retry after 30 s. [request req_fakeerr1]"
    )

    api.next(Scripted(402, problem(402, "insufficient_credits", "No credit left. Top up at https://app.typesearch.ai/billing.")))
    assert only_text(call(registration, "get_contents", {"urls": "https://reddiaria.example/a"})).startswith(
        "Error (insufficient_credits): No credit left. Top up at https://app.typesearch.ai/billing."
    )

    # La cuota diaria no se reintenta.
    api.reset()
    api.next(
        Scripted(429, problem(429, "quota_exceeded", "Daily token quota reached."), {"Retry-After": "1"}), Scripted(body=search_response())
    )
    assert only_text(call(registration, "search_news", {"query": "el dólar"})).startswith("Error (quota_exceeded):")
    assert len(api.requests) == 1


def test_server_errors_are_retried_once(registration: PluginRegistration, api: FakeApi) -> None:
    api.next(Scripted(503, problem(503, "shutting_down", "The server is restarting.")))
    assert len(call(registration, "search_news", {"query": "el dólar"})) == 2
    assert len(api.requests) == 2

    api.reset()
    api.next(Scripted(502, raw="<html>Bad gateway</html>"), Scripted(502, raw="<html>Bad gateway</html>"))
    assert only_text(call(registration, "check_coverage", {})) == (
        "Error (http_502): the typesearch API failed (status 502). Try again in a moment. [request req_fakescr1]"
    )
    assert len(api.requests) == 2


def test_the_api_validation_errors_list_every_field(registration: PluginRegistration, api: FakeApi) -> None:
    errors = [
        {"path": "countries.0", "message": "«ZZ» is not an ISO 3166-1 alpha-2 code."},
        {"path": "languages.0", "message": "«xx» is not an ISO 639-1 code."},
    ]
    api.next(Scripted(400, problem(400, "invalid_request", "countries.0: «ZZ» is not an ISO 3166-1 alpha-2 code.", errors=errors)))
    text = only_text(call(registration, "search_news", {"query": "el dólar", "countries": "ZZ", "languages": "xx"}))
    assert text == (
        "Error (invalid_request): countries.0: «ZZ» is not an ISO 3166-1 alpha-2 code. "
        "Also: languages.0: «xx» is not an ISO 639-1 code. [request req_fakeerr1]"
    )


def test_network_failures_are_plain_sentences(registration: PluginRegistration, api: FakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    from typesearch_plugin import api as api_module

    api.next(Scripted(destroy=True))
    assert (
        only_text(call(registration, "check_coverage", {}))
        == "Error (connection): the connection to the typesearch API was interrupted. Try again."
    )

    monkeypatch.setattr(api_module, "TIMEOUT", 0.3)
    api.next(Scripted(delay=1.5, body=search_response()))
    assert only_text(call(registration, "search_news", {"query": "el dólar"})) == (
        "Error (timeout): typesearch took too long to answer. Try again, or use a lighter mode."
    )

    monkeypatch.setattr(api_module, "BASE_URL", "http://127.0.0.1:9")
    assert only_text(call(registration, "check_coverage", {})) == (
        "Error (connection): could not reach the typesearch API. Check the network connection and try again."
    )
