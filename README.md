# AI Server

[![CI](https://github.com/diegojrobles/AI-Server/actions/workflows/test.yml/badge.svg)](https://github.com/diegojrobles/AI-Server/actions/workflows/test.yml)

A REST API server for running AI models behind a single interface.

**Current state:** Flask API serving a local HuggingFace sentiment model, with API-key
auth and rate limiting.

**Where it is going:** an async FastAPI gateway that fronts OpenAI, Anthropic and Google
behind one schema, with streaming, per-client rate limiting, provider fallback, and
published benchmarks. The plan is in [ROADMAP.md](ROADMAP.md); progress is in
[docs/dev-log.md](docs/dev-log.md).

## Features

- Sentiment analysis via `transformers`
- API key authentication (`X-API-Key`)
- Per-IP rate limiting
- Environment-based configuration
- Model loaded lazily on first request, so the process starts fast and tests run offline

## Setup

```bash
git clone https://github.com/diegojrobles/AI-Server.git
cd AI-Server

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt  # runtime, includes torch
cp .env.example .env             # then edit API_KEY

python run.py
```

### Dependency layout

| File | Contents | Use |
| --- | --- | --- |
| `requirements-base.txt` | web layer only | shared |
| `requirements.txt` | base + torch/transformers | running the server |
| `requirements-dev.txt` | base + pytest/ruff | tests and CI, no torch |

## API

### `GET /health`

```json
{ "status": "healthy", "model": "distilbert-...", "model_loaded": false }
```

### `POST /predict`

```bash
curl -X POST http://localhost:5000/predict \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text": "I love this product!"}'
```

```json
{ "input": "I love this product!", "prediction": [{ "label": "POSITIVE", "score": 0.99 }] }
```

Returns `400` on a missing or empty `text`, `401` on a bad key, `429` past the limit.

### `GET /models`

Lists the current and available model names.

## Development

```bash
make dev      # create .venv and install the test/lint dependencies
make test     # 25 tests, no network, no model download
make lint     # ruff check + ruff format --check
make check    # all three gates CI enforces
```

`make help` lists every target. The full loop — setup, the gate, the commit
rules — is in [CONTRIBUTING.md](CONTRIBUTING.md).

Tests fake the model handler via `server.set_model_handler()`, so the suite runs in
well under a second and CI never downloads torch.

### Secret scanning

`scripts/secret_scan.py` blocks credentials and key material from reaching the
repo. No third-party dependencies, so it behaves identically locally and in CI.

```bash
git config core.hooksPath .githooks   # once per clone: refuse commits with secrets

python3 scripts/secret_scan.py --staged   # what is about to be committed
python3 scripts/secret_scan.py --tree     # every tracked file
python3 scripts/secret_scan.py --all      # tracked files plus full history
```

It detects provider tokens (GitHub, OpenAI, Anthropic, Google, AWS, Slack,
Stripe), private keys, JWTs, credentials embedded in connection URLs, auth
headers, and high-entropy secret assignments, and refuses paths like `.env`,
`*.pem` and `id_rsa`. Placeholders such as `change-me` are ignored. For a value
that is genuinely not a secret, append `# pragma: allowlist secret` to the line;
suppressions are printed on every run so they cannot rot unnoticed.

CI runs the scan over the entire history on every push, alongside `pip-audit`
for known CVEs in dependencies.

## Docker

```bash
docker compose up --build
```

## License

MIT — see [LICENSE](LICENSE).
