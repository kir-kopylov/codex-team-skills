from __future__ import annotations

import re
from datetime import date

from conftest import assert_nonempty_list, load_registry, skill_dirs


ALLOWED_STATUSES = {"draft", "team-ready", "deprecated", "internal-only"}


def test_skill_yaml_schema() -> None:
    required = {
        "owner",
        "status",
        "summary",
        "use_cases",
        "do_not_use_for",
        "natural_triggers",
        "example_files",
        "last_reviewed",
    }

    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        assert required <= set(registry), f"{skill_dir.name} missing registry keys"
        assert isinstance(registry["owner"], str) and registry["owner"].startswith("@")
        assert registry["status"] in ALLOWED_STATUSES
        assert isinstance(registry["summary"], str) and registry["summary"].strip()
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", str(registry["last_reviewed"]))
        date.fromisoformat(str(registry["last_reviewed"]))

        for key in ("use_cases", "do_not_use_for", "natural_triggers", "example_files"):
            assert_nonempty_list(registry, key, skill_dir / "skill.yaml")


def test_owner_and_optional_authors_are_not_placeholders() -> None:
    forbidden_owners = {"@owner", "@github-login", "@needs-owner", "@todo"}

    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        assert registry["owner"] not in forbidden_owners, f"{skill_dir.name} has placeholder owner"

        if "authors" in registry:
            assert_nonempty_list(registry, "authors", skill_dir / "skill.yaml")
            assert all(not author.startswith("@") for author in registry["authors"]), (
                f"{skill_dir.name} authors should preserve human authorship, not duplicate owner handles"
            )
            assert registry.get("source_asset"), f"{skill_dir.name} with authors should explain source_asset"


def test_deprecated_skills_explain_replacement_or_reason() -> None:
    for skill_dir in skill_dirs():
        registry = load_registry(skill_dir)
        if registry.get("status") == "deprecated":
            assert registry.get("replacement") or registry.get("deprecation_reason"), (
                f"{skill_dir.name} is deprecated but has no replacement or reason"
            )
