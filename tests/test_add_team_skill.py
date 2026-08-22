from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "add-team-skill"


def test_add_team_skill_requires_isolated_test_preflight():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "pyproject.toml",
        "pytest-cov",
        "временную venv",
        "codex --version",
        "LOCAL_NATIVE_SMOKE_BLOCKED",
        "git clone --no-hardlinks",
        "не доустанавливайте пакеты в глобальный Python",
    ):
        assert required in text


def test_add_team_skill_gates_pr_mutation_on_separate_validation():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "check_pr_governance.py metadata --event-path",
        "наблюдаемого кода возврата `0`",
        "отдельным вызовом выполните `gh pr create --body-file",
        "gh pr view",
        "git ls-remote --heads origin",
        "полный `gh pr checks",
        "старый зелёный job не подтверждает новые метаданные",
        "простой rerun старого job может использовать прежний event payload",
    ):
        assert required in text


def test_add_team_skill_registry_covers_observed_failure_classes():
    metadata = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))
    registry = yaml.safe_load(
        (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    )

    ids = {item["id"] for item in registry["exceptions"]}
    assert {
        "missing-test-extras-in-system-python",
        "broken-codex-wrapper-treated-as-skill-failure",
        "local-clone-hardlink-failure",
        "pr-mutation-runs-after-failed-validation",
        "stale-pr-governance-after-metadata-edit",
        "verbose-consent-card-hides-decision",
        "static-green-wrong-first-response",
    } <= ids
    for relative_path in metadata["example_files"]:
        assert (SKILL_DIR / relative_path).is_file()


def test_add_team_skill_gates_commit_on_observed_first_response():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-02-team-ready.md").read_text(
        encoding="utf-8"
    )

    required = (
        "дословную естественную фразу запуска",
        "До запуска зафиксируйте",
        "от одного до трёх наблюдаемых признаков",
        "свежий контекст",
        "только первый ответ",
        "`BEHAVIOR_PROBE_PASS`",
        "`BEHAVIOR_PROBE_FAIL`",
        "`BEHAVIOR_PROBE_BLOCKED`",
        "не делайте commit",
        "Структурный pytest не исполняет модель",
    )
    for fragment in required:
        assert fragment in text

    assert text.index("До запуска зафиксируйте") < text.index("Откройте свежий контекст")
    assert "не предлагает оплату" in example
    assert "открывает commit" in example
