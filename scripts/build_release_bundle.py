#!/usr/bin/env python3
"""Build the immutable one-shot team-skills release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path


RELEASE_ASSET_NAMES = (
    "install-team-skills.cmd",
    "install-team-skills.ps1",
    "install-team-skills.command",
    "migrate-team-skills.cmd",
    "migrate-team-skills.ps1",
    "migrate-team-skills.command",
    "uninstall-team-skills.ps1",
    "uninstall-team-skills.command",
    "remove-team-skills-autoupdate.ps1",
    "remove-team-skills-autoupdate.command",
)

WINDOWS_POWERSHELL_ASSETS = {
    "install-team-skills.ps1",
    "migrate-team-skills.ps1",
    "uninstall-team-skills.ps1",
    "remove-team-skills-autoupdate.ps1",
}

RELEASE_BOUND_ASSETS = {
    "install-team-skills.cmd",
    "install-team-skills.ps1",
    "install-team-skills.command",
    "migrate-team-skills.cmd",
    "migrate-team-skills.ps1",
    "migrate-team-skills.command",
}

RELEASE_TAG_PLACEHOLDER = "__TEAM_SKILLS_RELEASE_TAG__"

BUNDLE_TRANSIENT_DIR_NAMES = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
BUNDLE_TRANSIENT_FILE_NAMES = {".DS_Store"}
BUNDLE_TRANSIENT_FILE_SUFFIXES = {".pyc", ".pyo"}
BUNDLE_FORBIDDEN_FILE_NAMES = {
    "latest.json",
    "latest.json.sig",
    "manifest.json.sig",
    "team-skills-auto-update-with-git-fallback.ps1",
    "team-skills-public-key.pem",
    "team-skills-registry.py",
}
BUNDLE_FORBIDDEN_FILE_PREFIXES = (
    "bootstrap-team-skills",
    "refresh-team-skills",
    "update-team-skills",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_transient_bundle_path(path: Path) -> bool:
    return (
        any(part in BUNDLE_TRANSIENT_DIR_NAMES for part in path.parts)
        or path.name in BUNDLE_TRANSIENT_FILE_NAMES
        or path.suffix.lower() in BUNDLE_TRANSIENT_FILE_SUFFIXES
    )


def validate_plugin_bundle_source(plugin_root: Path) -> None:
    for path in plugin_root.rglob("*"):
        relative = path.relative_to(plugin_root)
        if is_transient_bundle_path(relative):
            continue
        if path.is_symlink():
            raise ValueError(f"plugin bundle source contains a symlink: {relative}")
        if not path.is_file():
            continue
        name = path.name.lower()
        if (
            name in BUNDLE_FORBIDDEN_FILE_NAMES
            or name.endswith(".sig")
            or name.startswith(BUNDLE_FORBIDDEN_FILE_PREFIXES)
        ):
            raise ValueError(f"plugin bundle source contains forbidden runtime: {relative}")


def ignore_transient_bundle_entries(directory: str, names: list[str]) -> set[str]:
    root = Path(directory)
    ignored: set[str] = set()
    for name in names:
        path = root / name
        if (
            name in BUNDLE_TRANSIENT_DIR_NAMES
            or name in BUNDLE_TRANSIENT_FILE_NAMES
            or path.suffix.lower() in BUNDLE_TRANSIENT_FILE_SUFFIXES
        ):
            ignored.add(name)
    return ignored


def copy_release_asset(source: Path, destination: Path, replacements: dict[str, str]) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"release asset source is missing: {source}")

    if source.name in RELEASE_BOUND_ASSETS:
        content = source.read_text(encoding="utf-8-sig")
        for placeholder, value in replacements.items():
            content = content.replace(placeholder, value)
        unresolved = {
            placeholder for placeholder in replacements if placeholder in content
        }
        if unresolved:
            names = ", ".join(sorted(unresolved))
            raise ValueError(f"release installer contains unresolved placeholders: {names}")
        encoding = "utf-8-sig" if source.name in WINDOWS_POWERSHELL_ASSETS else "utf-8"
        destination.write_text(content, encoding=encoding)
        shutil.copymode(source, destination)
        return

    if source.name in WINDOWS_POWERSHELL_ASSETS:
        content = source.read_text(encoding="utf-8-sig")
        destination.write_text(content, encoding="utf-8-sig")
        shutil.copymode(source, destination)
        return

    shutil.copy2(source, destination)


def build_release_bundle(
    *,
    root: Path,
    dist: Path,
    commit: str,
    run_number: str,
    run_attempt: str,
) -> None:
    shutil.rmtree(dist, ignore_errors=True)
    dist.mkdir(parents=True, exist_ok=True)

    plugin_root = root / "plugins" / "team-skills"
    validate_plugin_bundle_source(plugin_root)
    source_manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))

    short_sha = commit[:7]
    release_id = f"r{run_number}.{run_attempt}-{short_sha}"
    release_tag = f"team-skills-v{release_id}"
    product_version = source_manifest["version"]
    plugin_version = f"{product_version}-r.{run_number}.{run_attempt}.{short_sha}"
    release_base = (
        "https://github.com/kir-kopylov/codex-team-skills/releases/download/"
        f"{release_tag}"
    )
    release_plugin_root = dist / "bundle-root" / "team-skills"
    shutil.copytree(
        plugin_root,
        release_plugin_root,
        ignore=ignore_transient_bundle_entries,
    )
    release_manifest_path = release_plugin_root / ".codex-plugin" / "plugin.json"
    release_plugin_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    release_plugin_manifest.update(
        {
            "product_version": product_version,
            "version": plugin_version,
            "release_id": release_id,
            "release_tag": release_tag,
            "commit": commit,
        }
    )
    release_manifest_path.write_text(
        json.dumps(release_plugin_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    bundle_path = dist / "team-skills-bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(release_plugin_root.rglob("*")):
            if path.is_file():
                archive.write(
                    path,
                    Path("team-skills") / path.relative_to(release_plugin_root),
                )
    shutil.rmtree(dist / "bundle-root", ignore_errors=True)

    manifest = {
        "schema_version": 1,
        "release_tag": release_tag,
        "commit": commit,
        "plugin_version": plugin_version,
        "bundle": {
            "url": f"{release_base}/team-skills-bundle.zip",
            "size": bundle_path.stat().st_size,
            "sha256": sha256(bundle_path),
        },
    }
    (dist / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    replacements = {RELEASE_TAG_PLACEHOLDER: release_tag}
    for name in RELEASE_ASSET_NAMES:
        copy_release_asset(root / "installer" / name, dist / name, replacements)

    expected = {
        "manifest.json",
        "team-skills-bundle.zip",
        *RELEASE_ASSET_NAMES,
    }
    actual = {path.name for path in dist.iterdir()}
    if actual != expected:
        extra = ", ".join(sorted(actual - expected)) or "none"
        missing = ", ".join(sorted(expected - actual)) or "none"
        raise RuntimeError(f"unexpected dist contents; extra={extra}; missing={missing}")


def env_or_default(name: str, default: str) -> str:
    return os.environ.get(name) or default


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dist", type=Path)
    parser.add_argument(
        "--commit",
        default=env_or_default(
            "GITHUB_SHA_VALUE", env_or_default("GITHUB_SHA", "dev0000")
        ),
    )
    parser.add_argument(
        "--run-number",
        default=env_or_default(
            "GITHUB_RUN_NUMBER_VALUE", env_or_default("GITHUB_RUN_NUMBER", "0")
        ),
    )
    parser.add_argument(
        "--run-attempt",
        default=env_or_default(
            "GITHUB_RUN_ATTEMPT_VALUE", env_or_default("GITHUB_RUN_ATTEMPT", "0")
        ),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    dist = args.dist.resolve() if args.dist else root / "dist"
    build_release_bundle(
        root=root,
        dist=dist,
        commit=args.commit,
        run_number=args.run_number,
        run_attempt=args.run_attempt,
    )


if __name__ == "__main__":
    main()
