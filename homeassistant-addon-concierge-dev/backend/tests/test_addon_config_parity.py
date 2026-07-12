"""Guard: config.yaml options must stay in lockstep with Settings.

Options are the operator-facing SUBSET of Settings; these are supplied by the
runtime, not by options, so they're allowed to be absent from config.yaml.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

from concierge.config import Settings

ADDON_DIR = Path(__file__).resolve().parents[2]
MANIFEST = yaml.safe_load((ADDON_DIR / "config.yaml").read_text())

RUNTIME_SUPPLIED = {
    "ha_url",
    "ha_token",
    "data_dir",
    "host",
    "port",
    # Baked into the image by the Dockerfile (CONCIERGE_STATIC_DIR=/app/static,
    # never from /data/options.json — there is no user-facing use case for
    # changing where the built frontend lives), so it has no config.yaml option.
    "static_dir",
}


def _load_run():
    spec = importlib.util.spec_from_file_location("addon_run", ADDON_DIR / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_every_option_is_a_settings_field() -> None:
    settings_fields = set(Settings.model_fields)
    unknown = set(MANIFEST["options"]) - settings_fields
    assert not unknown, f"config.yaml options with no Settings field: {unknown}"


def test_no_settings_field_silently_unconfigurable() -> None:
    # Every Settings field is either an exposed option or deliberately
    # runtime-supplied — nothing falls through the cracks unnoticed.
    settings_fields = set(Settings.model_fields)
    unaccounted = settings_fields - set(MANIFEST["options"]) - RUNTIME_SUPPLIED
    assert not unaccounted, (
        f"Settings fields neither exposed as options nor runtime-supplied: "
        f"{unaccounted} — expose them in config.yaml or add to RUNTIME_SUPPLIED"
    )


def test_option_defaults_construct_valid_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings(**kwargs) does NOT run pydantic-settings' env-source JSON
    # parsing, so a plain-kwargs `skills="[]"` fails list-type validation.
    # The real add-on path is env vars -> Settings(), so exercise that: set
    # each CONCIERGE_* var build_env() produces, then construct with no args.
    run = _load_run()
    env = run.build_env(MANIFEST["options"], supervisor_token="tok")
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    settings = Settings()
    assert settings.provider == MANIFEST["options"]["provider"]
