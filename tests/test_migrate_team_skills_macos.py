from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ROOT


SCRIPT = ROOT / "installer" / "migrate-team-skills.command"
RELEASE_TAG = "team-skills-vr999.1-deadbee"


pytestmark = pytest.mark.skipif(shutil.which("zsh") is None, reason="для проверки нужен zsh")


def bake_migrator(tmp_path: Path, *, child_timeout_seconds: int = 600) -> Path:
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count("__TEAM_SKILLS_RELEASE_TAG__") == 1
    assert source.count("CHILD_TIMEOUT_SECONDS=600") == 1
    target = tmp_path / "migrate-team-skills.command"
    target.write_text(
        source.replace("__TEAM_SKILLS_RELEASE_TAG__", RELEASE_TAG).replace(
            "CHILD_TIMEOUT_SECONDS=600",
            f"CHILD_TIMEOUT_SECONDS={child_timeout_seconds}",
        ),
        encoding="utf-8",
    )
    return target


def make_fake_runtime(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    sequence = tmp_path / "sequence.log"

    (fake_bin / "uname").write_text("#!/bin/sh\nprintf 'Darwin\\n'\n", encoding="utf-8")
    (fake_bin / "uname").chmod(0o755)

    python_wrapper = fake_bin / "python3"
    python_wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "${1:-}" = "-" ] && [ "${2:-}" = "canonical-home" ]; then\n'
        "  exit 0\n"
        "fi\n"
        f"exec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    python_wrapper.chmod(0o755)

    cleanup = fixtures / "remove-team-skills-autoupdate.command"
    cleanup.write_text(
        "#!/usr/bin/env zsh\n"
        "set -euo pipefail\n"
        "printf 'cleanup:%s\\n' \"$1\" >> \"$TEST_SEQUENCE_LOG\"\n"
        "case \"$1\" in\n"
        "  --dry-run)\n"
        "    if [[ \"${TEST_FINAL_REFUSED:-0}\" == \"1\" && -e \"$HOME/plugins/team-skills/.codex-plugin/plugin.json\" ]]; then\n"
        "      printf 'TEAM_SKILLS_RESULT=REFUSED_UNSAFE\\n'\n"
        "      exit 3\n"
        "    fi\n"
        "    if [[ -e \"$HOME/legacy-updater-present\" ]]; then\n"
        "      printf 'TEAM_SKILLS_RESULT=DRY_RUN_SAFE\\n'\n"
        "      [[ \"${TEST_BAD_INITIAL_DRY_EXIT:-0}\" != \"1\" ]] || exit 3\n"
        "    else\n"
        "      printf 'TEAM_SKILLS_RESULT=NOT_FOUND\\n'\n"
        "    fi\n"
        "    ;;\n"
        "  --apply)\n"
        "    rm -f -- \"$HOME/legacy-updater-present\"\n"
        "    if [[ \"${TEST_APPLY_REFUSED:-0}\" == \"1\" ]]; then\n"
        "      printf 'TEAM_SKILLS_RESULT=REFUSED_UNSAFE\\n'\n"
        "      exit 3\n"
        "    fi\n"
        "    printf 'TEAM_SKILLS_RESULT=CLEANED\\n'\n"
        "    ;;\n"
        "  *)\n"
        "    printf 'TEAM_SKILLS_RESULT=INVALID_INVOCATION\\n'\n"
        "    exit 2\n"
        "    ;;\n"
        "esac\n",
        encoding="utf-8",
    )

    installer = fixtures / "install-team-skills.command"
    installer.write_text(
        "#!/usr/bin/env zsh\n"
        "set -euo pipefail\n"
        "printf 'installer\\n' >> \"$TEST_SEQUENCE_LOG\"\n"
        "if [[ \"${TEST_INSTALLER_MODE:-success}\" == \"fail\" ]]; then\n"
        "  printf 'TEAM_SKILLS_RESULT=INSTALL_FAILED\\n'\n"
        "  exit 1\n"
        "fi\n"
        "if [[ \"${TEST_INSTALLER_MODE:-success}\" == \"hang\" ]]; then\n"
        "  /bin/sleep 30\n"
        "fi\n"
        "manifest=\"$HOME/plugins/team-skills/.codex-plugin/plugin.json\"\n"
        "mkdir -p -- \"${manifest:h}\"\n"
        "printf '{\"name\":\"team-skills\",\"version\":\"0.1.0-test\",\"release_tag\":\"%s\"}\\n' \"$TEST_RELEASE_TAG\" > \"$manifest\"\n"
        "rm -rf -- \"$HOME/.codex/plugins/cache/codex-team-skills\"\n"
        "if [[ \"${TEST_INSTALLER_MODE:-success}\" == \"regression\" ]]; then\n"
        "  : > \"$HOME/legacy-updater-present\"\n"
        "fi\n"
        "printf 'TEAM_SKILLS_RESULT=INSTALLED\\n'\n"
        "printf 'TEAM_SKILLS_RELEASE=%s\\n' \"$TEST_RELEASE_TAG\"\n"
        "printf 'TEAM_SKILLS_PLUGIN_VERSION=0.1.0-test\\n'\n",
        encoding="utf-8",
    )

    curl = fake_bin / "curl"
    curl.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        "output=\n"
        "url=\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  case \"$1\" in\n"
        "    --output) output=$2; shift 2 ;;\n"
        "    *) url=$1; shift ;;\n"
        "  esac\n"
        "done\n"
        "case \"$url\" in\n"
        "  */remove-team-skills-autoupdate.command)\n"
        "    printf 'download:cleanup\\n' >> \"$TEST_SEQUENCE_LOG\"\n"
        f"    cp {shlex.quote(str(cleanup))} \"$output\"\n"
        "    ;;\n"
        "  */install-team-skills.command)\n"
        "    printf 'download:installer\\n' >> \"$TEST_SEQUENCE_LOG\"\n"
        "    if [ \"${TEST_FAIL_INSTALLER_DOWNLOAD:-0}\" = \"1\" ]; then exit 22; fi\n"
        f"    cp {shlex.quote(str(installer))} \"$output\"\n"
        "    ;;\n"
        "  *) exit 22 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)
    return fake_bin, sequence


def run_migrator(
    tmp_path: Path,
    *,
    legacy_present: bool = False,
    installer_mode: str = "success",
    bad_initial_dry_exit: bool = False,
    fail_installer_download: bool = False,
    final_refused: bool = False,
    apply_refused: bool = False,
    stale_lock_pid: int | None = None,
    child_timeout_seconds: int = 600,
    symlink_plugin_parent: bool = False,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    temp_root = tmp_path / "tmp"
    temp_root.mkdir()
    if legacy_present:
        (home / "legacy-updater-present").touch()
    cache = home / ".codex" / "plugins" / "cache" / "codex-team-skills"
    cache.mkdir(parents=True)
    (cache / "stale.txt").write_text("stale\n", encoding="utf-8")
    if symlink_plugin_parent:
        outside = tmp_path / "outside-plugins"
        outside.mkdir()
        (home / "plugins").symlink_to(outside, target_is_directory=True)

    fake_bin, sequence = make_fake_runtime(tmp_path)
    migrator = bake_migrator(tmp_path, child_timeout_seconds=child_timeout_seconds)
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("CODEX_TEAM_SKILLS_")
    }
    environment.update(
        {
            "HOME": str(home),
            "TMPDIR": str(temp_root),
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "TEST_SEQUENCE_LOG": str(sequence),
            "TEST_RELEASE_TAG": RELEASE_TAG,
            "TEST_INSTALLER_MODE": installer_mode,
            "TEST_BAD_INITIAL_DRY_EXIT": "1" if bad_initial_dry_exit else "0",
            "TEST_FAIL_INSTALLER_DOWNLOAD": "1" if fail_installer_download else "0",
            "TEST_FINAL_REFUSED": "1" if final_refused else "0",
            "TEST_APPLY_REFUSED": "1" if apply_refused else "0",
        }
    )
    if extra_env:
        environment.update(extra_env)
    if stale_lock_pid is not None:
        lock = temp_root / f"codex-team-skills-migrate-{os.getuid()}.lock"
        lock.mkdir(mode=0o700)
        (lock / "pid").write_text(f"{stale_lock_pid}\n", encoding="ascii")

    result = subprocess.run(
        ["zsh", str(migrator)],
        text=True,
        capture_output=True,
        env=environment,
        timeout=20,
        check=False,
    )
    return result, home, sequence


def read_sequence(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def test_validate_only_does_not_require_baked_release_or_touch_product() -> None:
    result = subprocess.run(
        ["zsh", str(SCRIPT), "--validate-only"],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "без выполнения перехода" in result.stdout
    assert "TEAM_SKILLS_MIGRATION_RESULT=VALIDATED" in result.stdout


def test_success_downloads_both_children_before_mutation_and_installs_once(tmp_path: Path) -> None:
    result, home, sequence_path = run_migrator(tmp_path, legacy_present=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=MIGRATED_RESTART_REQUIRED" in result.stdout
    assert read_sequence(sequence_path) == [
        "download:cleanup",
        "download:installer",
        "cleanup:--dry-run",
        "cleanup:--apply",
        "installer",
        "cleanup:--dry-run",
    ]
    manifest = json.loads(
        (home / "plugins" / "team-skills" / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest == {
        "name": "team-skills",
        "version": "0.1.0-test",
        "release_tag": RELEASE_TAG,
    }
    assert not (home / ".codex" / "plugins" / "cache" / "codex-team-skills").exists()
    assert not (home / "legacy-updater-present").exists()
    assert not list((tmp_path / "tmp").glob("codex-team-skills-migrate.*"))
    assert not list((tmp_path / "tmp").glob("codex-team-skills-migrate-*.lock"))


def test_installer_regression_is_cleaned_and_release_is_rejected(tmp_path: Path) -> None:
    result, home, sequence_path = run_migrator(tmp_path, installer_mode="regression")

    assert result.returncode == 6, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=INSTALLER_REGRESSION_CLEANED" in result.stdout
    assert read_sequence(sequence_path) == [
        "download:cleanup",
        "download:installer",
        "cleanup:--dry-run",
        "installer",
        "cleanup:--dry-run",
        "cleanup:--apply",
    ]
    assert read_sequence(sequence_path).count("installer") == 1
    assert not (home / "legacy-updater-present").exists()


def test_second_download_failure_happens_before_cleanup_or_install(tmp_path: Path) -> None:
    result, home, sequence_path = run_migrator(
        tmp_path,
        legacy_present=True,
        fail_installer_download=True,
    )

    assert result.returncode == 10, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=BLOCKED_PREFLIGHT" in result.stdout
    assert read_sequence(sequence_path) == ["download:cleanup", "download:installer"]
    assert (home / "legacy-updater-present").exists()
    assert not (home / "plugins" / "team-skills").exists()


def test_cleanup_token_and_exit_mismatch_stops_before_mutation(tmp_path: Path) -> None:
    result, home, sequence_path = run_migrator(
        tmp_path,
        legacy_present=True,
        bad_initial_dry_exit=True,
    )

    assert result.returncode == 4, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=CLEANUP_INCOMPLETE" in result.stdout
    assert read_sequence(sequence_path) == [
        "download:cleanup",
        "download:installer",
        "cleanup:--dry-run",
    ]
    assert (home / "legacy-updater-present").exists()
    assert not (home / "plugins" / "team-skills").exists()


def test_installer_failure_is_not_retried_and_reports_pending_install(tmp_path: Path) -> None:
    result, home, sequence_path = run_migrator(
        tmp_path,
        legacy_present=True,
        installer_mode="fail",
    )

    assert result.returncode == 5, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=LEGACY_REMOVED_INSTALL_PENDING" in result.stdout
    assert read_sequence(sequence_path) == [
        "download:cleanup",
        "download:installer",
        "cleanup:--dry-run",
        "cleanup:--apply",
        "installer",
    ]
    assert read_sequence(sequence_path).count("installer") == 1
    assert not (home / "legacy-updater-present").exists()
    assert not (home / "plugins" / "team-skills").exists()


def test_hanging_installer_is_killed_once_and_reports_pending(tmp_path: Path) -> None:
    result, home, sequence_path = run_migrator(
        tmp_path,
        installer_mode="hang",
        child_timeout_seconds=1,
    )

    assert result.returncode == 5, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=LEGACY_REMOVED_INSTALL_PENDING" in result.stdout
    assert "превысил timeout 1 секунд" in result.stdout
    assert read_sequence(sequence_path).count("installer") == 1
    assert not (home / "plugins" / "team-skills").exists()


def test_apply_refusal_after_possible_mutation_is_incomplete(tmp_path: Path) -> None:
    result, home, sequence_path = run_migrator(
        tmp_path,
        legacy_present=True,
        apply_refused=True,
    )

    assert result.returncode == 4, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=CLEANUP_INCOMPLETE" in result.stdout
    assert not (home / "legacy-updater-present").exists()
    assert "installer" not in read_sequence(sequence_path)


def test_codex_team_skills_override_is_rejected_before_download(tmp_path: Path) -> None:
    result, home, sequence_path = run_migrator(
        tmp_path,
        extra_env={"CODEX_TEAM_SKILLS_PLUGIN_DIR": str(tmp_path / "other-plugin")},
    )

    assert result.returncode == 10, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=BLOCKED_PREFLIGHT" in result.stdout
    assert "CODEX_TEAM_SKILLS_PLUGIN_DIR" in result.stdout
    assert read_sequence(sequence_path) == []
    assert not (home / "plugins" / "team-skills").exists()


def test_symlink_in_managed_path_is_rejected_before_download(tmp_path: Path) -> None:
    result, _, sequence_path = run_migrator(tmp_path, symlink_plugin_parent=True)

    assert result.returncode == 10, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=BLOCKED_PREFLIGHT" in result.stdout
    assert read_sequence(sequence_path) == []


def test_stale_owned_lock_is_reclaimed(tmp_path: Path) -> None:
    result, _, sequence_path = run_migrator(tmp_path, stale_lock_pid=999_999_999)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=MIGRATED_RESTART_REQUIRED" in result.stdout
    assert "installer" in read_sequence(sequence_path)


def test_refusal_after_install_is_incomplete_not_no_mutation(tmp_path: Path) -> None:
    result, home, sequence_path = run_migrator(tmp_path, final_refused=True)

    assert result.returncode == 4, result.stdout + result.stderr
    assert "TEAM_SKILLS_MIGRATION_RESULT=CLEANUP_INCOMPLETE" in result.stdout
    assert "TEAM_SKILLS_MIGRATION_RESULT=REFUSED_UNSAFE" not in result.stdout
    assert (home / "plugins" / "team-skills" / ".codex-plugin" / "plugin.json").is_file()
    assert read_sequence(sequence_path).count("installer") == 1


def test_invalid_invocation_has_machine_result() -> None:
    result = subprocess.run(
        ["zsh", str(SCRIPT), "--unknown"],
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert "TEAM_SKILLS_MIGRATION_RESULT=INVALID_INVOCATION" in result.stderr


def test_static_contract_has_no_latest_or_persistent_runtime() -> None:
    content = SCRIPT.read_text(encoding="utf-8")

    assert "__TEAM_SKILLS_RELEASE_TAG__" in content
    assert "releases/download/$BAKED_RELEASE_TAG" in content
    assert "releases/latest" not in content
    assert content.count('run_child "installer" "$INSTALLER_SCRIPT"') == 1
    assert '--manifest-url "$RELEASE_BASE/manifest.json"' in content
    assert "CHILD_TIMEOUT_SECONDS=600" in content
    assert "CODEX_TEAM_SKILLS_" in content
    assert "canonical-home" in content
    assert "codex-team-skills-migrate-$CURRENT_UID.lock" in content
    assert "TEAM_SKILLS_MIGRATION_RESULT=%s" in content
    for outcome in (
        "BLOCKED_PREFLIGHT",
        "REFUSED_UNSAFE",
        "CLEANUP_INCOMPLETE",
        "LEGACY_REMOVED_INSTALL_PENDING",
        "INSTALLER_REGRESSION_CLEANED",
        "MIGRATED_RESTART_REQUIRED",
    ):
        assert outcome in content
    for forbidden in (
        "LaunchAgents",
        "state.json",
        "latest.json",
        "Register-ScheduledTask",
    ):
        assert forbidden not in content
