#!/usr/bin/env python3
"""Exercise native Codex marketplace install/update/remove in an isolated home."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ID = "team-skills@codex-team-skills"
MARKETPLACE_NAME = "codex-team-skills"
MINIMUM_CODEX_VERSION = (0, 144, 4)


def run_json(command: list[str], *, env: dict[str, str]) -> dict:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            f"команда завершилась с кодом {error.returncode}: {' '.join(command)}\n"
            f"stdout={error.stdout!r}\nstderr={error.stderr!r}"
        ) from error
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"команда не вернула JSON: {' '.join(command)}\n"
            f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
        ) from error


def codex_version(codex: str, *, env: dict[str, str]) -> tuple[int, int, int]:
    output = subprocess.run(
        [codex, "--version"],
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", output)
    if not match:
        raise RuntimeError(f"не удалось определить версию Codex: {output!r}")
    return tuple(int(part) for part in match.groups())


def expected_plugin_version() -> str:
    manifest = json.loads(
        (ROOT / "plugins/team-skills/.codex-plugin/plugin.json").read_text(encoding="utf-8")
    )
    return manifest["version"]


def assert_inside(path: Path, parent: Path) -> None:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError as error:
        raise AssertionError(f"Codex записал plugin вне изолированного CODEX_HOME: {path}") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--ref")
    args = parser.parse_args(argv)

    codex = shutil.which("codex")
    if not codex:
        raise SystemExit("codex не найден в PATH")
    with tempfile.TemporaryDirectory(prefix="team-skills-native-marketplace-") as temp_dir:
        codex_home = Path(temp_dir) / ".codex"
        codex_home.mkdir()
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)
        if codex_version(codex, env=env) < MINIMUM_CODEX_VERSION:
            raise SystemExit("нужен Codex 0.144.4 или новее")

        add_marketplace = [codex, "plugin", "marketplace", "add", args.source]
        if args.ref:
            add_marketplace.extend(["--ref", args.ref])
        add_marketplace.append("--json")
        marketplace = run_json(add_marketplace, env=env)
        assert marketplace["marketplaceName"] == MARKETPLACE_NAME

        installed = run_json([codex, "plugin", "add", PLUGIN_ID, "--json"], env=env)
        assert installed["pluginId"] == PLUGIN_ID
        assert installed["version"] == expected_plugin_version()
        installed_path = Path(installed["installedPath"])
        assert_inside(installed_path, codex_home)

        marker = installed_path / ".reinstall-marker"
        marker.write_text("старый кэш", encoding="utf-8")
        repeated = run_json([codex, "plugin", "add", PLUGIN_ID, "--json"], env=env)
        assert repeated["version"] == expected_plugin_version()
        assert not marker.exists(), "повторная установка не заменила старый cache"

        if args.ref:
            upgraded = run_json(
                [codex, "plugin", "marketplace", "upgrade", MARKETPLACE_NAME, "--json"],
                env=env,
            )
            assert upgraded.get("errors", []) == []

        listed = run_json([codex, "plugin", "list", "--json"], env=env)
        matches = [item for item in listed["installed"] if item["pluginId"] == PLUGIN_ID]
        assert len(matches) == 1
        assert matches[0]["enabled"] is True
        assert matches[0]["version"] == expected_plugin_version()

        run_json([codex, "plugin", "remove", PLUGIN_ID, "--json"], env=env)
        run_json(
            [codex, "plugin", "marketplace", "remove", MARKETPLACE_NAME, "--json"],
            env=env,
        )
        final_state = run_json([codex, "plugin", "list", "--json"], env=env)
        assert all(item["pluginId"] != PLUGIN_ID for item in final_state["installed"])

    if args.ref:
        print("Git marketplace: установка, переустановка, обновление и удаление проверены.")
    else:
        print("Локальный marketplace: установка, переустановка и удаление проверены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
