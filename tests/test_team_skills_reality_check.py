from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "team-skills-reality-check"


def test_reality_check_separates_all_five_layers_and_unknowns():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "удалённый main",
        "marketplace-источник",
        "установленный plugin",
        "личные одноимённые кандидаты",
        "список навыков текущей сессии",
        "UNKNOWN_COMMAND_FAILED",
        "UNKNOWN_NOT_EXPOSED",
        "UNKNOWN_SESSION_NOT_OBSERVED",
    ):
        assert required in text


def test_reality_check_is_read_only_and_does_not_infer_session_from_disk():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "Не восстанавливайте список сессии из cache" in text
    assert "POTENTIAL_PERSONAL_SHADOW" in text
    assert "OBSERVED_PERSONAL_SHADOW" in text
    assert "Не выполнять `marketplace add/upgrade/remove`" in text
    assert "Изменения среды: не выполнялись" in text


def test_reality_check_package_is_complete_and_experimental():
    metadata = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))
    exceptions = yaml.safe_load(
        (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    )

    assert metadata["status"] == "experimental"
    assert len(metadata["example_files"]) == 5
    assert len(exceptions["exceptions"]) >= 5
    for relative_path in metadata["example_files"]:
        assert (SKILL_DIR / relative_path).is_file()
    assert (SKILL_DIR / "references" / "domain-playbook.md").is_file()
