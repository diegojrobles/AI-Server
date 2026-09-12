#!/usr/bin/env python3
"""Secret and info-disclosure scanner.

Runs with no third-party dependencies so it works identically in CI, in a
pre-commit hook, and inside the automated daily job.

    python3 scripts/secret_scan.py --staged      # what is about to be committed
    python3 scripts/secret_scan.py --tree        # every tracked file
    python3 scripts/secret_scan.py --range a..b  # a commit range
    python3 scripts/secret_scan.py --all         # tracked files + full history

Exit codes: 0 clean, 1 findings, 2 usage/internal error.

Suppress a single verified-safe line with a trailing ``pragma: allowlist secret``
comment. Suppressions are reported so they cannot rot silently.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass

ALLOWLIST_PRAGMA = "pragma: allowlist secret"

# Obvious non-secrets. Anything whose captured value matches is not reported.
PLACEHOLDERS = re.compile(
    r"^(?:"
    r"change[-_]?me|your[-_].*|my[-_].*|test[-_]?key|dummy|sample|example|placeholder"
    r"|xxx+|yyy+|zzz+|foo|bar|baz|none|null|true|false|todo|tbd"
    r"|\.\.\.|<[^>]*>|\$\{[^}]*\}|%\([^)]*\)s|\{\{[^}]*\}\}"
    r"|[*x]{4,}|0+|1234\d*|secret|password|token|redacted"
    r")$",
    re.I,
)

# Files that should never be tracked at all, matched on path.
FORBIDDEN_PATHS = [
    (re.compile(r"(^|/)\.env$"), "committed .env file"),
    (re.compile(r"(^|/)\.env\.(?!example$|sample$|template$)[\w.-]+$"), "committed .env variant"),
    (re.compile(r"(^|/)\.gh-token$"), "committed GitHub token file"),
    (re.compile(r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$"), "committed private SSH key"),
    (re.compile(r"\.(pem|pfx|p12|jks|keystore)$"), "committed key/certificate store"),
    (re.compile(r"(^|/)credentials(\.json)?$"), "committed credentials file"),
    (re.compile(r"(^|/)service[-_]account.*\.json$"), "committed service-account key"),
    (re.compile(r"(^|/)\.npmrc$"), "npmrc can carry an auth token"),
    (re.compile(r"(^|/)\.pypirc$"), "pypirc carries upload credentials"),
]

# Binary-ish and vendored paths we do not scan for content.
SKIP_CONTENT = re.compile(
    r"(^|/)(\.venv|venv|node_modules|dist|build|__pycache__|\.git)/"
    r"|\.(png|jpe?g|gif|svg|ico|pdf|zip|gz|tar|whl|so|dylib|dll|woff2?|ttf|eot|lock)$"
)


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern
    severity: str  # "high" blocks; "low" warns
    group: int = 0


RULES: list[Rule] = [
    # --- provider credentials: unambiguous, always high ---
    Rule("GitHub fine-grained PAT", re.compile(r"github_pat_[A-Za-z0-9_]{22,}"), "high"),
    Rule("GitHub classic token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"), "high"),
    Rule("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}"), "high"),
    Rule("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}"), "high"),
    Rule("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"), "high"),
    Rule("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "high"),
    Rule("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "high"),
    Rule("Stripe secret key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{20,}"), "high"),
    Rule("Private key block", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----"), "high"),
    Rule(
        "JSON Web Token",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        "high",
    ),
    Rule(
        "Credentials in connection URL",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@]+:([^/\s:@]{3,})@", re.I),
        "high",
        group=1,
    ),
    Rule(
        "Basic auth header value",
        re.compile(r"[Aa]uthorization\s*[:=]\s*[\"']?(?:Basic|Bearer)\s+([A-Za-z0-9+/=._\-]{16,})"),
        "high",
        group=1,
    ),
    # --- generic assignments: high, but entropy-filtered below ---
    Rule(
        "Hardcoded secret assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|apikey|secret|password|passwd|pwd|token|access[_-]?key"
            r"|private[_-]?key|client[_-]?secret|auth[_-]?token)\b"
            r"\s*[:=]\s*[\"']([^\"'\n]{8,})[\"']"
        ),
        "high",
        group=1,
    ),
    # --- information disclosure: worth knowing, does not block ---
    Rule("Local user path", re.compile(r"/(?:Users|home)/(?!runner\b)[A-Za-z0-9._-]{3,}/"), "low"),
    Rule(
        "Private IP address",
        re.compile(r"\b(?:10\.\d+|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+\b"),
        "low",
    ),
]


# Values matching these are structurally incapable of being a live secret.
# Deliberately narrow: a real password is often plain alphanumeric, so treating
# every bare identifier as code hides genuine credentials.
def _looks_like_code(value: str) -> bool:
    return bool(
        re.search(r"[{}()\[\]<>]|\s{2,}|^\s|\s$", value)  # interpolation / expressions
        or re.fullmatch(r"[A-Z][A-Z0-9_]*", value)  # CONSTANT_NAME, not a secret
        or value.count(" ") >= 2  # prose
    )


def _shannon(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _is_noise(rule: Rule, value: str) -> bool:
    """Filter values that cannot plausibly be a live credential."""
    v = value.strip()
    if not v or PLACEHOLDERS.match(v):
        return True
    if rule.name in {
        "Hardcoded secret assignment",
        "Credentials in connection URL",
        "Basic auth header value",
    }:
        # These rules match a shape, not a known vendor prefix, so demand that
        # the captured value actually look random.
        if _looks_like_code(v):
            return True
        if len(v) < 12:
            return True
        if _shannon(v) < 3.0:
            return True
    return False


def _redact(value: str) -> str:
    v = value.strip()
    if len(v) <= 8:
        return "*" * len(v)
    return f"{v[:4]}{'*' * max(4, len(v) - 8)}{v[-4:]}"


@dataclass
class Finding:
    where: str
    line_no: int
    rule: str
    severity: str
    redacted: str
    context: str


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode != 0:
        return ""
    return r.stdout


def scan_text(
    where: str,
    text: str,
    findings: list[Finding],
    suppressed: list[str],
    start_line: int = 1,
) -> None:
    for i, line in enumerate(text.splitlines(), start_line):
        if len(line) > 4000:
            line = line[:4000]
        allowlisted = ALLOWLIST_PRAGMA in line
        for rule in RULES:
            for m in rule.pattern.finditer(line):
                value = m.group(rule.group) if rule.group else m.group(0)
                if _is_noise(rule, value):
                    continue
                if allowlisted:
                    suppressed.append(f"{where}:{i} {rule.name}")
                    continue
                findings.append(
                    Finding(
                        where=where,
                        line_no=i,
                        rule=rule.name,
                        severity=rule.severity,
                        redacted=_redact(value),
                        context=line.strip()[:120],
                    )
                )


def check_paths(paths: list[str], findings: list[Finding]) -> None:
    for p in paths:
        for pattern, why in FORBIDDEN_PATHS:
            if pattern.search(p):
                findings.append(
                    Finding(where=p, line_no=0, rule=why, severity="high", redacted="", context="")
                )


def tracked_files() -> list[str]:
    return [p for p in _git("ls-files").splitlines() if p]


def scan_tree(findings: list[Finding], suppressed: list[str]) -> None:
    paths = tracked_files()
    check_paths(paths, findings)
    for p in paths:
        if SKIP_CONTENT.search(p):
            continue
        blob = _git("show", f"HEAD:{p}") or ""
        if not blob:
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    blob = fh.read()
            except OSError:
                continue
        scan_text(p, blob, findings, suppressed)


HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _scan_patch(patch: str, label: str, findings: list[Finding], suppressed: list[str]) -> None:
    """Scan added lines of a unified diff, tracking real line numbers."""
    current = label
    line_no = 0
    for raw in patch.splitlines():
        if raw.startswith("+++ b/"):
            current = raw[6:]
            continue
        if raw.startswith("+++ ") or raw.startswith("--- "):
            continue
        m = HUNK.match(raw)
        if m:
            line_no = int(m.group(1))
            continue
        if raw.startswith("+"):
            scan_text(current, raw[1:], findings, suppressed, start_line=line_no)
            line_no += 1
        elif raw.startswith(" "):
            line_no += 1


def scan_diff(
    rev_args: list[str], label: str, findings: list[Finding], suppressed: list[str]
) -> None:
    names = [p for p in _git("diff", "--name-only", *rev_args).splitlines() if p]
    check_paths(names, findings)
    _scan_patch(_git("diff", "--unified=0", *rev_args), label, findings, suppressed)


def scan_history(findings: list[Finding], suppressed: list[str]) -> None:
    revs = [r for r in _git("rev-list", "--all").splitlines() if r]
    for rev in revs:
        patch = _git("show", "--unified=0", "--format=", rev)
        sub: list[Finding] = []
        _scan_patch(patch, rev[:9], sub, suppressed)
        for f in sub:
            f.where = f"{rev[:9]}:{f.where}"
        findings.extend(sub)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--staged", action="store_true", help="scan the staged diff")
    g.add_argument("--tree", action="store_true", help="scan all tracked files")
    g.add_argument("--range", metavar="A..B", help="scan a commit range")
    g.add_argument("--all", action="store_true", help="tracked files plus full history")
    ap.add_argument("--strict", action="store_true", help="treat low-severity findings as failures")
    args = ap.parse_args()

    if not _git("rev-parse", "--git-dir"):
        print("secret-scan: not a git repository", file=sys.stderr)
        return 2

    findings: list[Finding] = []
    suppressed: list[str] = []

    if args.staged:
        scan_diff(["--cached"], "<staged>", findings, suppressed)
        mode = "staged changes"
    elif args.range:
        scan_diff([args.range], args.range, findings, suppressed)
        mode = f"range {args.range}"
    elif args.all:
        scan_tree(findings, suppressed)
        scan_history(findings, suppressed)
        mode = "tracked files + full history"
    else:
        scan_tree(findings, suppressed)
        mode = "tracked files"

    high = [f for f in findings if f.severity == "high"]
    low = [f for f in findings if f.severity == "low"]

    for f in high:
        loc = f"{f.where}:{f.line_no}" if f.line_no else f.where
        detail = f" value={f.redacted}" if f.redacted else ""
        print(f"BLOCK  {loc}: {f.rule}{detail}")
        if f.context:
            print(f"       {f.context}")
    for f in low:
        loc = f"{f.where}:{f.line_no}" if f.line_no else f.where
        print(f"warn   {loc}: {f.rule} {f.redacted}".rstrip())

    if suppressed:
        print(f"\n{len(suppressed)} allowlisted via pragma:")
        for s in suppressed:
            print(f"       {s}")

    print(f"\nsecret-scan: {mode} — {len(high)} blocking, {len(low)} warnings")

    if high:
        print("\nA blocking finding means DO NOT COMMIT OR PUSH.")
        print("If a value is genuinely not a secret, append a trailing")
        print(f"'{ALLOWLIST_PRAGMA}' comment on that line and re-run.")
        return 1
    if low and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
