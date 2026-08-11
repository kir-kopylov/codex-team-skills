from __future__ import annotations

import subprocess
import sys

from conftest import ROOT, load_registry


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "kak-drugie-reshili"


def test_external_practice_skill_has_executable_handoff() -> None:
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(SKILL)

    assert registry["status"] == "experimental"
    assert registry["owner"] == "@kir-kopylov"
    for fragment in (
        "CandidatePacket v1",
        "local_status` всегда равен `NOT_TESTED",
        "stuck-troubleshooting-reframe",
        "scripts/validate_candidate_packet.py",
        "поисковый фрагмент считайте наводкой",
    ):
        assert fragment in body


def test_synthetic_candidate_packet_passes_validator() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SKILL / "scripts" / "validate_candidate_packet.py"),
            str(SKILL / "examples" / "synthetic-candidate-packet.yaml"),
            "--input-contract",
            str(SKILL / "examples" / "synthetic-input-contract.yaml"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "VALID" in result.stdout
    assert "не истинность источника" in result.stdout
