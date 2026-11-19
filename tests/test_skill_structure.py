from __future__ import annotations

import pytest
import yaml

from conftest import (
    NAME_RE,
    ROOT,
    SKILLS_DIR,
    assert_nonempty_list,
    load_frontmatter,
    load_registry,
    skill_dirs,
)


ALLOWED_FRONTMATTER_KEYS = {"name", "description", "license", "allowed-tools", "metadata"}


@pytest.mark.parametrize(
    ("skill_id", "title", "legacy_phrase"),
    [
        (
            "otbor-navykov-iz-chata",
            "Предложи навыки и патчи из чата",
            "изучи этот чат и предложи навыки",
        ),
        (
            "kontrakt-navyka-do-sborki",
            "Попробуй собрать контракт навыка",
            "спроектируй контракт skill",
        ),
        (
            "navyk-iz-chastogo-zaprosa",
            "Сделай из промпта команду",
            "сделай из промпта быструю команду",
        ),
        (
            "dobavlenie-navyka-v-biblioteku",
            "Добавь в командную библиотеку",
            "добавь новый skill",
        ),
        (
            "pravilo-iz-zhurnala-sboev",
            "разбери ошибки навыка",
            "разбери exception log skill",
        ),
    ],
)
def test_authoring_skill_title_is_its_invocation(
    skill_id: str, title: str, legacy_phrase: str
) -> None:
    """Одно название на всех поверхностях, прежний ID и вход сохранены.

    Проверка согласованности файлов не доказывает выбор навыка моделью:
    распознавание новых и прежних фраз проверяется отдельной живой пробой.
    """
    skill_dir = SKILLS_DIR / skill_id
    frontmatter, body = load_frontmatter(skill_dir / "SKILL.md")
    registry = load_registry(skill_dir)
    interface = yaml.safe_load(
        (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
    )["interface"]

    assert frontmatter["name"] == skill_id
    assert title in frontmatter["description"]
    assert body.strip().splitlines()[0] == f"# {title}"
    assert f"Применяю **«{title}»**:" in body
    assert interface["display_name"] == title
    assert interface["default_prompt"] == title
    assert registry["natural_triggers"][0] == title
    assert legacy_phrase in registry["natural_triggers"]
    assert f"~/.codex/skill-runs/{skill_id}/usage-feedback.jsonl" in body

    link = f"[{title}](plugins/team-skills/skills/{skill_id}/SKILL.md)"
    rows = [
        line
        for line in (ROOT / "catalog.md").read_text(encoding="utf-8").splitlines()
        if link in line
    ]
    assert len(rows) == 1
    header = next(
        line
        for line in (ROOT / "catalog.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("|") and "Первая фраза для Codex" in line
    )
    phrase_column = [cell.strip() for cell in header.strip("|").split("|")].index(
        "Первая фраза для Codex"
    )
    cells = [cell.strip() for cell in rows[0].strip("|").split("|")]
    assert cells[phrase_column] == f"`{title}`"


def test_each_skill_has_valid_skill_md() -> None:
    skills = skill_dirs()
    assert skills, "At least one skill is required"

    for skill_dir in skills:
        path = skill_dir / "SKILL.md"
        assert path.exists(), f"{skill_dir.name} missing SKILL.md"
        frontmatter, body = load_frontmatter(path)

        assert set(frontmatter) <= ALLOWED_FRONTMATTER_KEYS
        assert frontmatter.get("name") == skill_dir.name
        assert NAME_RE.match(frontmatter["name"])

        description = frontmatter.get("description")
        assert isinstance(description, str) and description.strip()
        assert "TODO" not in description
        assert len(description) <= 1024
        assert body.strip(), f"{path} body cannot be empty"


def test_optional_openai_yaml_is_parseable() -> None:
    for skill_dir in skill_dirs():
        path = skill_dir / "agents" / "openai.yaml"
        if not path.exists():
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path} must be a YAML mapping"
        interface = data.get("interface", {})
        assert interface.get("display_name")
        assert interface.get("short_description")
        prompt = interface.get("default_prompt", "")
        registry = load_registry(skill_dir)
        natural_triggers = registry.get("natural_triggers", [])
        prompt_lower = prompt.lower()
        assert (
            skill_dir.name in prompt
            or "сделай" in prompt_lower
            or "use " in prompt_lower
            or any(trigger.lower() in prompt_lower for trigger in natural_triggers)
        ), (
            f"{path}: default_prompt должен содержать внутреннее имя, понятную "
            "команду или естественную фразу запуска из skill.yaml"
        )


def test_team_ready_and_experimental_skills_have_no_template_todos() -> None:
    # experimental skill раздаётся команде и предлагается через consent-gate,
    # поэтому TODO в нём так же недопустимы, как в team-ready
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        if registry.get("status") not in {"team-ready", "experimental"}:
            continue
        assert "TODO" not in (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        for key in ("use_cases", "do_not_use_for", "natural_triggers"):
            assert_nonempty_list(registry, key, skill_dir / "skill.yaml")


def test_team_ready_skills_have_complete_publish_package() -> None:
    required_files = ("SKILL.md", "skill.yaml", "known-exceptions.yaml")

    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        if registry.get("status") != "team-ready":
            continue

        for name in required_files:
            assert (skill_dir / name).exists(), f"{skill_dir.name} team-ready missing {name}"

        examples_dir = skill_dir / "examples"
        assert examples_dir.is_dir(), f"{skill_dir.name} team-ready missing examples/"
        assert_nonempty_list(registry, "example_files", skill_dir / "skill.yaml")

        listed_examples = set(registry["example_files"])
        actual_examples = {path.relative_to(skill_dir).as_posix() for path in examples_dir.glob("*.md")}
        assert listed_examples == actual_examples, (
            f"{skill_dir.name} team-ready example_files must match examples/*.md exactly: "
            f"listed={sorted(listed_examples)}, actual={sorted(actual_examples)}"
        )
        assert all(path.startswith("examples/") for path in listed_examples), (
            f"{skill_dir.name} team-ready examples must live under examples/"
        )
