#!/usr/bin/env python3
"""Fail a PR when the Codex plugin changed without a semver bump."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path("plugins/team-skills/.codex-plugin/plugin.json")
PLUGIN_PREFIX = "plugins/team-skills/"
SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def parse_semver(value: str) -> tuple[int, int, int]:
    match = SEMVER_RE.fullmatch(value)
    if not match:
        raise ValueError(f"некорректная semver-версия: {value!r}")
    return tuple(int(part) for part in match.groups())


def plugin_changed(paths: Iterable[str]) -> bool:
    return any(path.replace("\\", "/").startswith(PLUGIN_PREFIX) for path in paths)


def validate_version_bump(
    changed_paths: Iterable[str],
    *,
    base_version: str,
    head_version: str,
) -> list[str]:
    if not plugin_changed(changed_paths):
        return []

    try:
        base = parse_semver(base_version)
        head = parse_semver(head_version)
    except ValueError as error:
        return [str(error)]

    if head <= base:
        return [
            "содержимое plugins/team-skills изменилось, но версия плагина "
            f"не повышена: было {base_version}, стало {head_version}"
        ]
    return []


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def changed_paths(base_ref: str) -> list[str]:
    output = run_git("diff", "--name-only", "--diff-filter=ACDMRT", base_ref, "--")
    return [line.strip() for line in output.splitlines() if line.strip()]


def manifest_version_from_ref(ref: str) -> str:
    payload = json.loads(run_git("show", f"{ref}:{MANIFEST_PATH.as_posix()}"))
    return payload["version"]


def manifest_version_from_worktree() -> str:
    payload = json.loads((ROOT / MANIFEST_PATH).read_text(encoding="utf-8"))
    return payload["version"]


def default_base_ref() -> str | None:
    base = os.environ.get("GITHUB_BASE_REF")
    return f"origin/{base}" if base else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default=default_base_ref())
    args = parser.parse_args(argv)

    if not args.base_ref:
        parser.error("укажите --base-ref или GITHUB_BASE_REF")

    paths = changed_paths(args.base_ref)
    errors = validate_version_bump(
        paths,
        base_version=manifest_version_from_ref(args.base_ref),
        head_version=manifest_version_from_worktree(),
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    if plugin_changed(paths):
        print("Версия Codex plugin повышена вместе с его содержимым.")
    else:
        print("Содержимое Codex plugin не менялось; повышение версии не требуется.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
