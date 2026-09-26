"""El plugin como paquete: manifest y YAML válidos para Dify (los carga el propio dify_plugin), el mismo
contrato que el MCP de typesearch, y lo que pide la revisión del Marketplace (langgenius/dify-plugins)."""

from __future__ import annotations

import re
import tomllib
from typing import Any

import yaml
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.tool import ToolParameter

from typesearch_plugin import VERSION

from .conftest import ROOT

LOCALES = ("en_US", "zh_Hans", "ja_JP", "pt_BR")  # los idiomas que admite Dify (no hay es_ES)
CONTRACT = {
    "search_news": [
        "query",
        "mode",
        "max_results",
        "days",
        "published_after",
        "published_before",
        "include_domains",
        "exclude_domains",
        "countries",
        "languages",
    ],
    "get_contents": ["urls", "query"],
    "find_similar": ["url", "max_results", "days"],
}
# Los que fija quien arma la app (form: form), además de los del MCP: el modelo no los ve.
DEVELOPER = {"find_similar": ["countries", "languages"]}
REQUIRED = {"search_news": ["query"], "get_contents": ["urls"], "find_similar": ["url"]}
# Lo que el paquete publica (lo que no ignora .difyignore): el texto que ven usuarios y revisores.
PUBLIC = ["README.md", "PRIVACY.md", "manifest.yaml", "provider/typesearch.yaml", *[f"tools/{t}.yaml" for t in CONTRACT]]


def load(path: str) -> Any:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def i18n_objects(node: Any, path: str = "") -> list[tuple[str, dict[str, str]]]:
    """Todos los textos traducibles (label, description, human, human_description, help, placeholder)."""
    found: list[tuple[str, dict[str, str]]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if (
                key in ("label", "description", "human", "human_description", "help", "placeholder")
                and isinstance(value, dict)
                and "en_US" in value
            ):
                found.append((f"{path}.{key}", value))
            else:
                found.extend(i18n_objects(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            found.extend(i18n_objects(value, f"{path}[{i}]"))
    return found


# --- Dify lo carga ---------------------------------------------------------------------------------


def test_dify_plugin_loads_the_manifest_the_provider_and_the_three_tools(registration: PluginRegistration) -> None:
    assert registration.configuration.name == "typesearch"
    assert registration.configuration.author == "typesearch"
    assert registration.configuration.version == VERSION
    assert registration.get_tool_provider_cls("typesearch").__name__ == "TypesearchProvider"  # type: ignore[union-attr]
    provider, _, tools = registration.tools_mapping["typesearch"]
    assert list(tools) == list(CONTRACT)
    assert [c.name for c in provider.credentials_schema] == ["typesearch_api_key"]
    credential = provider.credentials_schema[0]
    assert credential.type.value == "secret-input" and credential.required
    assert credential.url == "https://app.typesearch.ai"
    assert {t.value for t in provider.identity.tags} == {"search", "news"}
    assert {f.filename for f in registration.files} == {"icon.svg", "icon-dark.svg"}


def test_the_same_parameters_as_the_mcp(registration: PluginRegistration) -> None:
    _, _, tools = registration.tools_mapping["typesearch"]
    for name, (config, _cls) in tools.items():
        assert [p.name for p in config.parameters] == CONTRACT[name] + DEVELOPER.get(name, [])
        assert [p.name for p in config.parameters if p.required] == REQUIRED[name]
        for p in config.parameters:
            if p.name in DEVELOPER.get(name, []):
                assert p.form == ToolParameter.ToolParameterForm.FORM, (name, p.name)  # los fija quien arma la app
                continue
            assert p.form == ToolParameter.ToolParameterForm.LLM, (name, p.name)  # el modelo los completa
            assert p.llm_description and len(p.llm_description) > 20, (name, p.name)
        assert len(config.description.llm) > 80
    search = {p.name: p for p in tools["search_news"][0].parameters}
    assert search["mode"].type == ToolParameter.ToolParameterType.SELECT
    assert [o.value for o in search["mode"].options or []] == ["ultra", "fast", "normal", "deep"]
    assert search["mode"].default == "fast"
    assert (search["max_results"].default, search["max_results"].min, search["max_results"].max) == (10, 1, 25)
    assert (search["days"].min, search["days"].max) == (1, 365)


def test_the_yaml_follows_the_daemon_rules() -> None:
    """Lo que valida el plugin daemon al instalar (validate:"required…" en sus structs de Go)."""
    provider = load("provider/typesearch.yaml")
    assert re.fullmatch(r"[a-zA-Z0-9_-]+", provider["identity"]["name"])
    for path in provider["tools"]:
        tool = load(path)
        assert re.fullmatch(r"[a-zA-Z0-9_-]+", tool["identity"]["name"])
        assert tool["extra"]["python"]["source"] == path.replace(".yaml", ".py")
        assert (ROOT / tool["extra"]["python"]["source"]).is_file()
        for p in tool["parameters"]:
            assert {"name", "label", "human_description", "type", "form"} <= set(p), p["name"]
            assert p["type"] in ("string", "number", "boolean", "select")
            assert p["form"] in ("llm", "form")


def test_every_text_has_the_four_dify_languages_and_fits() -> None:
    for path in ("manifest.yaml", "provider/typesearch.yaml", *[f"tools/{t}.yaml" for t in CONTRACT]):
        for where, text in i18n_objects(load(path)):
            if ".options[" in where:
                continue  # los modos se llaman igual en todos los idiomas
            assert set(text) == set(LOCALES), (path, where, set(text))
            for locale, value in text.items():
                assert isinstance(value, str) and 0 < len(value) < 1024, (path, where, locale)


# --- Lo que pide el Marketplace ----------------------------------------------------------------------


def test_manifest_has_what_the_marketplace_review_requires() -> None:
    m = load("manifest.yaml")
    for key in ("author", "name", "version", "type", "icon", "plugins", "privacy", "repo", "contact"):
        assert m.get(key), key
    assert m["type"] == "plugin"
    assert "dify" not in m["author"] and "langgenius" not in m["author"]
    assert re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+", m["repo"])
    assert re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]+", m["contact"])
    assert m["meta"]["runner"] == {"language": "python", "version": "3.12", "entrypoint": "main"}
    assert m["meta"]["minimum_dify_version"]
    assert m["network"] == {"domains": ["api.typesearch.ai"]}
    assert (ROOT / m["privacy"]).is_file()
    for icon in (m["icon"], m["icon_dark"]):
        svg = (ROOT / "_assets" / icon).read_text(encoding="utf-8")
        assert svg.startswith("<svg") and "DIFY_MARKETPLACE_TEMPLATE_ICON_DO_NOT_USE" not in svg


def test_versions_match() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert load("manifest.yaml")["version"] == project["version"] == VERSION
    assert f"## [{VERSION}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_requirements_match_pyproject_and_are_bounded() -> None:
    """Dify instala requirements.txt; pyproject.toml es sólo para desarrollar. Tienen que decir lo mismo."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lines = [
        line.strip()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert lines == project["dependencies"]
    for line in lines:
        assert re.search(r">=[\d.]+,<[\d.]+$", line), line  # piso y techo: la revisión avisa si falta el techo
    assert lines[0].startswith("dify_plugin>=0.10")  # el Marketplace exige dify_plugin >= 0.9.0


def test_readme_and_privacy_are_ready_for_review() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "https://github.com/typesearch-ai/typesearch-dify-plugin" in readme
    assert not re.search(r"[㐀-䶿一-鿿]", re.sub(r"```.*?```", "", readme, flags=re.DOTALL))  # README en inglés
    for word in ("Setup", "Usage", "API key", "Connection"):
        assert word in readme
    privacy = (ROOT / "PRIVACY.md").read_text(encoding="utf-8").lower()
    assert "please fill in the privacy policy" not in privacy
    assert "api.typesearch.ai" in privacy and "does not collect" in privacy


def test_the_package_leaves_out_development_files() -> None:
    ignore = (ROOT / ".difyignore").read_text(encoding="utf-8").splitlines()
    for entry in (
        ".git",
        "tests/",
        "scripts/",
        ".github/",
        "pyproject.toml",
        "uv.lock",
        ".env",
        ".venv/",
        "__pycache__/",
        "*.difypkg",
        "PUBLICAR.md",
        "PR-dify-plugins.md",
    ):
        assert entry in ignore, entry


def test_public_text_has_no_prices_and_only_example_outlets() -> None:
    """Sin precios (están en typesearch.ai/pricing), sin medios reales: los ejemplos usan dominios .example."""
    host = re.compile(
        r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|info|news|io|co|tv|fm|ar|br|mx|es|uk|us|cl|uy|pe|de|fr|it)(?:\.[a-z]{2})?\b", re.IGNORECASE
    )
    allowed = ("typesearch.ai", "dify.ai", "github.com", "example.com", "example.org", "keepachangelog.com", "semver.org", "vercel.com")
    for path in PUBLIC:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert not re.search(r"(US)?\$\s?\d", text), path
        for found in host.findall(text):
            assert found.lower().endswith(allowed), (path, found)


def test_public_text_offers_no_index_coverage() -> None:
    """La cobertura del índice no es pública: ni /v1/sources, ni check_coverage, ni cuántos medios o notas hay."""
    for path in [*PUBLIC, "CHANGELOG.md", "PR-dify-plugins.md"]:
        text = (ROOT / path).read_text(encoding="utf-8")
        assert not re.search(r"/v1/sources|check.?coverage|index coverage", text, re.IGNORECASE), path
        assert not re.search(r"\d[\d,.]*\+?\s+(sources|outlets|articles indexed)", text, re.IGNORECASE), path
