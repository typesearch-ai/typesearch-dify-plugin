# typesearch

**News search for AI agents.** Recent news on any topic from outlets worldwide, judged by a calibrated
relevance model, with filters by date, domain, country and language. Each result carries its title, link,
source, date, country and language, a relevance score and short excerpts, never the full article, so your
agent cites the link.

- **Author:** typesearch
- **Type:** tool
- **Source repository:** https://github.com/typesearch-ai/typesearch-dify-plugin
- **Contact:** support@typesearch.ai

## Tools

| Tool | What it does |
| --- | --- |
| **Search news** (`search_news`) | News on a topic, with a relevance score per article. Parameters: `query` (required), `mode` (`ultra`, `fast`, `normal` or `deep`; `fast` by default), `max_results` (1 to 25, 10 by default), `days` (the last N days, 7 by default), `published_after`, `published_before`, `include_domains`, `exclude_domains`, `countries` (ISO 3166-1 alpha-2 codes, such as `AR, US`), `languages` (ISO 639-1 codes, such as `es, en`). |
| **Get article contents** (`get_contents`) | Title, standfirst, date, source and a short verbatim excerpt (up to 25 words) of up to 10 article URLs. With `query`, the excerpt is the one about it, with a relevance score. Never the full text. |
| **Find similar news** (`find_similar`) | Other coverage of the story in an article URL: `url` (required), `max_results`, `days`. |
| **Check index coverage** (`check_coverage`) | Whether a news domain is covered (`domain`), or how many sources the index has per country and language. Free. |

Every tool is read-only. Lists (domains, countries, languages, URLs) are text separated by commas or line
breaks, so they work the same when the model fills them in and when you map a workflow variable.

**Modes.** `fast` (default) judges headlines and standfirsts and is the cheapest; `ultra` judges headlines
only; `normal` also reads the best matches; `deep` reads more and also finds the topic in other words. Use
`fast` unless it finds too little.

## Setup

1. Get an API key at [app.typesearch.ai](https://app.typesearch.ai) (keys start with `ts_live_`).
2. In Dify, install **typesearch** from the Marketplace (**Plugins → Explore Marketplace**), or upload the
   package (**Plugins → Install plugin → Local package file**).
3. Open **Tools → typesearch → Authorize** (or the plugin's settings), paste the API key and save. Dify
   checks the key with a free call before saving it.

Requires Dify 1.14.2 or later (Cloud, Community or Enterprise).

## Usage

### In an Agent app or an Agent node

Add the typesearch tools in the app's **Tools** section. The model reads each tool's description and picks
one: *Search news* for current events, *Get article contents* to read a link, *Find similar news* for
other coverage of a story, and *Check index coverage* to see what is indexed. For example:

> What did outlets in Argentina report this week about inflation? Answer in English and cite the links.

The agent can call `search_news` with `query: "inflation"`, `countries: "AR"` and `days: 7`, and answer
from the results, citing each link.

### In a Workflow or Chatflow

Add a **Tool** node → **typesearch** → **Search news**, and map `query` to a variable (such as the user's
question). The node has two outputs:

- `text`: a readable list of the results, ready for an LLM node.
- `json`: the same data, for code or iteration nodes:

```json
{
  "query": "el dólar",
  "mode": "fast",
  "results": [
    {
      "title": "El dólar cerró estable",
      "url": "https://diarioejemplo.example/economia/nota-1",
      "source": "Diario Ejemplo",
      "published_at": "2026-09-21T18:05Z",
      "country": "AR",
      "language": "es",
      "snippet": "La divisa se mantuvo sin cambios frente al cierre anterior.",
      "score": 0.95
    }
  ],
  "request_id": "req_…"
}
```

Fields without a value are left out to save tokens. `score` is the probability that the article is about
the query, and `cost_usd` what the call cost. When nothing matches, `results` is empty and `near_misses`
lists the closest articles.

### Errors

When a call fails, the tool answers with a single text line that the model can act on, such as
`Error (invalid_api_key): The API key is not valid.` or
`Error (rate_limited): … Retry after 12 s.` Invalid parameters are explained before anything is sent.
The API key never appears in a message. Failed calls are free.

## API key and billing

Every call uses the credit of the typesearch account that owns the API key, like the REST API: see
[typesearch.ai/pricing](https://typesearch.ai/pricing). *Check index coverage* and the key check are
free, and so are cached results and failed calls. You can see each request, its cost and your balance in
the [dashboard](https://app.typesearch.ai).

## Connection requirements

The plugin calls one endpoint only: `https://api.typesearch.ai` (HTTPS, port 443). On a self-hosted Dify,
the plugin daemon needs outbound access to that host. Most calls take a few seconds; a `deep` search can
take about a minute.

## Privacy

The plugin sends the query, the filters and the article URLs you ask about, with your API key, to the
typesearch API, and stores nothing. See [PRIVACY.md](PRIVACY.md) and the
[typesearch privacy policy](https://typesearch.ai/privacy).

## Development

In the [source repository](https://github.com/typesearch-ai/typesearch-dify-plugin):

```bash
uv sync                      # Python 3.12
uv run pytest                # the tools against a fake API, with no network
uv run ruff check . && uv run ruff format --check . && uv run mypy
dify plugin package . -o typesearch-0.1.0.difypkg
```

To debug against a Dify instance, copy `.env.example` to `.env`, paste the debugging URL and key that
Dify shows under **Plugins → Debug**, and run `uv run python -m main`.

## License

[MIT](LICENSE)
