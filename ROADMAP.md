# AI-Server Roadmap

Goal: turn this from a Flask wrapper around one local sentiment model into what it
is supposed to be — an async LLM gateway that fronts OpenAI, Anthropic and Google
behind a single REST interface, with streaming, Pydantic validation, per-client
rate limiting, and **measured** performance numbers.

One increment per working day. Each item is self-contained, keeps `main` green, and
is meant to be defensible in an interview on its own.

**Working agreement for the daily automation**

- Do the next unchecked item, and only that item.
- Tests must pass before committing. If an item turns out to be bigger than a day,
  split it in place and do the first half.
- Every commit updates this file (check the box) and appends 2 lines to
  `docs/dev-log.md` saying what changed and why.
- Never commit secrets, API keys, or `.env`.
- No provider network calls in CI. `MockProvider` is what tests run against.

---

## Phase 0 — Make CI honest and green (8 days)

The workflow currently runs `python -m pytest`, but `pytest` is not in
`requirements.txt` and `test_server.py` does live HTTP against `localhost:5000`.
CI cannot be passing. Nothing else matters until this is true.

- [x] 1. Split dependencies: `requirements.txt` (runtime) and `requirements-dev.txt` (pytest, ruff, httpx). Pin versions.
- [x] 2. Rewrite `test_server.py` as real pytest tests using Flask's `test_client`, with the model faked. No live server, no network.
- [x] 3. Break the import-time side effect: `ModelHandler()` runs on import of `app.server`, so importing the app downloads a model. Move it behind a factory/lazy accessor so tests import instantly.
- [x] 4. Modernize the workflow: `actions/checkout@v4`, `actions/setup-python@v5`, pip caching, Python 3.11 + 3.12 matrix.
- [x] 5. Add `ruff` config in `pyproject.toml` and a lint job; fix what it flags.
- [x] 6. Add `LICENSE` (README claims MIT, the file does not exist) and `.env.example`.
- [x] 7. Fix the README: real clone URL (it still says `YOUR-USERNAME`), correct test instructions, CI badge.
- [ ] 8. Add `CONTRIBUTING.md` with the local dev loop, and a `Makefile` for `make test` / `make lint` / `make run`.

## Phase 1 — FastAPI + Pydantic + async (17 days)

- [ ] 9. Add `fastapi`, `uvicorn[standard]`, `pydantic-settings` to requirements.
- [ ] 10. Define Pydantic models: `PredictRequest`, `PredictResponse`, `ErrorResponse`, `HealthResponse`.
- [ ] 11. Move `config/settings.py` to `pydantic-settings` `BaseSettings` with validation and typed fields.
- [ ] 12. New `app/api.py`: FastAPI app skeleton with `/health` ported.
- [ ] 13. Port `/models`.
- [ ] 14. Port `/predict` with Pydantic request validation.
- [ ] 15. Replace the hand-rolled `require_api_key` decorator with a FastAPI dependency + `Security` scheme so it shows in OpenAPI.
- [ ] 16. Exception handlers mapping domain errors to consistent JSON error envelopes with request IDs.
- [ ] 17. `lifespan` handler for model load/unload; `/health` reports whether the model is actually ready.
- [ ] 18. `transformers` inference is blocking — run it in a threadpool so the event loop is not stalled.
- [ ] 19. Port the test suite to `httpx.AsyncClient` + `ASGITransport`.
- [ ] 20. Request logging middleware: method, path, status, duration, request ID.
- [ ] 21. Delete Flask, `flask-cors`, `flask-limiter`; re-implement CORS with FastAPI middleware.
- [ ] 22. Update `Dockerfile` to `uvicorn` workers; add a `HEALTHCHECK`; slim the image with a multi-stage build.
- [ ] 23. Update `docker-compose.yml` and README for the new entrypoint.
- [ ] 24. OpenAPI polish: tags, summaries, response examples, and a `docs/api.md` generated from the schema.
- [ ] 25. Pin a `python-version` file and confirm the matrix is green end to end.

## Phase 2 — The actual gateway (30 days)

This is the part that makes the resume line true.

- [ ] 26. Define the `Provider` protocol: `complete()`, `stream()`, `name`, `supported_models`, `health()`.
- [ ] 27. `MockProvider` — deterministic, offline, no keys. Everything in CI runs against this.
- [ ] 28. `LocalProvider` — wraps the existing transformers pipeline so the original feature survives the migration.
- [ ] 29. Canonical schema: `ChatRequest` (messages, model, temperature, max_tokens, stream) and `ChatResponse` (content, model, usage, finish_reason).
- [ ] 30. Provider registry + config-driven enablement; unknown provider returns a clean 400.
- [ ] 31. Model routing: `"anthropic/claude-..."` style identifiers resolve to a provider.
- [ ] 32. `OpenAIProvider`: `complete()`, request/response mapping, error mapping.
- [ ] 33. `OpenAIProvider`: `stream()`.
- [ ] 34. `AnthropicProvider`: `complete()`.
- [ ] 35. `AnthropicProvider`: `stream()`.
- [ ] 36. `GoogleProvider`: `complete()`.
- [ ] 37. `GoogleProvider`: `stream()`.
- [ ] 38. Normalize `finish_reason` and role names across all three providers; table-driven tests for the mapping.
- [ ] 39. Normalize usage/token accounting into one `Usage` model.
- [ ] 40. `POST /v1/chat` non-streaming endpoint over the registry.
- [ ] 41. `POST /v1/chat` streaming via SSE, with correct flush semantics and client-disconnect handling.
- [ ] 42. Cancellation: client disconnect must abort the upstream provider request.
- [ ] 43. Per-client API keys: config-loaded key table with an owner label per key.
- [ ] 44. Per-client rate limiting keyed on API key rather than IP, token-bucket, in-process.
- [ ] 45. Per-key quotas (requests/day and tokens/day) with `429` + `Retry-After` and `X-RateLimit-*` headers.
- [ ] 46. Cost accounting: per-provider price table, cost per request, running total per key.
- [ ] 47. `GET /v1/usage` — per-key usage and spend.
- [ ] 48. Structured JSON logging with request ID, key label, provider, model, latency, tokens, cost.
- [ ] 49. Provider error taxonomy: rate-limited, overloaded, invalid-request, auth, timeout — normalized across SDKs.
- [ ] 50. Contract tests: every provider adapter must satisfy the same shared test suite.
- [ ] 51. Recorded-fixture tests for each real provider (recorded once, replayed offline) so CI stays keyless.
- [ ] 52. `GET /v1/models` aggregated across enabled providers.
- [ ] 53. Config reload without restart.
- [ ] 54. README + `docs/architecture.md` rewrite with a real diagram of the request path.
- [ ] 55. Integration test: full path from API key auth through routing, rate limit, provider, streaming response.

## Phase 3 — Resilience (17 days)

- [ ] 56. Per-provider connect and read timeouts, configurable.
- [ ] 57. Retry with exponential backoff and jitter on retryable errors only.
- [ ] 58. Idempotency: never retry a request that already streamed bytes to the client.
- [ ] 59. Circuit breaker per provider: open, half-open, closed, with tests for each transition.
- [ ] 60. Fallback chain: primary provider fails or trips → next provider, recorded in the response metadata.
- [ ] 61. `/health` reports per-provider circuit state and last error.
- [ ] 62. Response cache for identical (model, messages, params) with TTL and a size bound.
- [ ] 63. Cache correctness: never cache streamed partials or errored responses.
- [ ] 64. Concurrency limit per provider so one slow upstream cannot exhaust the pool.
- [ ] 65. Graceful shutdown: drain in-flight requests before exit.
- [ ] 66. Backpressure: bounded request queue, `503` when saturated instead of unbounded latency.
- [ ] 67. Chaos tests: injected latency, injected 500s, injected partial streams.
- [ ] 68. Timeout budget propagation so a retry cannot exceed the client's total deadline.
- [ ] 69. Secrets hygiene pass: confirm no key ever reaches logs or error bodies; add a test that asserts it.
- [ ] 70. Dependency audit (`pip-audit`) wired into CI.
- [ ] 71. Container hardening: non-root user, pinned base image digest.
- [ ] 72. Load-shedding policy documented in `docs/operations.md`.

## Phase 4 — Measure it (18 days)

The resume gap: every other project has numbers and this one has none. Fix that
with numbers that are actually reproducible.

- [ ] 73. Benchmark harness: async load driver against `MockProvider` with fixed latency, so it measures the gateway and not the upstream.
- [ ] 74. Record p50 / p95 / p99 latency and throughput; commit the raw results as JSON.
- [ ] 75. Gateway overhead: latency added versus calling the fake upstream directly.
- [ ] 76. Throughput under concurrency sweep (1, 10, 50, 100, 500 concurrent).
- [ ] 77. Streaming benchmark: time-to-first-token versus total time.
- [ ] 78. Cache hit-rate and the latency delta it buys.
- [ ] 79. Rate limiter accuracy under burst: measured allowed-vs-configured.
- [ ] 80. Memory profile under sustained load; check for growth.
- [ ] 81. Prometheus `/metrics`: request count, latency histogram, tokens, cost, circuit state.
- [ ] 82. Grafana dashboard JSON committed to `docs/`.
- [ ] 83. `make bench` reproduces every number in one command.
- [ ] 84. Benchmarks run in CI on a schedule and fail on regression beyond a threshold.
- [ ] 85. `BENCHMARKS.md` with methodology, hardware, and the numbers.
- [ ] 86. Charts generated from the raw JSON, committed as SVG.
- [ ] 87. Compare the FastAPI implementation against the original Flask one and publish the delta.
- [ ] 88. `docs/decisions/` — short ADRs for the four or five real design calls made along the way.
- [ ] 89. README final pass: what it is, the architecture diagram, the numbers, how to run it.
- [ ] 90. Write the honest resume bullet from the measured results, with the commit that proves each claim.

---

## Backlog (only after 90)

- Anthropic prompt caching support and measured savings
- Tool/function-calling passthrough normalized across providers
- Multi-modal (image input) passthrough
- Postgres-backed usage accounting instead of in-process
- Horizontal scaling with a shared Redis rate limiter
