"""Tests that keep the Makefile, CONTRIBUTING.md and CI from drifting apart.

The Makefile is documentation that executes: CONTRIBUTING.md tells a
contributor to run ``make check``, and CI runs the same commands by hand in
the workflow. These tests fail when one of those three copies moves without
the others.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = ROOT / "Makefile"
CONTRIBUTING = ROOT / "CONTRIBUTING.md"
WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"

# Targets the roadmap and the docs promise. Removing one is a breaking change
# to the documented dev loop, so it should break a test rather than a person.
REQUIRED_TARGETS = ("test", "lint", "run", "check", "help")

TARGET_RE = re.compile(r"^([a-zA-Z_-]+):(?:[^=]*?)(?:##\s*(.+))?$", re.MULTILINE)
PHONY_RE = re.compile(r"^\.PHONY:\s*(.+)$", re.MULTILINE)
MAKE_REFERENCE_RE = re.compile(r"`make ([a-z_-]+)`")


@pytest.fixture(scope="module")
def makefile() -> str:
    return MAKEFILE.read_text()


@pytest.fixture(scope="module")
def targets(makefile: str) -> dict[str, str | None]:
    """Map of Makefile target name -> its ``##`` help description, if any."""
    return {name: (desc.strip() if desc else None) for name, desc in TARGET_RE.findall(makefile)}


def test_makefile_exists():
    assert MAKEFILE.is_file(), "Makefile is the documented entry point for the dev loop"


@pytest.mark.parametrize("target", REQUIRED_TARGETS)
def test_required_target_is_defined(targets, target):
    assert target in targets, f"Makefile is missing the documented `make {target}` target"


def test_every_phony_target_is_defined(makefile, targets):
    declared = {name for line in PHONY_RE.findall(makefile) for name in line.split()}
    missing = declared - targets.keys()
    assert not missing, f".PHONY names a target with no rule: {sorted(missing)}"


def test_every_phony_target_documents_itself(makefile, targets):
    """`make help` reads the ## comments, so an undocumented target is invisible."""
    declared = {name for line in PHONY_RE.findall(makefile) for name in line.split()}
    undocumented = sorted(name for name in declared if not targets.get(name))
    assert not undocumented, f"targets missing a `## description`: {undocumented}"


def test_recipes_use_tabs_not_spaces(makefile):
    """Make requires tabs. A space-indented recipe fails with a cryptic error."""
    offenders = [
        i
        for i, line in enumerate(makefile.splitlines(), start=1)
        if line.startswith("    ") and not line.lstrip().startswith("#")
    ]
    assert not offenders, f"space-indented lines in the Makefile: {offenders}"


def test_contributing_only_references_real_targets(targets):
    referenced = set(MAKE_REFERENCE_RE.findall(CONTRIBUTING.read_text()))
    assert referenced, "CONTRIBUTING.md should document the make-based dev loop"
    missing = referenced - targets.keys()
    assert not missing, f"CONTRIBUTING.md documents targets that do not exist: {sorted(missing)}"


def test_check_runs_what_ci_runs(makefile):
    """`make check` is sold as 'what CI runs'. Keep that claim true."""
    check_line = next(line for line in makefile.splitlines() if line.startswith("check:"))
    prerequisites = check_line.split(":", 1)[1].split("##")[0].split()
    assert {"lint", "test", "scan"} <= set(
        prerequisites
    ), f"`make check` no longer covers lint, test and the secret scan: {prerequisites}"


def test_ci_still_enforces_the_same_gates():
    workflow = WORKFLOW.read_text()
    for command in ("pytest", "ruff check .", "ruff format --check .", "secret_scan.py --all"):
        assert command in workflow, f"CI no longer runs `{command}`, so `make check` overpromises"
