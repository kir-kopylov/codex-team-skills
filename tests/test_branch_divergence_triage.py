from __future__ import annotations

import subprocess
import sys

from conftest import ROOT

SCRIPT = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "branch-divergence-triage"
    / "scripts"
    / "classify_divergence.py"
)


def test_classifier_selftest_passes() -> None:
    # Скрипт выносит вердикт-гейт, поэтому обязан уметь доказать, что сам различает классы.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--selftest"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"самотест классификатора не прошёл:\n{result.stdout}\n{result.stderr}"
    )


def test_classifier_requires_repo_and_branch() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "ОШИБКА" in result.stderr
