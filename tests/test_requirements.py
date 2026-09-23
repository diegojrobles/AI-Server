"""Tests that keep the dependency manifests honest.

The three requirements files are a layered set: ``requirements-base.txt`` is
the web layer, ``requirements-dev.txt`` adds the test and lint tools, and
``requirements.txt`` adds the local inference stack. Both leaf files pull the
base in with ``-r``, which is what keeps CI installable in seconds.

Three properties are worth enforcing mechanically, because each one has
already cost this project a red pipeline or would have:

* every requirement is pinned with ``==`` — an unpinned dependency means the
  numbers recorded in Phase 4 are not reproducible, and a transitive bump can
  turn ``main`` red on a day nobody touched the code;
* no package is pinned to two different versions across the layers — pip
  resolves that by silently taking one of them;
* the environment the tests are running in matches what the manifests ask
  for, so a stale local ``.venv`` fails loudly here instead of mysteriously
  somewhere else.
"""

import re
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "requirements-base.txt"
DEV = ROOT / "requirements-dev.txt"
RUNTIME = ROOT / "requirements.txt"

# name[extras]==version, with the extras and any trailing comment optional.
REQUIREMENT_RE = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)"
    r"(?:\[(?P<extras>[A-Za-z0-9,._-]+)\])?"
    r"(?P<spec>.*?)\s*(?:#.*)?$"
)

# The web layer the FastAPI migration (ROADMAP Phase 1) is built on. These
# live in the base file specifically so the test environment gets them
# without torch: the ports in items 10-25 are all exercised in CI.
WEB_STACK = ("fastapi", "pydantic", "pydantic-settings", "uvicorn")

# Installing either of these into the test environment would add minutes and
# gigabytes to every CI run. The model is faked in tests; keep it that way.
ML_PACKAGES = ("torch", "transformers")


def normalize(name: str) -> str:
    """PEP 503 normalization, so ``python_dotenv`` and ``python-dotenv`` match."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_requirements(path: Path, *, follow_includes: bool = False) -> dict[str, dict]:
    """Return ``{normalized name: {...}}`` for one requirements file.

    ``-r other.txt`` includes are followed only when asked for, so a test can
    talk about one layer in isolation or about the fully resolved set.
    """
    found: dict[str, dict] = {}
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ")):
            if follow_includes:
                included = path.parent / line.split(maxsplit=1)[1].strip()
                found.update(parse_requirements(included, follow_includes=True))
            continue
        match = REQUIREMENT_RE.match(line)
        assert match, f"{path.name}:{lineno}: cannot parse requirement {line!r}"
        extras = match.group("extras")
        found[normalize(match.group("name"))] = {
            "name": match.group("name"),
            "extras": tuple(extras.split(",")) if extras else (),
            "spec": match.group("spec").strip(),
            "source": f"{path.name}:{lineno}",
        }
    return found


@pytest.fixture(scope="module")
def layers() -> dict[str, dict[str, dict]]:
    """Each manifest on its own, without its ``-r`` includes resolved."""
    return {
        "requirements-base.txt": parse_requirements(BASE),
        "requirements-dev.txt": parse_requirements(DEV),
        "requirements.txt": parse_requirements(RUNTIME),
    }


@pytest.mark.parametrize("path", [BASE, DEV, RUNTIME], ids=lambda p: p.name)
def test_manifest_exists(path: Path):
    assert path.is_file(), f"{path.name} is referenced by CI and the Makefile"


@pytest.mark.parametrize("path", [DEV, RUNTIME], ids=lambda p: p.name)
def test_leaf_manifests_include_the_base_layer(path: Path):
    """Both leaves build on the base file rather than restating the web layer."""
    assert "-r requirements-base.txt" in path.read_text(), (
        f"{path.name} should pull the shared web layer in with "
        "`-r requirements-base.txt`, not duplicate it"
    )


def test_every_requirement_is_pinned(layers):
    unpinned = [
        f"{entry['source']}: {entry['name']}{entry['spec'] or ' (no version at all)'}"
        for requirements in layers.values()
        for entry in requirements.values()
        if not re.fullmatch(r"==[^\s,;]+", entry["spec"])
    ]
    assert not unpinned, f"requirements must be pinned with `==`: {unpinned}"


def test_no_package_is_pinned_twice_with_different_versions(layers):
    seen: dict[str, tuple[str, str]] = {}
    conflicts = []
    for requirements in layers.values():
        for key, entry in requirements.items():
            previous = seen.get(key)
            if previous and previous[1] != entry["spec"]:
                conflicts.append(f"{entry['name']}: {previous[0]}{previous[1]} vs {entry['spec']}")
            else:
                seen[key] = (entry["source"], entry["spec"])
    assert not conflicts, f"the same package is pinned to two versions: {conflicts}"


@pytest.mark.parametrize("package", WEB_STACK)
def test_web_stack_is_declared_in_the_base_layer(layers, package):
    """FastAPI and friends must reach the test environment, which skips torch."""
    assert normalize(package) in layers["requirements-base.txt"], (
        f"{package} belongs in requirements-base.txt so the test environment "
        "installs it without pulling the inference stack"
    )


def test_uvicorn_requests_the_standard_extra(layers):
    """``[standard]`` is what installs uvloop and httptools."""
    uvicorn = layers["requirements-base.txt"]["uvicorn"]
    assert "standard" in uvicorn["extras"], (
        "uvicorn should be declared as uvicorn[standard]; without the extra "
        "the server falls back to the pure-python event loop and http parser"
    )


@pytest.mark.parametrize("package", ML_PACKAGES)
def test_the_test_environment_stays_free_of_the_inference_stack(package):
    installed = parse_requirements(DEV, follow_includes=True)
    assert normalize(package) not in installed, (
        f"{package} leaked into the dev/test dependency set; tests fake the "
        "model precisely so CI does not download it"
    )


def test_inference_stack_is_declared_in_the_runtime_manifest(layers):
    runtime = layers["requirements.txt"]
    missing = [pkg for pkg in ML_PACKAGES if normalize(pkg) not in runtime]
    assert not missing, f"requirements.txt no longer installs the model runtime: {missing}"


def test_installed_versions_match_the_pins():
    """A stale .venv should fail here, not somewhere confusing later."""
    mismatched = []
    for key, entry in parse_requirements(DEV, follow_includes=True).items():
        try:
            installed = metadata.version(key)
        except metadata.PackageNotFoundError:
            mismatched.append(f"{entry['name']}: pinned {entry['spec']}, not installed")
            continue
        pinned = entry["spec"].removeprefix("==")
        if installed != pinned:
            mismatched.append(f"{entry['name']}: pinned {pinned}, installed {installed}")
    assert not mismatched, (
        "the environment does not match requirements-dev.txt; "
        f"run `make dev` to reinstall: {mismatched}"
    )


def test_ruff_target_version_is_the_oldest_supported_python():
    """ruff's target-version must not claim a newer floor than CI actually tests.

    Parsed with a regex rather than ``tomllib`` on purpose: this file has to
    import cleanly on python 3.10, where ``tomllib`` does not exist yet.
    """
    pyproject = (ROOT / "pyproject.toml").read_text()
    target = re.search(r'^target-version\s*=\s*"(?P<v>py\d+)"', pyproject, re.MULTILINE)
    assert target, "pyproject.toml should pin ruff's target-version explicitly"

    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text()
    tested = sorted(
        re.findall(r'"(3\.\d+)"', workflow),
        key=lambda v: tuple(int(part) for part in v.split(".")),
    )
    assert tested, "the CI matrix should name explicit python versions"

    oldest = tested[0]
    assert target.group("v") == "py" + oldest.replace(".", ""), (
        f"ruff targets {target.group('v')} but CI's oldest python is {oldest}; "
        "ruff would allow syntax that version cannot run"
    )
