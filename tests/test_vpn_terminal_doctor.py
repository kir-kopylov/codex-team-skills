from __future__ import annotations

from conftest import ROOT


SKILL = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "vpn-terminal-doctor"
    / "SKILL.md"
)


def test_first_response_contains_observed_network_probes() -> None:
    content = SKILL.read_text(encoding="utf-8")

    assert "Stop-gate: если терминал агента доступен" in content
    assert "до отправки первого ответа обязательно выполните" in content
    assert "две HTTP-пробы из шага 1" in content
    assert "наблюдаемые коды обеих проб" in content
    assert "обещание «сначала проверю» запрещено" in content
    assert "read-only определите транспорт remote" in content
