from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from conftest import ROOT, skill_dirs


SCRIPT = ROOT / "scripts" / "pull-skills.sh"


def run_sync(destination: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CLAUDE_SKILLS_DIR"] = str(destination)
    env["TEAM_SKILLS_PULL"] = "0"  # детерминизм: без сетевого git pull в тестах
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )


def write_skill(path: Path, name: str, body: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {name}\n---\n\n# {name}\n\n{body}\n",
        encoding="utf-8",
    )


def test_claude_sync_copies_repo_skills_and_preserves_local_only(tmp_path: Path) -> None:
    destination = tmp_path / "claude skills with space"
    local_only = destination / "local-only"
    write_skill(local_only, "local-only", "Личный скилл пользователя.")

    result = run_sync(destination)

    assert "Готово: установлено скиллов" in result.stdout
    assert (local_only / "SKILL.md").read_text(encoding="utf-8").endswith("Личный скилл пользователя.\n")
    for skill_dir in skill_dirs():
        if (skill_dir / "SKILL.md").exists():
            assert (destination / skill_dir.name / "SKILL.md").exists()


def test_claude_sync_is_idempotent_and_updates_repo_managed_skills(tmp_path: Path) -> None:
    destination = tmp_path / "claude skills with space"
    run_sync(destination)

    managed_skill = skill_dirs()[0]
    installed_skill = destination / managed_skill.name
    (installed_skill / "SKILL.md").write_text("stale local copy\n", encoding="utf-8")

    run_sync(destination)

    assert (installed_skill / "SKILL.md").read_text(encoding="utf-8") == (
        managed_skill / "SKILL.md"
    ).read_text(encoding="utf-8")

    before = sorted(path.relative_to(destination) for path in destination.rglob("*"))
    run_sync(destination)
    after = sorted(path.relative_to(destination) for path in destination.rglob("*"))
    assert before == after


def test_claude_sync_fails_when_repo_skill_source_is_missing(tmp_path: Path) -> None:
    broken_root = tmp_path / "repo without skills"
    broken_script = broken_root / "scripts" / "pull-skills.sh"
    broken_script.parent.mkdir(parents=True)
    shutil.copy2(SCRIPT, broken_script)

    env = os.environ.copy()
    env["CLAUDE_SKILLS_DIR"] = str(tmp_path / "destination")
    env["TEAM_SKILLS_PULL"] = "0"  # детерминизм: без сетевого git pull в тестах
    result = subprocess.run(
        ["bash", str(broken_script)],
        cwd=broken_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode != 0
    assert "Не найдена папка скиллов репозитория" in result.stderr
