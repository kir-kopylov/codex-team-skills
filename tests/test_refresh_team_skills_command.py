from __future__ import annotations

import shutil
import subprocess

from conftest import ROOT


SCRIPT = ROOT / "installer" / "refresh-team-skills.command"


def test_refresh_team_skills_command_automates_update_sync_and_restart() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    assert "Обновляю локальный plugin team-skills до latest release" in content
    assert "Синхронизирую repo-managed skills в Claude skills folder" in content
    assert "Планирую detached restart Codex/Claude desktop apps" in content
    assert "update-team-skills.sh" in content
    assert "pull-skills.sh" in content
    assert "dopsoglasheniya-po-oplate" in content


def test_refresh_team_skills_command_validate_only() -> None:
    if not shutil.which("zsh"):
        return

    subprocess.run(
        ["zsh", str(SCRIPT), "--validate-only"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
