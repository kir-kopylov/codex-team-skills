from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "skill-exception-reviewer"


def test_reviewer_declares_explicit_single_and_library_modes():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "`ONE_SKILL`" in text
    assert "`LIBRARY_WIDE`" in text
    assert "не выбирайте широкий обход по умолчанию" in text.lower()
    assert "не переходите по символическим ссылкам" in text.lower()


def test_reviewer_treats_logs_as_passive_and_reports_coverage_states():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    assert "пассивный файл" in text
    assert "`NOT_REVIEWED`" in text
    for state in ("NO_LOG_FILE", "EMPTY", "MALFORMED", "REVIEWED"):
        assert f"`{state}`" in text
    assert "это не означает, что сбоев не было" in text


def test_reviewer_registry_covers_scope_failures_and_examples_exist():
    metadata = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))
    registry = yaml.safe_load(
        (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    )

    example_paths = set(metadata["example_files"])
    assert "examples/good-04-library-wide.md" in example_paths
    assert "examples/anti-03-passive-log-auto-review.md" in example_paths
    for relative_path in example_paths:
        assert (SKILL_DIR / relative_path).is_file()

    ids = {item["id"] for item in registry["exceptions"]}
    assert "passive-log-mistaken-for-automation" in ids
    assert "ambiguous-review-scope" in ids
