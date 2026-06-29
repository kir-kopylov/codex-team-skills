from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from conftest import ROOT


SCRIPT = ROOT / "installer" / "refresh-team-skills.command"


def test_refresh_team_skills_command_automates_update_sync_and_restart() -> None:
    content = SCRIPT.read_text(encoding="utf-8")
    assert "Обновляю локальный plugin team-skills до latest release" in content
    assert "Синхронизирую repo-managed skills в Claude skills folder" in content
    assert "Планирую detached restart Codex/Claude desktop apps" in content
    assert "update-team-skills.sh" in content
    assert "NEXT_UPDATE_SCRIPT" in content
    assert "NEXT_REFRESH_SCRIPT" in content
    assert "promote_staged_updater" in content
    assert "promote_staged_refresh" in content
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


def test_refresh_team_skills_promotes_staged_updater_before_running(tmp_path: Path) -> None:
    if not shutil.which("zsh"):
        return

    install_root = tmp_path / "CodexTeamSkills"
    bin_dir = install_root / "bin"
    bin_dir.mkdir(parents=True)
    marker = tmp_path / "which-updater-ran.txt"

    update_script = bin_dir / "update-team-skills.sh"
    update_script.write_text(
        f"#!/usr/bin/env zsh\nprintf 'old\\n' > {marker}\n",
        encoding="utf-8",
    )
    update_script.chmod(0o755)

    next_update_script = bin_dir / "update-team-skills.sh.next"
    next_update_script.write_text(
        f"#!/usr/bin/env zsh\nprintf 'next\\n' > {marker}\n",
        encoding="utf-8",
    )
    next_update_script.chmod(0o755)

    sync_script = bin_dir / "pull-skills.sh"
    sync_script.write_text(
        "#!/usr/bin/env zsh\n"
        "mkdir -p \"$CLAUDE_SKILLS_DIR/dopsoglasheniya-po-oplate\"\n"
        "printf '# synced\\n' > \"$CLAUDE_SKILLS_DIR/dopsoglasheniya-po-oplate/SKILL.md\"\n",
        encoding="utf-8",
    )
    sync_script.chmod(0o755)

    status_script = bin_dir / "team-skills-status.command"
    status_script.write_text("#!/usr/bin/env zsh\nexit 0\n", encoding="utf-8")
    status_script.chmod(0o755)

    next_refresh_script = bin_dir / "refresh-team-skills.command.next"
    next_refresh_script.write_text("#!/usr/bin/env zsh\n# next refresh\n", encoding="utf-8")
    next_refresh_script.chmod(0o755)

    result = subprocess.run(
        [
            "zsh",
            str(SCRIPT),
            "--no-restart",
            "--claude-skills-dir",
            str(tmp_path / "claude-skills"),
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "CODEX_TEAM_SKILLS_HOME": str(install_root),
            "CODEX_TEAM_SKILLS_PLUGIN_DIR": str(tmp_path / "plugins" / "team-skills"),
        },
    )

    assert "Updater обновлён из staged .next версии." in result.stdout
    assert "Refresh command обновлена из staged .next версии." in result.stdout
    assert marker.read_text(encoding="utf-8").strip() == "next"
    assert not next_update_script.exists()
    assert not next_refresh_script.exists()
    assert "next" in update_script.read_text(encoding="utf-8")
    assert "next refresh" in (bin_dir / "refresh-team-skills.command").read_text(encoding="utf-8")
