from __future__ import annotations

import re
from pathlib import Path

from conftest import ROOT, load_registry, skill_dirs


def _phrase_column_index(catalog_lines: list[str]) -> int:
    """Locate the 0-based index of the "Первая фраза для Codex" table column.

    Found by name from the header row so the check survives column reordering
    rather than hardcoding a position."""
    for line in catalog_lines:
        stripped = line.strip()
        if stripped.startswith("|") and "Первая фраза" in stripped:
            headers = [cell.strip() for cell in stripped.strip("|").split("|")]
            for index, header in enumerate(headers):
                if "Первая фраза" in header:
                    return index
    raise AssertionError("catalog.md must have a 'Первая фраза для Codex' column")


def test_team_ready_and_experimental_skills_are_in_catalog() -> None:
    # experimental skill раздаётся команде, поэтому должен быть находим в каталоге
    catalog = (ROOT / "catalog.md").read_text(encoding="utf-8")
    catalog_lines = catalog.splitlines()
    phrase_col = _phrase_column_index(catalog_lines)

    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        if registry.get("status") not in {"team-ready", "experimental"}:
            continue
        assert skill_dir.name in catalog
        skill_link = f"plugins/team-skills/skills/{skill_dir.name}/SKILL.md"
        assert skill_link in catalog

        # Meaningful routing check (no escape hatch): the team-ready skill's OWN
        # catalog row must carry a real, non-empty "Первая фраза для Codex" cell —
        # the phrase a colleague pastes into Codex to route to this skill. We pin
        # to the row identified by skill_link, so this depends only on team-ready
        # trigger phrases, never on the column header or other catalog prose.
        row_cells = None
        for line in catalog_lines:
            stripped = line.strip()
            if stripped.startswith("|") and skill_link in stripped:
                row_cells = [cell.strip() for cell in stripped.strip("|").split("|")]
                break
        assert row_cells is not None, f"{skill_dir.name} must have a catalog table row"
        assert phrase_col < len(row_cells), f"{skill_dir.name} row is missing the phrase column"

        phrase = row_cells[phrase_col].strip().strip("`").strip()
        assert phrase and phrase not in {"...", "—", "-", "TBD", "TODO"}, (
            f"{skill_dir.name} must have a non-empty 'Первая фраза для Codex' cell in catalog.md"
        )


def test_markdown_links_resolve() -> None:
    files = [
        ROOT / "README.md",
        ROOT / "catalog.md",
        ROOT / "quickstart.md",
        ROOT / "START_HERE_CONNECT_CODEX_SKILLS.md",
        ROOT / "admin-onboarding-guide.md",
        ROOT / "CONTRIBUTING.md",
        ROOT / "language-policy.md",
        ROOT / "docs" / "platform-overview.md",
        ROOT / "docs" / "seed-skill-example.md",
        ROOT / "docs" / "skill-exception-learning.md",
    ]
    for file in files:
        content = file.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", content):
            if "://" in target or target.startswith("#"):
                continue
            path = (file.parent / target).resolve()
            assert path.exists(), f"{file} has broken link: {target}"
