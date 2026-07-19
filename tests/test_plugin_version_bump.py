from __future__ import annotations

import importlib.util

from conftest import ROOT


SCRIPT = ROOT / "scripts" / "check_plugin_version_bump.py"
spec = importlib.util.spec_from_file_location("check_plugin_version_bump", SCRIPT)
assert spec and spec.loader
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_regular_skill_change_requires_higher_version() -> None:
    errors = check.validate_version_bump(
        ["plugins/team-skills/skills/verify/SKILL.md"],
        base_version="1.2.3",
        head_version="1.2.3",
    )
    assert errors and "не повышена" in errors[0]


def test_patch_minor_and_major_bumps_are_accepted() -> None:
    path = ["plugins/team-skills/skills/verify/SKILL.md"]
    for head in ("1.2.4", "1.3.0", "2.0.0"):
        assert check.validate_version_bump(path, base_version="1.2.3", head_version=head) == []


def test_lower_or_invalid_version_is_rejected() -> None:
    path = ["plugins/team-skills/.codex-plugin/plugin.json"]
    assert check.validate_version_bump(path, base_version="1.2.3", head_version="1.2.2")
    assert check.validate_version_bump(path, base_version="1.2.3", head_version="v1.2.4")


def test_non_plugin_change_does_not_require_bump() -> None:
    assert check.validate_version_bump(
        ["README.md"],
        base_version="1.2.3",
        head_version="1.2.3",
    ) == []
