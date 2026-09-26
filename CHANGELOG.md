# Changelog

All notable changes to the typesearch plugin for Dify are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [0.1.0] - Unreleased

First release.

- Three read-only tools with the same parameters and output as the typesearch MCP server: `search_news`,
  `get_contents` and `find_similar`.
- `find_similar` also takes `countries` and `languages`, set in the tool settings, never by the model.
- Compact output for agents: readable text plus the same data as JSON, without empty fields.
- Errors the model can act on (`Error (code): message`), without the API key; invalid parameters are
  explained before calling the API.
- The API key is checked with a free call when it is saved.
- Labels and descriptions in English, Simplified Chinese, Japanese and Brazilian Portuguese.
