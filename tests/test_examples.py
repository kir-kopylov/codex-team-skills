from __future__ import annotations

from conftest import load_registry, skill_dirs


def test_team_ready_examples_exist_and_are_linked() -> None:
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        if registry.get("status") != "team-ready":
            continue

        example_files = registry["example_files"]
        good = [path for path in example_files if "/good-" in path or path.startswith("examples/good-")]
        anti = [path for path in example_files if "/anti-" in path or path.startswith("examples/anti-")]
        assert len(good) >= 3, f"{skill_dir.name} needs at least 3 good examples"
        assert len(anti) >= 2, f"{skill_dir.name} needs at least 2 anti-examples"

        for relative in example_files:
            path = skill_dir / relative
            assert path.exists(), f"Missing example file: {path}"


def test_examples_have_required_sections() -> None:
    required_sections = ("## Вход", "## Ожидаемое Поведение", "## Нельзя")

    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        for relative in registry["example_files"]:
            path = skill_dir / relative
            content = path.read_text(encoding="utf-8")
            for section in required_sections:
                assert section in content, f"{path} missing {section}"
            if registry.get("status") == "team-ready":
                assert "TODO" not in content, f"{path} still contains TODO"
