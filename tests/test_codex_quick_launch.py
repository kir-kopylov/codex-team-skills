from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "codex-quick-launch"


def test_personal_skill_uses_documented_discovery_and_invocation() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    playbook = (SKILL_DIR / "references" / "domain-playbook.md").read_text(encoding="utf-8")
    combined = skill + playbook

    for required in (
        r"%USERPROFILE%\.agents\skills\<имя>\SKILL.md",
        "$HOME/.agents/skills/<имя>/SKILL.md",
        "$имя",
        "/skills",
        "ChatGPT Desktop",
        "enabled skills появляются в slash-списке",
        "один restart",
        "фактический запуск проверены",
    ):
        assert required in combined


def test_failed_discovery_cannot_jump_to_plugin_or_config_guess() -> None:
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    anti_example = (SKILL_DIR / "examples" / "anti-03-plugin-detour.md").read_text(
        encoding="utf-8"
    )
    combined = skill + anti_example

    for required in (
        "не создавайте marketplace/plugin для одного личного prompt",
        "не изобретайте `commands/<name>.md`",
        "Не переходите после первой неудачи к новому механизму",
        "вручную переписывать `config.toml`",
    ):
        assert required in combined

    anti_pinning = (SKILL_DIR / "examples" / "anti-01-unverified-pinning.md").read_text(
        encoding="utf-8"
    )
    assert "создаёт разумный alias" not in anti_pinning
    assert "добавлять префикс `00-`" in anti_pinning


def test_new_failure_rules_are_backed_by_shipped_examples() -> None:
    data = yaml.safe_load((SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8"))
    symptoms = "\n".join(item["symptom"] for item in data["exceptions"])

    assert ".codex/skills" in symptoms
    assert "commands/<имя>.md" in symptoms
    assert "installed, enabled" in symptoms
    assert "mojibake" in symptoms

    for item in data["exceptions"]:
        assert (SKILL_DIR / item["source_example"]).exists()
