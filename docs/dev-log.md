# Dev log

Two lines per working session: what changed, and why it mattered. Newest last.

## 2026-09-12 — Roadmap and a CI foundation that actually runs

Wrote `ROADMAP.md`: a 90-increment plan to take this from a Flask wrapper around one
local sentiment model to an async multi-provider LLM gateway with measured numbers.

Fixed CI, which could not have been passing: the workflow ran `python -m pytest` but
`pytest` was never in `requirements.txt`, and `test_server.py` made live HTTP calls to
`localhost:5000`. Split requirements into base / runtime / dev so the test environment
skips torch entirely, deferred the `transformers` import and the model instantiation out
of import time (importing `app.server` used to download a model), and replaced the old
script with 13 real tests against Flask's test client. Suite runs in 0.04s. Added ruff,
a 3.11/3.12 matrix, and a lint job.

## 2026-09-12 — Secret scanning as a hard gate

Added `scripts/secret_scan.py`: a dependency-free scanner for provider tokens
(GitHub, OpenAI, Anthropic, Google, AWS, Slack, Stripe), private keys, JWTs,
credentials in connection URLs, auth headers, and high-entropy secret assignments,
plus a path denylist for `.env`, `*.pem`, `id_rsa` and friends. Entropy and
placeholder filters keep `change-me` and `${VAR}` from generating noise.

Wired into three places so it cannot be skipped by accident: a `.githooks/pre-commit`
hook, a mandatory step in the automated daily job, and a CI job that scans the full
history on every push. Added `pip-audit` in the same CI job (roadmap item 70, pulled
forward). Verified against 12 planted credentials — all caught, no false positives on
the existing tree, and the repo's entire history scans clean.

## 2026-09-13 — Patched 7 CVEs the new audit caught

The `pip-audit` job added yesterday turned CI red on its first run, which is the
tool doing its job: flask 3.0.3, flask-cors 4.0.1 (four separate advisories),
python-dotenv 1.0.1 and pytest 8.3.3 all carried known vulnerabilities. Bumped to
flask 3.1.3, flask-cors 6.0.0, python-dotenv 1.2.2, pytest 9.0.3 and pytest-cov
7.0.0. flask-cors crossing a major version was the only real risk; the plain
`CORS(app)` call is unchanged in 6.x and the suite passes untouched. Audit now
reports no known vulnerabilities.
