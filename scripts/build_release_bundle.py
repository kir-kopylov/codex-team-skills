#!/usr/bin/env python3
"""Build the validated team-skills release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path


SUPPORT_NAMES = (
    "install-team-skills.cmd",
    "install-team-skills.ps1",
    "install-team-skills.command",
    "bootstrap-team-skills.ps1",
    "bootstrap-team-skills.sh",
    "update-team-skills.ps1",
    "update-team-skills.sh",
    "uninstall-team-skills.ps1",
    "uninstall-team-skills.command",
    "team-skills-status.ps1",
    "team-skills-status.command",
    "pull-skills.sh",
    "team-skills-registry.py",
    "team-skills-public-key.pem",
)

WINDOWS_POWERSHELL_ASSETS = {
    "install-team-skills.ps1",
    "bootstrap-team-skills.ps1",
    "update-team-skills.ps1",
    "uninstall-team-skills.ps1",
    "team-skills-status.ps1",
}


def asset_metadata(name: str, path: Path, release_base: str) -> dict[str, str | int]:
    return {
        "name": name,
        "url": f"{release_base}/{name}",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
    }


def copy_support_file(source: Path, destination: Path) -> None:
    if source.name in WINDOWS_POWERSHELL_ASSETS:
        content = source.read_text(encoding="utf-8-sig")
        destination.write_text(content, encoding="utf-8-sig")
        return

    shutil.copy2(source, destination)


def support_source_path(root: Path, name: str) -> Path:
    if name == "pull-skills.sh":
        return root / "scripts" / name
    return root / "installer" / name


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
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    plugin_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    short_sha = commit[:7]
    release_id = f"r{run_number}.{run_attempt}-{short_sha}"
    release_tag = f"team-skills-v{release_id}"
    product_version = plugin_manifest["version"]
    runtime_version = f"{product_version}-r.{run_number}.{run_attempt}.{short_sha}"
    release_base = f"https://github.com/kir-kopylov/codex-team-skills/releases/download/{release_tag}"

    release_plugin_root = dist / "bundle-root" / "team-skills"
    shutil.copytree(plugin_root, release_plugin_root)
    release_manifest_path = release_plugin_root / ".codex-plugin" / "plugin.json"
    release_plugin_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    release_plugin_manifest["product_version"] = product_version
    release_plugin_manifest["version"] = runtime_version
    release_plugin_manifest["release_id"] = release_id
    release_plugin_manifest["commit"] = commit
    release_manifest_path.write_text(
        json.dumps(release_plugin_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    bundle_path = dist / "team-skills-bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(release_plugin_root.rglob("*")):
            if path.is_file():
                archive.write(path, Path("team-skills") / path.relative_to(release_plugin_root))
    shutil.rmtree(dist / "bundle-root", ignore_errors=True)

    for name in SUPPORT_NAMES:
        copy_support_file(support_source_path(root, name), dist / name)

    plugin_bundle = asset_metadata("team-skills-bundle.zip", bundle_path, release_base)
    support_files = [asset_metadata(name, dist / name, release_base) for name in SUPPORT_NAMES]
    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "name": "team-skills",
        "product_version": product_version,
        "runtime_version": runtime_version,
        "release_id": release_id,
        "release_tag": release_tag,
        "commit": commit,
        "channel": "stable",
        "minimum_bootstrap_version": "1.0.0",
        "minimum_updater_version": "1.0.0",
        "created_at": created_at,
        "plugin_bundle": plugin_bundle,
        "support_files": support_files,
    }
    (dist / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    latest = {
        "name": "team-skills",
        "channel": "stable",
        "release_id": release_id,
        "release_tag": release_tag,
        "runtime_version": runtime_version,
        "commit": commit,
        "manifest_url": f"{release_base}/manifest.json",
        "created_at": created_at,
    }
    (dist / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def env_or_default(name: str, default: str) -> str:
    return os.environ.get(name) or default


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--commit", default=env_or_default("GITHUB_SHA_VALUE", env_or_default("GITHUB_SHA", "dev0000")))
    parser.add_argument("--run-number", default=env_or_default("GITHUB_RUN_NUMBER_VALUE", env_or_default("GITHUB_RUN_NUMBER", "0")))
    parser.add_argument(
        "--run-attempt",
        default=env_or_default("GITHUB_RUN_ATTEMPT_VALUE", env_or_default("GITHUB_RUN_ATTEMPT", "0")),
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
