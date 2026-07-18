from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "installer" / "remove-team-skills-autoupdate.command"


pytestmark = pytest.mark.skipif(shutil.which("zsh") is None, reason="для проверки нужен zsh")


def make_fake_launchctl(tmp_path: Path, *, loaded: bool = False) -> Path:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    state = tmp_path / "launchctl-loaded"
    if loaded:
        state.write_text("loaded", encoding="utf-8")
    launchctl = fake_bin / "launchctl"
    launchctl.write_text(
        "#!/bin/sh\n"
        f"state={str(state)!r}\n"
        'case "$1" in\n'
        '  print) test -f "$state" ;;\n'
        '  bootout) rm -f "$state"; exit 0 ;;\n'
        '  *) exit 1 ;;\n'
        "esac\n",
        encoding="utf-8",
    )
    launchctl.chmod(0o755)
    ps = fake_bin / "ps"
    ps.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ps.chmod(0o755)
    return fake_bin


def legacy_root(home: Path, *, custom: bool = False) -> Path:
    if custom:
        return home / "Legacy" / "CodexTeamSkills"
    return home / "Library" / "Application Support" / "CodexTeamSkills"


def create_legacy_root(home: Path, *, custom: bool = False) -> Path:
    root = legacy_root(home, custom=custom)
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    for name in ("bootstrap-team-skills.sh", "update-team-skills.sh"):
        (bin_dir / name).write_text("#!/usr/bin/env zsh\nexit 0\n", encoding="utf-8")
    (root / "state").mkdir()
    (root / "state" / "state.json").write_text("{}\n", encoding="utf-8")
    return root


def add_full_historical_release_bin(root: Path) -> None:
    bin_dir = root / "bin"
    historical_names = {
        "bootstrap-team-skills.ps1",
        "install-team-skills.cmd",
        "install-team-skills.command",
        "install-team-skills.ps1",
        "pull-skills.sh",
        "refresh-team-skills.command",
        "team-skills-public-key.pem",
        "team-skills-registry.py",
        "team-skills-status.command",
        "team-skills-status.ps1",
        "uninstall-team-skills.command",
        "uninstall-team-skills.ps1",
        "update-team-skills.ps1",
    }
    for name in historical_names:
        (bin_dir / name).write_text("historical release asset\n", encoding="utf-8")
    pycache = bin_dir / "__pycache__"
    pycache.mkdir()
    (pycache / "team-skills-registry.cpython-314.pyc").write_bytes(b"bytecode")


def write_exact_plist(home: Path, root: Path, *, label: str = "com.codex-team-skills.autoupdate") -> Path:
    plist_path = home / "Library" / "LaunchAgents" / "com.codex-team-skills.autoupdate.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    logs = home / "Library" / "Logs"
    payload = {
        "Label": label,
        "ProgramArguments": ["/bin/zsh", str(root / "bin" / "bootstrap-team-skills.sh")],
        "StartInterval": 172800,
        "RunAtLoad": False,
        "StandardOutPath": str(logs / "codex-team-skills-autoupdate.log"),
        "StandardErrorPath": str(logs / "codex-team-skills-autoupdate.err"),
    }
    with plist_path.open("wb") as handle:
        plistlib.dump(payload, handle)
    return plist_path


def create_protected(home: Path) -> dict[Path, bytes]:
    files = {
        home / "plugins" / "team-skills" / "SKILL.md": b"plugin\n",
        home / ".agents" / "plugins" / "marketplace.json": b'{"plugins": []}\n',
        home / ".codex" / "config.toml": b"model = 'test'\n",
        home / ".codex" / "plugins" / "cache" / "codex-team-skills" / "cache.txt": b"cache\n",
        home / "plugins" / "team-skills.previous.1" / "keep.txt": b"previous\n",
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return files


def run_cleanup(
    home: Path,
    fake_bin: Path,
    mode: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    if extra_env:
        environment.update(extra_env)
    return subprocess.run(
        ["zsh", str(SCRIPT), mode],
        text=True,
        capture_output=True,
        env=environment,
        timeout=20,
        check=False,
    )


def test_dry_run_is_read_only_and_reports_exact_objects(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home, custom=True)
    plist = write_exact_plist(home, root)
    protected = create_protected(home)
    fake_bin = make_fake_launchctl(tmp_path, loaded=True)
    before = {path: path.read_bytes() for path in [plist, *protected]}

    result = run_cleanup(home, fake_bin, "--dry-run")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Результат: DRY_RUN_SAFE" in result.stdout
    assert f"LaunchAgent: {plist}" in result.stdout
    assert f"Updater root: {root}" in result.stdout
    assert root.is_dir()
    assert {path: path.read_bytes() for path in before} == before


def test_apply_removes_exact_legacy_objects_and_preserves_protected_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home, custom=True)
    plist = write_exact_plist(home, root)
    logs = home / "Library" / "Logs"
    logs.mkdir(parents=True, exist_ok=True)
    stdout_log = logs / "codex-team-skills-autoupdate.log"
    stderr_log = logs / "codex-team-skills-autoupdate.err"
    stdout_log.write_text("out\n", encoding="utf-8")
    stderr_log.write_text("err\n", encoding="utf-8")
    protected = create_protected(home)
    fake_bin = make_fake_launchctl(tmp_path, loaded=True)

    result = run_cleanup(home, fake_bin, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Результат: CLEANED" in result.stdout
    assert not root.exists()
    assert not plist.exists()
    assert not stdout_log.exists()
    assert not stderr_log.exists()
    for path, content in protected.items():
        assert path.read_bytes() == content


def test_full_historical_release_bin_is_accepted(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home, custom=True)
    add_full_historical_release_bin(root)
    write_exact_plist(home, root)
    fake_bin = make_fake_launchctl(tmp_path, loaded=True)

    result = run_cleanup(home, fake_bin, "--dry-run")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Результат: DRY_RUN_SAFE" in result.stdout
    assert root.is_dir()


def test_unknown_registry_bytecode_is_refused(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home, custom=True)
    add_full_historical_release_bin(root)
    (root / "bin" / "__pycache__" / "foreign.cpython-314.pyc").write_bytes(b"unknown")
    plist = write_exact_plist(home, root)
    fake_bin = make_fake_launchctl(tmp_path, loaded=True)

    result = run_cleanup(home, fake_bin, "--apply")

    assert result.returncode == 3, result.stdout + result.stderr
    assert "Результат: REFUSED_UNSAFE" in result.stdout
    assert root.exists()
    assert plist.exists()


def test_apply_is_idempotent_after_canonical_fallback_cleanup(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home)
    protected = create_protected(home)
    fake_bin = make_fake_launchctl(tmp_path)

    first = run_cleanup(home, fake_bin, "--apply")
    second = run_cleanup(home, fake_bin, "--apply")

    assert first.returncode == 0, first.stdout + first.stderr
    assert "Результат: CLEANED" in first.stdout
    assert second.returncode == 0, second.stdout + second.stderr
    assert "Результат: NOT_FOUND" in second.stdout
    for path, content in protected.items():
        assert path.read_bytes() == content


def test_env_overrides_are_active_and_defaults_and_state_paths_remain_protected(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home)
    defaults = create_protected(home)
    active_plugin = home / "active" / "plugin"
    active_marketplace = home / "active" / "marketplace.json"
    active_config = home / "active" / "config.toml"
    active_cache = home / "active" / "cache"
    state_only_recovery = home / "recovery" / "cache.stale.1"
    active_files = {
        active_plugin / "SKILL.md": b"active plugin\n",
        active_marketplace: b'{"active": true}\n',
        active_config: b"active = true\n",
        active_cache / "cache.txt": b"active cache\n",
        state_only_recovery / "keep.txt": b"state protected\n",
    }
    for path, content in active_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    state_path = root / "state" / "state.json"
    state_path.write_text(
        json.dumps({"codex_plugin_cache_invalidated_path": str(state_only_recovery)}) + "\n",
        encoding="utf-8",
    )
    fake_bin = make_fake_launchctl(tmp_path)
    overrides = {
        "CODEX_TEAM_SKILLS_PLUGIN_DIR": str(active_plugin),
        "CODEX_TEAM_SKILLS_MARKETPLACE": str(active_marketplace),
        "CODEX_TEAM_SKILLS_CODEX_CONFIG": str(active_config),
        "CODEX_TEAM_SKILLS_CODEX_PLUGIN_CACHE_DIR": str(active_cache),
    }

    result = run_cleanup(home, fake_bin, "--apply", extra_env=overrides)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"Активный plugin: {active_plugin}" in result.stdout
    assert f"Активный marketplace: {active_marketplace}" in result.stdout
    assert f"Активный config: {active_config}" in result.stdout
    assert f"Активный cache: {active_cache}" in result.stdout
    assert "Protected set SHA-256" in result.stdout
    for path, content in {**defaults, **active_files}.items():
        assert path.read_bytes() == content


def test_canonical_root_without_updater_markers_is_not_removed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = legacy_root(home)
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    one_shot_support = bin_dir / "uninstall-team-skills.command"
    one_shot_support.write_text("#!/usr/bin/env zsh\nexit 0\n", encoding="utf-8")
    fake_bin = make_fake_launchctl(tmp_path)

    result = run_cleanup(home, fake_bin, "--apply")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Результат: NOT_FOUND" in result.stdout
    assert one_shot_support.is_file()


def test_state_path_is_only_additional_protection_not_a_deletion_target(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home)
    state_path = root / "state" / "state.json"
    state_path.write_text(json.dumps({"plugin_path": str(root / "logs")}) + "\n", encoding="utf-8")
    fake_bin = make_fake_launchctl(tmp_path)

    result = run_cleanup(home, fake_bin, "--apply")

    assert result.returncode == 3, result.stdout + result.stderr
    assert "Результат: REFUSED_UNSAFE" in result.stdout
    assert root.exists()


@pytest.mark.parametrize(
    "unsafe_kind",
    ["unknown-bin", "wrong-label", "symlink", "parent-symlink", "recovery"],
)
def test_unsafe_attribution_refuses_before_mutation(tmp_path: Path, unsafe_kind: str) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home, custom=True)
    label = "com.codex-team-skills.autoupdate"
    if unsafe_kind == "unknown-bin":
        (root / "bin" / "not-owned.txt").write_text("no\n", encoding="utf-8")
    elif unsafe_kind == "wrong-label":
        label = "com.example.not-team-skills"
    elif unsafe_kind == "symlink":
        (root / "logs").mkdir()
        (root / "logs" / "linked.log").symlink_to(tmp_path / "outside")
    elif unsafe_kind == "parent-symlink":
        moved_parent = tmp_path / "moved-legacy"
        (home / "Legacy").rename(moved_parent)
        (home / "Legacy").symlink_to(moved_parent, target_is_directory=True)
    elif unsafe_kind == "recovery":
        (root / "state" / "state.previous.1").write_text("keep\n", encoding="utf-8")
    plist = write_exact_plist(home, root, label=label)
    protected = create_protected(home)
    fake_bin = make_fake_launchctl(tmp_path, loaded=True)
    before_plist = plist.read_bytes()

    result = run_cleanup(home, fake_bin, "--apply")

    assert result.returncode == 3, result.stdout + result.stderr
    assert "Результат: REFUSED_UNSAFE" in result.stdout
    assert root.exists()
    assert plist.read_bytes() == before_plist
    for path, content in protected.items():
        assert path.read_bytes() == content


def test_process_stop_contract_is_bounded_and_exact() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert '["ps", "-axo", "pid=,command="]' in content
    assert "shell_match = shell_prefix.match(command)" in content
    assert "is_exact_script_command(shell_match.group(1), path)" in content
    assert 'CURRENT_PIDS="$(list_updater_pids "$CANDIDATE_ROOT")"' in content
    assert 'kill -TERM "$pid"' in content
    assert 'kill -KILL "$pid"' in content
    assert "wait_for_no_processes 100 0.1" in content
    assert "wait_for_no_processes 50 0.1" in content
    assert "wait_for_no_processes 20 0.1" in content


def test_process_discovery_failure_refuses_before_mutation(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home)
    fake_bin = make_fake_launchctl(tmp_path)
    fake_ps = fake_bin / "ps"
    fake_ps.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_ps.chmod(0o755)

    result = run_cleanup(home, fake_bin, "--dry-run")

    assert result.returncode == 3, result.stdout + result.stderr
    assert "Результат: REFUSED_UNSAFE" in result.stdout
    assert root.exists()


def test_failed_deletion_returns_incomplete(tmp_path: Path) -> None:
    home = tmp_path / "home"
    root = create_legacy_root(home)
    fake_bin = make_fake_launchctl(tmp_path)
    fake_rm = fake_bin / "rm"
    fake_rm.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    fake_rm.chmod(0o755)

    result = run_cleanup(home, fake_bin, "--apply")

    assert result.returncode == 4, result.stdout + result.stderr
    assert "Результат: INCOMPLETE" in result.stdout
    assert root.exists()


def test_requires_exactly_one_public_mode(tmp_path: Path) -> None:
    result = subprocess.run(
        ["zsh", str(SCRIPT), "--dry-run", "--apply"],
        text=True,
        capture_output=True,
        timeout=5,
        check=False,
    )

    assert result.returncode == 2
    assert "Использование" in result.stderr
