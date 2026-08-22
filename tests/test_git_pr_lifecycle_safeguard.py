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


def test_explicit_approval_is_bound_to_the_exact_publish_candidate() -> None:
    text = SKILL.read_text(encoding="utf-8")
    section = text.split("## Явная Граница Одобрения Перед Публикацией", 1)[1]
    section = section.split("\n## ", 1)[0]
    section = " ".join(section.split())

    for invariant in (
        "не добавляет отдельный вопрос об одобрении",
        "пользователь явно потребовал",
        "точный `git diff --cached`",
        "staged tree из `git write-tree`",
        "удалённых base и target",
        "подтверждённое отсутствие target",
        "Перед `commit` и перед `push`",
        "Ошибка обновления или любое изменение запрещает `commit`, `push`, создание и обновление PR",
        "Tree commit должен совпасть с одобренным tree",
        "После `push`, но до работы с PR, снова успешно обновите remote refs",
        "OID target — указывать ровно на этот commit",
        "OID head PR должен совпасть с проверенным OID target",
        "OID base PR — с одобренным OID base",
        "получите новое одобрение",
    ):
        assert invariant in section

    assert section.index("Получите явное одобрение") < section.index(
        "Перед `commit` и перед `push`"
    )
