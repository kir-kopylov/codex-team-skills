from __future__ import annotations

from conftest import ROOT


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "git-pr-lifecycle-safeguard" / "SKILL.md"


def test_pr_metadata_edit_requires_fresh_pull_request_event() -> None:
    body = SKILL.read_text(encoding="utf-8")
    pr_mode = body.split("## Режим 1: local-wip-to-clean-pr", 1)[1].split(
        "## Режим 2: post-merge-branch-housekeeping", 1
    )[0]
    normalized = " ".join(pr_mode.split())

    for invariant in (
        "старый зелёный job не подтверждает новые метаданные",
        "новый `pull_request` event с уже исправленными метаданными",
        "простой rerun старого job может использовать прежний event payload",
        "Не создавайте бессодержательный commit только ради нового события",
    ):
        assert invariant in normalized
