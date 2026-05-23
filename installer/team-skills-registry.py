#!/usr/bin/env python3
"""Manage the Codex Desktop registry entry for the team-skills plugin."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path


BEGIN_MARKER = "# BEGIN codex-team-skills managed block"
END_MARKER = "# END codex-team-skills managed block"
MARKETPLACE_HEADER = "[marketplaces.codex-team-skills]"
PLUGIN_HEADER = '[plugins."team-skills@codex-team-skills"]'
TARGET_HEADERS = {MARKETPLACE_HEADER, PLUGIN_HEADER}


def quote_toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def read_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def validate_toml(text: str) -> None:
    tomllib.loads(text or "\n")


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_path = path.with_name(f"{path.name}.codex-team-skills.bak.{timestamp()}")
    shutil.copy2(path, backup_path)
    return backup_path


def strip_managed_content(text: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped == BEGIN_MARKER:
            index += 1
            while index < len(lines) and lines[index].strip() != END_MARKER:
                index += 1
            index += 1
            continue
        if stripped in TARGET_HEADERS:
            index += 1
            while index < len(lines) and not lines[index].lstrip().startswith("["):
                index += 1
            continue
        kept.append(lines[index])
        index += 1
    return "\n".join(kept).rstrip() + "\n"


def managed_block(marketplace_root: Path) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    source = str(marketplace_root.expanduser()).replace("\\", "/")
    return (
        f"{BEGIN_MARKER}\n"
        f"{MARKETPLACE_HEADER}\n"
        f"last_updated = {quote_toml_string(now)}\n"
        'source_type = "local"\n'
        f"source = {quote_toml_string(source)}\n"
        "\n"
        f"{PLUGIN_HEADER}\n"
        "enabled = true\n"
        f"{END_MARKER}\n"
    )


def ensure_registry(config_path: Path, marketplace_root: Path) -> dict[str, object]:
    original = read_text(config_path)
    next_text = strip_managed_content(original)
    if next_text.strip():
        next_text = next_text.rstrip() + "\n\n"
    next_text += managed_block(marketplace_root)
    validate_toml(next_text)

    config_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = backup(config_path)
    try:
        config_path.write_text(next_text, encoding="utf-8")
        validate_toml(read_text(config_path))
    except Exception:
        if backup_path is not None:
            shutil.copy2(backup_path, config_path)
        elif config_path.exists():
            config_path.unlink()
        raise
    return {
        "registry_ok": True,
        "config_path": str(config_path),
        "marketplace_root": str(marketplace_root),
        "backup_path": str(backup_path) if backup_path else None,
    }


def remove_registry(config_path: Path) -> dict[str, object]:
    original = read_text(config_path)
    if not original:
        return {"registry_removed": True, "config_path": str(config_path), "backup_path": None}
    next_text = strip_managed_content(original)
    validate_toml(next_text)
    backup_path = backup(config_path)
    try:
        config_path.write_text(next_text, encoding="utf-8")
        validate_toml(read_text(config_path))
    except Exception:
        if backup_path is not None:
            shutil.copy2(backup_path, config_path)
        raise
    return {
        "registry_removed": True,
        "config_path": str(config_path),
        "backup_path": str(backup_path) if backup_path else None,
    }


def registry_status(config_path: Path) -> dict[str, object]:
    text = read_text(config_path)
    result = {
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "managed_block": BEGIN_MARKER in text and END_MARKER in text,
        "marketplace_registered": MARKETPLACE_HEADER in text,
        "plugin_enabled": PLUGIN_HEADER in text and "enabled = true" in text,
        "toml_valid": False,
    }
    try:
        validate_toml(text)
        result["toml_valid"] = True
    except Exception as exc:
        result["toml_error"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Codex Desktop team-skills registry state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure = subparsers.add_parser("ensure")
    ensure.add_argument("--config", required=True)
    ensure.add_argument("--marketplace-root", required=True)

    remove = subparsers.add_parser("remove")
    remove.add_argument("--config", required=True)

    status = subparsers.add_parser("status")
    status.add_argument("--config", required=True)

    args = parser.parse_args()
    try:
        if args.command == "ensure":
            payload = ensure_registry(Path(args.config).expanduser(), Path(args.marketplace_root).expanduser())
        elif args.command == "remove":
            payload = remove_registry(Path(args.config).expanduser())
        else:
            payload = registry_status(Path(args.config).expanduser())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    payload["ok"] = True
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
