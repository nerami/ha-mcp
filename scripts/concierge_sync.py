#!/usr/bin/env python3
"""Sync the Concierge add-on between its dev and stable flavors.

Concierge ships no custom component, so backend/frontend/run.py/Dockerfile
(minus LABELs) are byte-identical across flavors — this transform touches only
flavor IDENTITY (config.yaml, Dockerfile labels, doc framing) and the version.
Regex text edits (not YAML round-trip) so comments/formatting survive.

  --direction promote --bump {patch,minor,major}   dev -> stable
  --direction reset                                 stable -> dev (hotfix pull)
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_DIR = REPO_ROOT / "homeassistant-addon-concierge-dev"
STABLE_DIR = REPO_ROOT / "homeassistant-addon-concierge"

DEV_SLUG = "ha_mcp_concierge_dev"
STABLE_SLUG = "ha_mcp_concierge"

# Build artifacts that may exist on disk next to the source (all gitignored)
# but must never be physically copied into the sibling flavor's tree.
_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "node_modules",
    "dist",
    ".venv",
    "venv",
    "*.egg-info",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "sdist",
)


def _read_version(config_text: str) -> str:
    m = re.search(r'^version:\s*"([^"]+)"', config_text, re.M)
    if not m:
        raise ValueError("no version in config.yaml")
    return m.group(1)


def next_stable_version(current_stable: str | None, dev_version: str, bump: str) -> str:
    """First promote (no stable yet) => dev's X.Y.Z; else bump the stable line."""
    if current_stable is None:
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)", dev_version)
        if not m:
            raise ValueError(f"unparseable dev version: {dev_version!r}")
        return f"{m[1]}.{m[2]}.{m[3]}"
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", current_stable)
    if not m:
        raise ValueError(f"unparseable stable version: {current_stable!r}")
    major, minor, patch = int(m[1]), int(m[2]), int(m[3])
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def next_dev_version(stable_version: str) -> str:
    """reset: start a fresh dev line from the stable base."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", stable_version)
    if not m:
        raise ValueError(f"unparseable stable version: {stable_version!r}")
    return f"{m[1]}.{m[2]}.{m[3]}.dev1"


def transform_config(text: str, *, to_stable: bool, version: str) -> str:
    if to_stable:
        text = text.replace(f'slug: "{DEV_SLUG}"', f'slug: "{STABLE_SLUG}"')
        text = text.replace(
            'name: "Concierge for HA MCP (Dev)"', 'name: "Concierge for HA MCP"'
        )
        text = text.replace(
            'description: "DEV CHANNEL (unstable) — ',
            'description: "',
        )
        text = text.replace('panel_title: "Concierge (Dev)"', 'panel_title: "Concierge"')
        # stage: experimental sits alone on its own line, right after `url:`.
        text = re.sub(r"^stage:\s*experimental\n", "", text, flags=re.M)
        text = re.sub(r"^boot:\s*manual\b", "boot: auto", text, flags=re.M)
    else:  # reset: stable -> dev identity
        text = text.replace(f'slug: "{STABLE_SLUG}"', f'slug: "{DEV_SLUG}"')
        text = text.replace(
            'name: "Concierge for HA MCP"', 'name: "Concierge for HA MCP (Dev)"'
        )
        text = text.replace(
            'description: "',
            'description: "DEV CHANNEL (unstable) — ',
        )
        text = text.replace('panel_title: "Concierge"', 'panel_title: "Concierge (Dev)"')
        text = re.sub(r"^boot:\s*auto\b", "boot: manual", text, flags=re.M)
        # Re-insert `stage: experimental` right after `url:`, mirroring the
        # dev file's own layout (NOT after `boot:` — stage lives next to url).
        text = re.sub(r"^(url:.*\n)", r"\1stage: experimental\n", text, count=1, flags=re.M)
    text = re.sub(r'^version:\s*"[^"]+"', f'version: "{version}"', text, count=1, flags=re.M)
    return text


def transform_dockerfile(text: str, *, to_stable: bool) -> str:
    if to_stable:
        return text.replace(
            'io.hass.name="Concierge for HA MCP (Dev)"',
            'io.hass.name="Concierge for HA MCP"',
        )
    return text.replace(
        'io.hass.name="Concierge for HA MCP"',
        'io.hass.name="Concierge for HA MCP (Dev)"',
    )


def transform_docs(text: str, *, to_stable: bool) -> str:
    """Swap the dev-channel framing in AGENTS.md/DOCS.md."""
    if to_stable:
        # Drop the "> **Dev channel.** ..." blockquote banner (DOCS.md only;
        # a no-op regex miss on AGENTS.md, which doesn't carry the banner).
        text = re.sub(
            r"\n> \*\*Dev channel\.\*\*.*?\n\n",
            "\n",
            text,
            count=1,
            flags=re.S,
        )
        text = text.replace(" (dev flavor)", "")
        text = text.replace(" (Dev)", "")
        text = text.replace("DEV CHANNEL (unstable) — ", "")
        return text
    # reset is rare; the dev-side framing is restored by re-running the dev edit
    # by hand on the reset PR if needed. Keep reset a copy for code, manual docs.
    return text


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True, ignore=_IGNORE)


def sync(direction: str, bump: str | None, root: Path = REPO_ROOT) -> str:
    dev, stable = root / DEV_DIR.name, root / STABLE_DIR.name
    to_stable = direction == "promote"
    src, dst = (dev, stable) if to_stable else (stable, dev)

    dev_version = _read_version((dev / "config.yaml").read_text())
    current_stable = (
        _read_version((stable / "config.yaml").read_text()) if stable.exists() else None
    )
    if to_stable:
        assert bump is not None
        version = next_stable_version(current_stable, dev_version, bump)
    else:
        assert current_stable is not None
        version = next_dev_version(current_stable)

    # CHANGELOG.md is per-flavor: stash the destination's own copy before the
    # copytree clobbers it, and restore it afterward (the source's changelog
    # is never carried across). On a first promote (no stable dir yet), there
    # is nothing to stash, so the copied dev CHANGELOG.md stands as the
    # stable flavor's initial history.
    dst_changelog = dst / "CHANGELOG.md"
    stashed_changelog = dst_changelog.read_text() if dst_changelog.exists() else None

    _copy_tree(src, dst)  # verbatim code copy; identity files fixed up below

    (dst / "config.yaml").write_text(
        transform_config((dst / "config.yaml").read_text(), to_stable=to_stable, version=version)
    )
    (dst / "Dockerfile").write_text(
        transform_dockerfile((dst / "Dockerfile").read_text(), to_stable=to_stable)
    )
    for doc in ("AGENTS.md", "DOCS.md"):
        p = dst / doc
        if p.exists() and not p.is_symlink():
            p.write_text(transform_docs(p.read_text(), to_stable=to_stable))

    if stashed_changelog is not None:
        dst_changelog.write_text(stashed_changelog)

    return version


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--direction", required=True, choices=["promote", "reset"])
    p.add_argument("--bump", choices=["patch", "minor", "major"])
    args = p.parse_args(argv)
    if args.direction == "promote" and not args.bump:
        p.error("--bump is required for --direction promote")
    version = sync(args.direction, args.bump)
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
