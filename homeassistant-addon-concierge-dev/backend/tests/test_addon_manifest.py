"""The add-on manifest (config.yaml) is one dir up from this backend project."""

from pathlib import Path

import pytest
import yaml

ADDON_DIR = Path(__file__).resolve().parents[2]
CONFIG = ADDON_DIR / "config.yaml"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def test_config_is_valid_yaml_with_required_keys(manifest: dict) -> None:
    for key in ("name", "slug", "version", "arch", "options", "schema"):
        assert key in manifest, f"missing required key: {key}"
    assert manifest["slug"] == "ha_mcp_concierge_dev"
    assert set(manifest["arch"]) == {"aarch64", "amd64"}


def test_security_invariants(manifest: dict) -> None:
    # /agui is unauthenticated; ingress is the only allowed exposure.
    assert manifest.get("ingress") is True
    assert manifest.get("ingress_stream") is True, "SSE needs unbuffered ingress"
    assert "ports" not in manifest, "no host port may be published"
    assert manifest.get("host_network") is not True, "host_network would expose /agui"
    assert manifest.get("ingress_port") == 8098


def test_dev_version_is_devN(manifest: dict) -> None:
    import re

    assert re.match(r"^\d+\.\d+\.\d+\.dev\d+$", str(manifest["version"])), (
        "dev add-on version must be X.Y.Z.devN"
    )


def test_options_have_schema_and_vice_versa(manifest: dict) -> None:
    assert set(manifest["options"]) == set(manifest["schema"]), (
        "every option needs a schema entry and vice versa"
    )
