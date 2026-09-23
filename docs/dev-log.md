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

## 2026-09-22 — One command for the dev loop

Phase 0 ends with the loop being reproducible instead of remembered. Added a
`Makefile` (`dev`, `test`, `lint`, `format`, `check`, `scan`, `audit`, `run`,
`hooks`, `docker`, `clean`) that bootstraps `.venv` on demand via stamp files, so
dependencies reinstall only when a requirements file actually changes, and
`CONTRIBUTING.md` documenting the setup, the gate, and the one-item-per-commit
rule. `make check` is lint + tests + full-history secret scan — the same three
gates CI enforces.

Console scripts are invoked as `python -m pip` / `-m pytest` / `-m ruff` rather
than `.venv/bin/pip`: those shebang scripts hard-code the interpreter path and
break the moment the checkout moves, which is exactly how this broke first try.
Added `tests/test_makefile.py` (12 tests) so the three copies of the dev loop —
Makefile, CONTRIBUTING.md, CI workflow — cannot drift apart silently: every
`.PHONY` target must exist and carry a `##` description (that is what `make help`
prints), every `make x` in CONTRIBUTING.md must resolve, `check` must keep
depending on lint/test/scan, and CI must still run all three.


## 2026-09-23 — The FastAPI stack arrives (as dependencies)

Phase 1 opens by putting `fastapi==0.141.1`, `pydantic==2.13.5`,
`pydantic-settings==2.15.0` and `uvicorn[standard]==0.53.0` into
`requirements-base.txt` — the base layer, not the runtime one, so the test
environment gets the whole web stack without ever touching torch. Flask and
FastAPI now coexist in that file on purpose; the Flask entries come out in item
21, once every route has been ported. `pydantic` is pinned explicitly instead of
arriving as a FastAPI transitive: the schemas in items 10 and 29 are the
contract the gateway is built on, and a silent minor bump should not be able to
change validation behaviour underneath it. `pip-audit --strict` is clean on the
new set.

Added `tests/test_requirements.py` (17 tests) so the manifests cannot rot:
everything must be pinned with `==`, no package may be pinned to two different
versions across the three layers, the FastAPI stack must stay in the base file,
`uvicorn` must keep its `[standard]` extra (that extra is uvloop and httptools —
the reason the Phase 4 numbers will mean anything), torch and transformers must
stay out of the dev set, and the installed environment must match the pins so a
stale `.venv` fails loudly here rather than confusingly later. One of them also
ties ruff's `target-version` to the oldest python in the CI matrix, so the linter
can never start allowing syntax a tested interpreter cannot run.
