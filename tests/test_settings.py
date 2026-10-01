"""Tests for the typed configuration layer (ROADMAP item 11).

These assert the three things the old ``class Config`` could not: that every
field arrives with the right *type*, that an out-of-range or malformed value is
rejected at startup instead of surfacing as an unrelated failure later, and
that the environment-variable names already published in ``.env.example`` keep
working unchanged.

Every construction passes ``_env_file=None`` unless the test is specifically
about ``.env`` loading. Without it the suite would read whatever ``.env``
happens to sit in the working directory of the machine running it, which is the
difference between a test and a coin flip.
"""

import importlib
import warnings

import pytest
from pydantic import ValidationError

import config.settings
from config.settings import Settings

# Every name the settings layer reads. Cleared wholesale so a value inherited
# from the developer's shell, from CI, or from conftest cannot decide a result.
ENV_NAMES = (
    "HOST",
    "PORT",
    "DEBUG",
    "MODEL_NAME",
    "MAX_LENGTH",
    "API_KEY",
    "RATELIMIT_ENABLED",
)


@pytest.fixture
def clean_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    return monkeypatch


class TestDefaults:
    def test_defaults_match_the_documented_env_example(self, clean_env):
        s = Settings(_env_file=None)
        assert s.host == "0.0.0.0"
        assert s.port == 5000
        assert s.debug is False
        assert s.model_name == "distilbert-base-uncased-finetuned-sst-2-english"
        assert s.max_length == 512
        assert s.api_key is None
        assert s.ratelimit_enabled is True

    def test_numeric_fields_are_actually_numbers(self, clean_env):
        """The regression the old ``int()`` casts existed to prevent."""
        s = Settings(_env_file=None)
        assert isinstance(s.port, int)
        assert isinstance(s.max_length, int)
        assert isinstance(s.debug, bool)
        assert isinstance(s.ratelimit_enabled, bool)


class TestEnvironmentReading:
    def test_reads_upper_case_names(self, clean_env):
        clean_env.setenv("HOST", "127.0.0.1")
        clean_env.setenv("PORT", "8080")
        clean_env.setenv("MAX_LENGTH", "256")
        s = Settings(_env_file=None)
        assert (s.host, s.port, s.max_length) == ("127.0.0.1", 8080, 256)

    def test_names_are_case_insensitive(self, clean_env):
        """``case_sensitive=False``, so a lower-case export still lands."""
        clean_env.setenv("port", "9001")
        assert Settings(_env_file=None).port == 9001

    def test_unknown_variables_are_ignored(self, clean_env):
        """The process environment is the host's, not ours to validate."""
        clean_env.setenv("TOTALLY_UNRELATED_VAR", "whatever")
        assert Settings(_env_file=None).port == 5000

    def test_env_file_is_read(self, clean_env, tmp_path):
        (tmp_path / ".env").write_text("PORT=6001\nMODEL_NAME=roberta-base\n")
        clean_env.chdir(tmp_path)
        s = Settings()
        assert (s.port, s.model_name) == (6001, "roberta-base")

    def test_real_environment_beats_env_file(self, clean_env, tmp_path):
        (tmp_path / ".env").write_text("PORT=6001\n")
        clean_env.chdir(tmp_path)
        clean_env.setenv("PORT", "7002")
        assert Settings().port == 7002


class TestPortValidation:
    @pytest.mark.parametrize("port", ["1", "80", "5000", "65535"])
    def test_accepts_valid_ports(self, clean_env, port):
        clean_env.setenv("PORT", port)
        assert Settings(_env_file=None).port == int(port)

    @pytest.mark.parametrize("port", ["0", "-1", "65536", "99999"])
    def test_rejects_out_of_range_ports(self, clean_env, port):
        """Previously accepted, then failed at bind time as an OS error."""
        clean_env.setenv("PORT", port)
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)
        assert "port" in str(exc.value)

    @pytest.mark.parametrize("port", ["", "abc", "80.5"])
    def test_rejects_non_integer_ports(self, clean_env, port):
        clean_env.setenv("PORT", port)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


class TestMaxLengthValidation:
    def test_accepts_one(self, clean_env):
        clean_env.setenv("MAX_LENGTH", "1")
        assert Settings(_env_file=None).max_length == 1

    @pytest.mark.parametrize("value", ["0", "-5"])
    def test_rejects_non_positive(self, clean_env, value):
        """A non-positive token limit used to reach the tokenizer verbatim."""
        clean_env.setenv("MAX_LENGTH", value)
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)
        assert "max_length" in str(exc.value)

    def test_has_no_invented_upper_bound(self, clean_env):
        """The real ceiling is the tokenizer's, enforced by transformers."""
        clean_env.setenv("MAX_LENGTH", "100000")
        assert Settings(_env_file=None).max_length == 100000


class TestBooleanParsing:
    @pytest.mark.parametrize("raw", ["1", "true", "True", "TRUE", "yes", "on"])
    def test_truthy_spellings(self, clean_env, raw):
        clean_env.setenv("DEBUG", raw)
        clean_env.setenv("HOST", "127.0.0.1")  # avoid the public-debug warning
        assert Settings(_env_file=None).debug is True

    @pytest.mark.parametrize("raw", ["0", "false", "False", "no", "off"])
    def test_falsy_spellings(self, clean_env, raw):
        clean_env.setenv("RATELIMIT_ENABLED", raw)
        assert Settings(_env_file=None).ratelimit_enabled is False

    @pytest.mark.parametrize("raw", ["ture", "enabled", "maybe", ""])
    def test_rejects_unparseable_booleans(self, clean_env, raw):
        """The silent failure this item exists to kill.

        ``_flag`` returned False for anything it did not recognise, so a typo
        in ``RATELIMIT_ENABLED`` disabled rate limiting without a word.
        """
        clean_env.setenv("RATELIMIT_ENABLED", raw)
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)
        assert "ratelimit_enabled" in str(exc.value)


class TestApiKey:
    def test_absent_means_none(self, clean_env):
        assert Settings(_env_file=None).api_key is None

    @pytest.mark.parametrize("raw", ["", "   ", "\t"])
    def test_blank_means_none(self, clean_env, raw):
        """``API_KEY=`` with the value deleted must disable auth, not enable it
        with a whitespace secret."""
        clean_env.setenv("API_KEY", raw)
        assert Settings(_env_file=None).api_key is None

    def test_surrounding_whitespace_is_trimmed(self, clean_env):
        clean_env.setenv("API_KEY", "  change-me\n")
        assert Settings(_env_file=None).api_key == "change-me"


class TestNonBlankStrings:
    @pytest.mark.parametrize("field", ["HOST", "MODEL_NAME"])
    def test_rejects_blank(self, clean_env, field):
        clean_env.setenv(field, "   ")
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)
        assert field.lower() in str(exc.value)

    def test_trims_model_name(self, clean_env):
        """A stray newline from a heredoc would otherwise become part of the
        Hugging Face identifier and 404 at load time."""
        clean_env.setenv("MODEL_NAME", "  roberta-base\n")
        assert Settings(_env_file=None).model_name == "roberta-base"


class TestPublicDebugWarning:
    @pytest.mark.parametrize("host", ["0.0.0.0", "::"])
    def test_warns_when_debug_is_publicly_bound(self, clean_env, host):
        clean_env.setenv("DEBUG", "true")
        clean_env.setenv("HOST", host)
        with pytest.warns(UserWarning, match="interactive debugger"):
            Settings(_env_file=None)

    def test_silent_when_debug_is_bound_to_loopback(self, clean_env):
        clean_env.setenv("DEBUG", "true")
        clean_env.setenv("HOST", "127.0.0.1")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert Settings(_env_file=None).debug is True

    def test_silent_when_debug_is_off(self, clean_env):
        clean_env.setenv("HOST", "0.0.0.0")
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert Settings(_env_file=None).debug is False


class TestImmutability:
    def test_cannot_be_mutated(self, clean_env):
        """Frozen on purpose: item 53 reloads config by swapping the instance,
        not by letting arbitrary callers write to shared state."""
        s = Settings(_env_file=None)
        with pytest.raises(ValidationError):
            s.port = 9999
        assert s.port == 5000


class TestModuleSingleton:
    def test_exposes_a_ready_instance(self):
        assert isinstance(config.settings.settings, Settings)

    def test_imports_without_warnings(self):
        """``model_name`` sits near Pydantic's protected namespaces. Under the
        pinned 2.13.5 they are ``("model_validate", "model_dump")``, so it does
        not collide -- but that is a property of the pin, so it is checked
        rather than assumed. This fails loudly if a future field is named
        something like ``model_dump_path``.
        """
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            importlib.reload(config.settings)
