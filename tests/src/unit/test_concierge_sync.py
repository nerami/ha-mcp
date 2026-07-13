"""Promote-transform drift guards. Concierge's transform is config-identity
only: code must be byte-identical across flavors; only identity/version change.
"""

import filecmp
import importlib.util
import re
import shutil
from pathlib import Path

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV = REPO_ROOT / "homeassistant-addon-concierge-dev"


def _load_sync():
    spec = importlib.util.spec_from_file_location(
        "concierge_sync", REPO_ROOT / "scripts" / "concierge_sync.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def promoted(tmp_path: Path):
    """Copy dev into a tmp repo, run promote, return (tmp_root, version)."""
    sync = _load_sync()
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    # Mirror the sync's own ignore set: the dev tree carries gitignored build
    # artifacts (__pycache__, node_modules, .venv, ...) on disk that must not
    # be dragged into the tmp fixture copy -- same reason sync itself ignores
    # them when copying dev -> stable.
    shutil.copytree(DEV, root / DEV.name, symlinks=True, ignore=sync._IGNORE)
    version = sync.sync("promote", "patch", root=root)
    return root, version


def _yaml(path: Path) -> dict:
    return YAML(typ="safe").load(path.read_text())


def test_stable_identity(promoted) -> None:
    root, version = promoted
    cfg = _yaml(root / "homeassistant-addon-concierge" / "config.yaml")
    assert cfg["slug"] == "ha_mcp_concierge"
    assert "stage" not in cfg
    assert cfg["boot"] == "auto"
    assert "(Dev)" not in cfg["name"]
    assert "DEV CHANNEL" not in cfg["description"]
    assert cfg["version"] == version
    assert re.match(r"^\d+\.\d+\.\d+$", version), "stable version must have no .devN"


def test_security_invariants_survive_promote(promoted) -> None:
    root, _ = promoted
    cfg = _yaml(root / "homeassistant-addon-concierge" / "config.yaml")
    assert cfg.get("ingress") is True
    assert cfg.get("ingress_stream") is True
    assert "ports" not in cfg
    assert cfg.get("host_network") is not True


def _recursive_dircmp_ok(cmp: filecmp.dircmp) -> list[str]:
    """Walk a dircmp tree recursively and collect all mismatches found at any
    depth. filecmp.dircmp does NOT recurse on its own -- `diff_files`,
    `left_only`, and `right_only` only reflect the top-level directory, so a
    mutation several subpackages deep (e.g. frontend/src/components/*.ts)
    would silently pass an unrecursed check. `subdirs` gives us the child
    dircmp objects to recurse into.
    """
    mismatches = [
        f"{cmp.left}/{name}" for name in (cmp.diff_files or cmp.left_only or cmp.right_only)
    ]
    for sub_cmp in cmp.subdirs.values():
        mismatches.extend(_recursive_dircmp_ok(sub_cmp))
    return mismatches


def test_code_is_byte_identical_across_flavors(promoted) -> None:
    root, _ = promoted
    dev = root / "homeassistant-addon-concierge-dev"
    stable = root / "homeassistant-addon-concierge"
    for rel in ("backend/concierge", "frontend/src", "run.py"):
        dev_path, stable_path = dev / rel, stable / rel
        if dev_path.is_dir():
            cmp = filecmp.dircmp(dev_path, stable_path)
            mismatches = _recursive_dircmp_ok(cmp)
            assert not mismatches, f"{rel} differs between flavors: {mismatches}"
        else:
            assert dev_path.read_bytes() == stable_path.read_bytes(), f"{rel} differs"


def test_dockerfile_differs_only_in_labels(promoted) -> None:
    root, _ = promoted
    dev = (root / "homeassistant-addon-concierge-dev" / "Dockerfile").read_text().splitlines()
    stable = (root / "homeassistant-addon-concierge" / "Dockerfile").read_text().splitlines()
    diff = [(a, b) for a, b in zip(dev, stable, strict=True) if a != b]
    assert all("io.hass.name" in a for a, _ in diff), f"Dockerfile drift beyond labels: {diff}"
