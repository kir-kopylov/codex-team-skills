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
        "выбранный до одобрения режим границы",
        "По умолчанию `strict-base`",
        "Режим `target-only` допустим",
        "до одобрения явно согласился",
        "Менять режим после одобрения нельзя",
        "git remote get-url --all \"<remote>\"",
        "git remote get-url --push --all \"<remote>\"",
        "Без сырого вывода в tool log",
        "оба списка должны содержать ровно один и тот же URL",
        "к этой URL не должна применяться ни одна `url.*.insteadOf` или `url.*.pushInsteadOf`",
        "имя `origin` или уже раскрытая URL не исключают повторную подстановку адреса",
        "destination должен быть без встроенного пароля или token",
        "настройте credential-free destination",
        "staged tree из `git write-tree`",
        "git ls-remote --heads \"<destination>\" \"<base-full-ref>\" \"<target-full-ref>\"",
        "\"<approved-push-destination>\"",
        "OID base и target либо подтверждённое отсутствие target",
        "при существующем target OID HEAD должен точно совпадать с OID target",
        "при отсутствии target OID HEAD должен точно совпадать с OID base",
        "пересоберите кандидата от точного удалённого состояния",
        "если существует `MERGE_HEAD`, он должен содержать ровно один OID",
        "совпадающий с OID base",
        "Дополнительные merge parents требуют пересборки",
        "HEAD как первого будущего parent",
        "все OID из него как остальных будущих parents",
        "ожидаемый merge-base base и будущего commit",
        "для обычного commit",
        "для merge с base среди `MERGE_HEAD`",
        "Merge без base среди будущих parents этим правилом не публикуйте",
        "точный снимок будущих метаданных commit",
        "сообщение побайтово",
        "author и committer с name, email, date и timezone",
        "сообщение побайтово, включая trailers",
        "режим подписи и полный ожидаемый набор headers с их значениями",
        "Не подменяйте этот снимок текущими значениями Git config",
        "требует отдельного показа и нового одобрения после создания, но до push",
        "Покажите пользователю этот снимок метаданных",
        "git diff --cached <expected-merge-base-oid> --",
        "git diff --cached <target-oid> --",
        "tree diff не доказывает отсутствие промежуточной неопубликованной истории",
        "не заменяет точное совпадение HEAD с target или base",
        "Непосредственно перед `commit`",
        "сравните все зафиксированные значения",
        "полный список будущих parents",
        "метаданные commit",
        "Только после успешного сравнения создайте commit из одобренных значений",
        "явно передайте точные bytes сообщения",
        "author/committer identities, timestamps/timezones",
        "не оставляйте их Git config или текущему времени",
        "режим границы",
        "destination и отсутствие URL-подстановок",
        "Ошибка обновления или любое изменение запрещает `commit`, `push`, создание и обновление PR",
        "упорядоченный список его parents — с одобренным списком",
        "merge-base base и commit — с ожидаемым merge-base",
        "не выводя неожиданные raw metadata в tool log",
        "git cat-file commit \"<verified-commit-oid>\"",
        "побайтово сравните его headers и сообщение с одобренным снимком",
        "Любой дополнительный header",
        "внесённое hook-ом",
        "делает commit новым кандидатом",
        "Перед `push` снова сравните destination и отсутствие URL-подстановок",
        "перечитайте с него base/target",
        "\"<verified-commit-oid>:refs/heads/<target>\"",
        "\"--force-with-lease=refs/heads/<target>:<approved-target-oid>\"",
        "\"--force-with-lease=refs/heads/<target>:\"",
        "пустой expect требует его отсутствия",
        "lease — только server-side CAS для обновляемого target ref",
        "сам по себе может разрешить non-fast-forward",
        "gates обязаны отдельно доказать нужную ancestry",
        "no-op refspec для base не создают server-side cross-ref CAS",
        "остановитесь до push, пока не доказан такой серверный guard",
        "Только в заранее одобренном режиме `target-only`",
        "После `push`, но до работы с PR, прямым `git ls-remote` с одобренного destination",
        "OID target — указывать ровно на этот commit",
        "имена head/base PR должны совпасть с ожидаемыми ветками",
        "OID head PR должен совпасть с проверенным OID target",
        "OID base PR не заменяет повторную проверку живого OID удалённой base",
        "получите новое одобрение",
    ):
        assert invariant in section

    approval_index = section.index("Получите явное одобрение")
    for preapproval_gate in (
        "выбранный до одобрения режим границы",
        "git remote get-url --push --all \"<remote>\"",
        "git ls-remote --heads \"<destination>\" \"<base-full-ref>\" \"<target-full-ref>\"",
        "при существующем target OID HEAD должен точно совпадать с OID target",
        "если существует `MERGE_HEAD`, он должен содержать ровно один OID",
        "точный снимок будущих метаданных commit",
        "git diff --cached <expected-merge-base-oid> --",
    ):
        assert section.index(preapproval_gate) < approval_index

    precommit_check_index = section.index("Непосредственно перед `commit`")
    stop_index = section.index("Ошибка обновления или любое изменение запрещает `commit`")
    commit_creation_index = section.index(
        "Только после успешного сравнения создайте commit из одобренных значений"
    )
    metadata_check_index = section.index('git cat-file commit "<verified-commit-oid>"')
    push_index = section.index("Push выполняйте")
    assert (
        approval_index
        < precommit_check_index
        < stop_index
        < commit_creation_index
        < metadata_check_index
        < push_index
    )

    assert "<approved-commit-oid>" not in section
    assert section.count('"--force-with-lease=refs/heads/<target>:') == 2
