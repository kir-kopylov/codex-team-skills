from __future__ import annotations

import re
from pathlib import Path

from conftest import ROOT, load_registry, skill_dirs


def test_team_ready_skills_are_in_catalog() -> None:
    catalog = (ROOT / "catalog.md").read_text(encoding="utf-8")

    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        if registry.get("status") != "team-ready":
            continue
        assert skill_dir.name in catalog
        assert f"plugins/team-skills/skills/{skill_dir.name}/SKILL.md" in catalog
        for trigger in registry["natural_triggers"][:1]:
            assert trigger in catalog or "First request" in catalog


def test_markdown_links_resolve() -> None:
    files = [ROOT / "README.md", ROOT / "catalog.md", ROOT / "quickstart.md", ROOT / "CONTRIBUTING.md"]
    for file in files:
        content = file.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
            if "://" in target or target.startswith("#"):
                continue
            path = (file.parent / target).resolve()
            assert path.exists(), f"{file} has broken link: {target}"

