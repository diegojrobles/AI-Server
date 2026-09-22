# Contributing

This is a personal project built in daily increments against
[ROADMAP.md](ROADMAP.md), but the loop below is the whole contract: if
`make check` is green and the roadmap box is ticked, the change is done.

## Setup

```bash
git clone https://github.com/diegojrobles/AI-Server.git
cd AI-Server

make dev      # creates .venv and installs the test/lint dependencies
make hooks    # once per clone: refuse commits containing secrets
```

`make dev` installs `requirements-dev.txt`, which is the web layer plus pytest
and ruff — no torch. That is deliberate: the tests fake the model, so the
environment installs in seconds. You only need the full stack (`make install`,
which pulls torch and transformers) to actually run the server.

No target expects an activated virtualenv; everything runs out of `.venv/bin`.

## The loop

```bash
make test     # pytest, offline, no model download
make lint     # ruff check + ruff format --check
make format   # apply formatting and autofixes
make check    # lint + test + secret scan, i.e. what CI runs
```

`make check` is the gate. It mirrors
[`.github/workflows/test.yml`](.github/workflows/test.yml), so a green run
locally should mean a green pipeline. `make help` lists everything else
(`coverage`, `audit`, `run`, `docker`, `clean`).

## Secrets

`scripts/secret_scan.py` is a hard gate, not a suggestion. A credential that
reaches the remote is compromised and has to be rotated, not deleted.

- The `.githooks/pre-commit` hook scans staged changes on every commit.
- `make scan` scans tracked files **and the full history**.
- CI scans the full history on every push.

Never commit `.env`, key material, or a real token — in code, in a test
fixture, in a docstring, or in a commit message. Use obvious placeholders like
`change-me` or `sk-ant-...`. If the scanner flags a value that genuinely is not
a secret, append `# pragma: allowlist secret` to that line; every suppression
is printed on each run so they cannot rot unnoticed. Do not reach for
`--no-verify`.

## Tests

Tests live in `tests/` and run against Flask's `test_client`. Two rules:

- **No network, ever.** No live server, no model download, no provider calls.
  The model handler is faked through `server.set_model_handler()`; from
  roadmap item 27 onward, provider code is exercised through `MockProvider`.
- **No import-time side effects.** Importing `app.server` must stay cheap.
  Loading the model on import was a real bug (roadmap item 3); the lazy
  accessor exists to keep it fixed.

## Style

`ruff` is the only authority — line length 100, rule set `E,F,I,UP,B`, config
in `pyproject.toml`. Run `make format` before `make check`.

## Commits

One roadmap item per commit. Each commit:

1. Implements the next unchecked `- [ ] N.` item in `ROADMAP.md`, and only that
   one. If it turns out to be bigger than a day, split it in the file and do
   the first half.
2. Ticks that box.
3. Appends 2–4 lines to [`docs/dev-log.md`](docs/dev-log.md) saying what
   changed and why it mattered.
4. Passes `make check`.

Subject line in the imperative, under ~70 characters, describing the change
rather than the item number ("Block secrets from reaching the repo", not
"Item 8"). The body explains the reasoning — that is what makes the history
worth reading later.

If you cannot get `make check` green, commit nothing. A skipped day costs
nothing; a broken `main` costs the next one.
