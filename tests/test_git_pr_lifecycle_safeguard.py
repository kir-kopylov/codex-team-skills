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
        "staged tree из `git write-tree`",
        "удалённых base и target",
        "подтверждённое отсутствие target",
        "HEAD как первого будущего parent",
        "все OID из него как остальных будущих parents",
        "ожидаемый merge-base base и будущего commit",
        "для обычного commit",
        "для merge с base среди `MERGE_HEAD`",
        "Merge без base среди будущих parents этим правилом не публикуйте",
        "git diff --cached <expected-merge-base-oid> --",
        "git diff --cached <target-oid> --",
        "Непосредственно перед `commit`",
        "сравните все зафиксированные значения",
        "полный список будущих parents",
        "Ошибка обновления или любое изменение запрещает `commit`, `push`, создание и обновление PR",
        "упорядоченный список его parents — с одобренным списком",
        "merge-base base и commit — с ожидаемым merge-base",
        "Перед `push` снова обновите remote refs, сравните OID удалённых base и target",
        "отсутствие target с одобренными",
        "После `push`, но до работы с PR, снова успешно обновите remote refs",
        "OID target — указывать ровно на этот commit",
        "имена head/base PR должны совпасть с ожидаемыми ветками",
        "OID head PR должен совпасть с проверенным OID target",
        "OID base PR не заменяет повторную проверку живого OID удалённой base",
        "получите новое одобрение",
    ):
        assert invariant in section

    assert section.index("git diff --cached <expected-merge-base-oid> --") < section.index(
        "Получите явное одобрение"
    )
