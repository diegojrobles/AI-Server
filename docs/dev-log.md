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
