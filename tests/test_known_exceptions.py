from __future__ import annotations

import yaml

from conftest import ROOT, skill_dirs


REQUIRED_EXCEPTION_KEYS = {"symptom", "root_cause", "do_next_time", "source_example"}


def load_known_exceptions(skill_name: str) -> dict:
    path = ROOT / "plugins" / "team-skills" / "skills" / skill_name / "known-exceptions.yaml"
    assert path.exists(), f"{skill_name} должен иметь known-exceptions.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} должен быть YAML mapping"
    return data


def test_known_exceptions_yaml_schema_when_present() -> None:
    for skill_dir in skill_dirs():
        path = skill_dir / "known-exceptions.yaml"
        if not path.exists():
            continue

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path} должен быть YAML mapping"
        assert set(data) <= {"exceptions"}, f"{path} содержит лишние top-level ключи"
        exceptions = data.get("exceptions")
        assert isinstance(exceptions, list), f"{path}: exceptions должен быть списком"

        for index, item in enumerate(exceptions):
            assert isinstance(item, dict), f"{path}: exceptions[{index}] должен быть mapping"
            assert REQUIRED_EXCEPTION_KEYS <= set(item), f"{path}: exceptions[{index}] missing required keys"
            for key in REQUIRED_EXCEPTION_KEYS:
                value = item[key]
                assert isinstance(value, str) and value.strip(), f"{path}: exceptions[{index}].{key} пустой"


def test_new_or_changed_exception_ready_skills_have_file() -> None:
    for skill_name in ("add-team-skill", "skill-exception-reviewer"):
        data = load_known_exceptions(skill_name)
        assert data["exceptions"] == []


def test_new_skill_generator_creates_known_exceptions_template() -> None:
    content = (ROOT / "scripts" / "new_skill.py").read_text(encoding="utf-8")
    assert "known-exceptions.yaml" in content
    assert "exceptions: []" in content
    assert "## Логирование Сбоев" in content
    assert "~/.codex/skill-runs" in content
    assert "exception-log.jsonl" in content


def test_exception_enabled_skills_have_logging_contract() -> None:
    for skill_dir in skill_dirs():
        if not (skill_dir / "known-exceptions.yaml").exists():
            continue

        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "## Логирование Сбоев" in content, f"{skill_dir.name} должен описывать логирование сбоев"
        assert "exception-log.jsonl" in content, f"{skill_dir.name} должен указывать приватный exception log"
        assert "Raw logs не коммитить" in content, f"{skill_dir.name} должен запрещать commit raw logs"
