from __future__ import annotations

import yaml

from conftest import NAME_RE, assert_nonempty_list, load_frontmatter, load_registry, skill_dirs


ALLOWED_FRONTMATTER_KEYS = {"name", "description", "license", "allowed-tools", "metadata"}


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
        assert skill_dir.name in prompt or "сделай" in prompt.lower() or "use " in prompt.lower()


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

