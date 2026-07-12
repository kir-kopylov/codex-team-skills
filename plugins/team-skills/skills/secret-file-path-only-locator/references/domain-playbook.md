# Domain Playbook

## Что Нельзя Потерять

- Coverage строится до утверждений о полноте.
- Scanner проверяется на синтетическом corpus до реальных данных.
- Output содержит только safe pointer, дату, категорию, risk, confidence и действие.
- Cleanup всегда revoke-first и batch-confirmed.
- Versions, trash, backups, shared documents и history являются отдельными поверхностями.
- Approved vault и password manager не считаются утечкой сами по себе.
- Active incident и legal hold запрещают уничтожать evidence.

## Что Надо Обезличить

- Реальные значения секретов и их части.
- Secret hash, fingerprint, entropy sample и matched line.
- Имена людей, адреса аккаунтов, subject/title с чувствительными данными.
- Личные абсолютные пути, реальные source IDs и приватные названия систем.
- Screenshots, raw exports, логи scanner и content snippets.

## Interface Mechanics

| Source | Включить явно | Безопасный pointer | Стоп |
| --- | --- | --- | --- |
| Local files | Hidden files, sync copies, разрешённые archives | Root alias + relative path + date | Symlink или path выходит за scope; scanner печатает match |
| Git | Worktree, ignored/untracked, history, stashes, submodules по отдельному scope | Repo alias + relative path + commit id | History rewrite без rotate и отдельного approval |
| Mail | Inbox, sent, archive, trash, attachments | Account alias + message/thread id + date; safe subject опционально | Connector неизбежно возвращает body/snippet |
| Cloud docs | Owned/shared-with-user files, comments, versions, trash | Drive alias + file id/link + date; safe title опционально | Shared surface вне полномочий или export раскрывает content |
| Notes | Notes, notebooks, attachments, deleted items | App alias + note id + date; safe title опционально | API/UI возвращает полный note body |
| Chat exports | Только разрешённые пользователю exports и attachments | Export alias + item id + date | Чужой account, private channel вне scope или raw export в отчёт |
| Backups and sync | Device backups, cloud sync, duplicate folders | Backup alias + relative pointer + snapshot date | Restore/decrypt требует новых полномочий |
| Archives | Только разрешённые archives с заданными depth/size limits | Archive alias + inner relative path | Encrypted archive, archive bomb или неконтролируемое раскрытие |
| Versions and trash | Только после основного scan и отдельного cleanup approval | Source id + version/trash marker + date | Purge необратим или нарушает retention/legal hold |

## Safe Output Preflight

1. Создать synthetic corpus без реальных значений.
2. Запустить выбранный scanner в предполагаемом path-only режиме.
3. Проверить stdout, stderr, reports и debug logs.
4. Убедиться, что нет value, line, snippet, preview, hash или fingerprint.
5. При провале не использовать tool на реальных данных.

## Recovery And Edge Cases

- Scanner показал value, line или snippet на синтетике -> не запускать real-data scan; выбрать другой output mode/tool или завершить blocked status.
- Connector возвращает body/snippet вместе с metadata -> не продолжать через этот connector; использовать provider-native redacted/DLP surface или отметить источник blocked.
- Source недоступен, partial или rate-limited -> сохранить coverage state и завершить `PARTIAL_COVERAGE`, не «всё чисто».
- Symlink, shared link или nested source выходит за разрешённый scope -> не переходить границу; запросить отдельное полномочие.
- Archive encrypted, рекурсивен или превышает согласованные limits -> не распаковывать; пометить exclusion и риск.
- Payment detector видит только короткое число без checksum/context -> не создавать finding; оставить review note без цифр.
- Обнаружены признаки active incident или legal hold -> остановить deletion и передать pointers владельцу response/retention.
- Replacement нельзя подтвердить безопасным каналом -> не удалять старую копию и оставить remediation pending.

## Cleanup Sequence

1. Назначить владельца remediation.
2. Revoke, rotate, invalidate, freeze или reissue.
3. Проверить replacement и недействительность старого доступа безопасным каналом.
4. Сформировать batch из pointers и последствий.
5. Получить явное подтверждение.
6. Удалить или отредактировать только утверждённые копии.
7. Отдельно решить versions, trash, history, shared copies и backups.
8. Повторить scan того же coverage.
