# Privacy Policy: typesearch plugin for Dify

Last updated: 2026-09-25

This plugin connects Dify to the typesearch news search API at `api.typesearch.ai`, run by typesearch.

## What the plugin sends, and where

When one of its tools runs, the plugin sends over HTTPS to `https://api.typesearch.ai`, and to no other
service:

- your typesearch API key, in the `Authorization` header, to authenticate the request;
- the tool's inputs: the search query and its filters (mode, number of results, dates, domains, countries
  and languages), or the article URLs you ask about.

When you save the API key in Dify, the plugin makes one free call to the API to check that the key works.

## What the plugin collects or stores

The plugin does not collect, store or log any user data. It has no analytics or telemetry and keeps
nothing between calls. Dify keeps the API key in its own credential storage; the plugin only reads it to
call the API. The results the tools return go back to your Dify app, which handles them under your Dify
instance's own policies.

## What typesearch does with the data it receives

typesearch processes each request under its privacy policy, <https://typesearch.ai/privacy>. In short:

- The queries and parameters are kept in the request logs for 7 days; the rest of each request record
  (time, key, endpoint, status and cost) for 35 days, for billing and support.
- To judge how relevant each article is and, when its index falls short, to find other news sites that may
  cover the topic, typesearch sends the query (and the candidate articles) to language model providers
  through Vercel AI Gateway, a third-party service ([Vercel's privacy policy](https://vercel.com/legal/privacy-policy)).
- Like any server, typesearch's servers keep short-lived technical logs, such as the IP address of the Dify
  server that makes the request.
- typesearch does not sell your queries.

Avoid putting personal data in queries unless your use case needs it.

## Contact

For privacy questions or requests, write to privacy@typesearch.ai.
