# Протокол Релиза Workspace Agent

## 1. Release Contract

Перед записью зафиксируйте:

| Поле | Что требуется |
| --- | --- |
| Target | Имя, stable agent id и environment |
| Requested diff | Точное изменение поведения или конфигурации |
| Exclusions | Controls, recipients, schedules и tools, которые нельзя менять |
| Release intent | Draft only, publish, schedule update, docs update или комбинация |
| Permissions | Разрешённые files, connectors, browser и внешние действия |
| Verification | Machine evidence для каждой изменяемой поверхности |
| Documentation | Разрешённые recovery docs |
| Completion | Условие, при котором допустим `DONE` |
| Redaction | Что нельзя переносить в отчёты и docs |

Общее пожелание «улучши агента» не означает автоматического разрешения публиковать, менять schedule, отправлять сообщения или править внешнюю документацию.

## 2. Иерархия Доказательств

Используйте порядок силы:

1. свежая machine-readable live configuration и schedule state;
2. свежий post-write readback draft;
3. tool response со stable version/deployment id;
4. screenshot или явное подтверждение пользователя;
5. recovery documentation и старые release notes;
6. inference или assumption.

Provenance:

- `machine_verified` — свежий read operation;
- `write_acknowledged` — ответ mutation без readback;
- `user_confirmed` — сообщение или screenshot пользователя;
- `document_derived` — разрешённый документ;
- `inferred` — вывод из неполных данных;
- `unverified` — доказательств нет.

Не повышайте `user_confirmed`, `document_derived` или `inferred` до `machine_verified` молча.

## 3. Snapshot

Храните компактную запись в текущей сессии. Во внешний журнал пишите её только с разрешением на конкретный target.

```yaml
release_id: "timestamp_or_release_id"
started_at: "ISO-8601"
agent_id: "AGENT_ID"
pre_draft_revision: "REVISION_OR_HASH"
pre_live_version_id: "VERSION_ID"
latest_published_version_id: "VERSION_ID"
live_schedule_ids: []
requested_diff: "APPROVED_DELTA"
excluded_changes: []
documentation_targets: []
permissions: []
status: "DRAFT"
errors: []
```

Rollback reference должен указывать точную прежнюю версию или содержать полный свежий snapshot. Prose-summary недостаточно.

## 4. Матрица Изменений

| Поверхность | Читать до | Правило изменения | Проверять после |
| --- | --- | --- | --- |
| Instructions | Полный текущий draft | Узкое детерминированное изменение | Draft и live text checks |
| Profile | Name и metadata | Только запрошенные поля | Published profile readback |
| Apps | Configured apps | Сохранить unrelated apps | Live configured app set |
| Tools | Enabled tools | Сохранить unrelated tools | Live tool set |
| Memory | Current policy | Не сбрасывать попутно | Pre/post comparison |
| Files | Current references | Только разрешённые files | Re-list identifiers |
| Schedules | Отдельный live list | Stable ids, no duplicates | Re-list cadence/timezone |
| Recipients | Current destination rules | Только approved list | Live instruction/settings |
| Deployment | Draft и published ids | Один publish на release | Intended live version |
| Docs | Authorized current doc | После live verification | Re-read changed sections |

## 5. Runbook

### Preflight

1. Разберите requested outcome и полномочия.
2. Назовите mutations и external side effects.
3. Подтвердите target и publish intent.
4. Отдельно определите scope schedules и docs.
5. Задайте redactions и completion predicate.

### Snapshot

1. Прочитайте current draft.
2. Прочитайте current live version.
3. Получите latest published deployment metadata.
4. Отдельно перечислите live schedules.
5. Прочитайте только разрешённые recovery docs.
6. Сохраните stable ids и provenance.

### Diff

1. Выразите каждое изменение как `до → после`.
2. Перечислите protected controls.
3. Привяжите каждый diff к post-write check.
4. Подготовьте rollback из точного snapshot.
5. Остановитесь, если diff зависит от недоступного current state.

### Mutate

1. Используйте narrowest mutation.
2. Отправьте одно coherent draft update.
3. Перед retry перечитайте draft.
4. Сравните requested и protected fields.
5. Зафиксируйте summary и undo basis.

### Publish

1. Проверьте explicit authority.
2. Опубликуйте verified draft один раз.
3. Сохраните version id.
4. При ambiguous result читайте deployments до retry.

### Verify

1. Прочитайте live configuration.
2. Сопоставьте version с publish result.
3. Проверьте requested diff.
4. Проверьте protected controls.
5. Отдельно re-list schedules и найдите duplicates.
6. Зафиксируйте discrepancy и остановите completion.

### Document

1. Измените только разрешённые recovery artifacts.
2. Запишите verified version, behavior, schedules, exclusions и rollback.
3. Удалите credentials и лишние personal data.
4. Перечитайте документ.
5. Сравните его с live.

### Close

1. Примените completion gate.
2. Отчитайтесь без завышения certainty.
3. Для incomplete state дайте один следующий шаг.

## 6. Full-Prompt Replacement

Применяйте только когда нет более узкой операции:

1. Получите весь current prompt непосредственно перед изменением.
2. Нормализуйте только line endings, необходимые platform.
3. Задайте exact old/new fragments.
4. Посчитайте occurrence каждого old fragment.
5. Остановитесь при неожиданном количестве совпадений.
6. Выполните deterministic replacement in memory.
7. Проверьте наличие new и отсутствие superseded fragments.
8. Сравните protected sections.
9. Отправьте один replacement.
10. Перечитайте stored prompt.

Никогда не собирайте replacement prompt из screenshot, recovery document, chat summary или remembered version.

## 7. Schedules

- Считайте schedules live resources, а не текстом prompt.
- До изменений сохраните ids, timezone, cadence, enabled state и target version, если доступны.
- Перед create ищите equivalent active schedule.
- Изменение времени, cadence или timezone выполняйте update существующей записи по её stable id: publish draft расписание не переносит.
- Порядок внутри релиза: publish новой версии → update schedule → re-list. Обратный порядок оставляет окно, в котором запуск срабатывает на старой версии.
- Если publish не состоялся, schedule не трогайте: иначе живое расписание уйдёт вперёд относительно live-версии.
- После publish проверяйте, на какой agent/version указывает schedule.
- Не удаляйте и не disable schedule без явного разрешения.
- Если instructions и live schedule противоречат друг другу, остановите publish до разрешения конфликта.

## 8. Apps И Connectors

- Проверяйте configured apps без раскрытия OAuth link ids, tokens, cookies и secrets.
- Configured app не доказывает успешность будущего runtime action.
- Используйте read-only connector check, если он доступен и разрешён.
- При auth failure просите reconnection и прекращайте repeated side effects.
- Не заменяйте failed connector браузером без отдельного разрешения.
- Не отправляйте test messages без явного scope и destination.

## 9. Browser Fallback Gate

Browser допустим, только если одновременно:

1. purpose-built API/connector не выполняет операцию;
2. пользователь отдельно разрешил browser для этой задачи;
3. session авторизована штатным способом;
4. действие не обходит access control;
5. UI позволяет verify result;
6. pre-action state однозначно указывает target.

После UI mutation refresh/reopen view и проверьте saved state. Если надёжный readback невозможен, используйте incomplete status.

## 10. Status Matrix

| Статус | Значение | Следующее действие |
| --- | --- | --- |
| `BLOCKED_PRECHECK` | Нет current state или authority | Восстановить доступ или scope, затем restart discovery |
| `DRAFT_CHANGED` | Draft изменён, publish не начат | Verify draft, publish или rollback |
| `PUBLISH_FAILED` | Draft есть, publish не подтверждён | Read deployments, safe retry или rollback |
| `PUBLISHED_UNVERIFIED` | Publish acknowledged, live не подтверждён | Читать live; не republish blindly |
| `VERIFIED` | Live совпадает с approved diff | Обновить required docs |
| `DOCUMENTATION_PENDING` | Live проверен, docs не готовы | Восстановить doc access и sync |
| `ROLLED_BACK` | Активирована прежняя версия, live, schedules и docs проверены | Действий не требуется |
| `DONE` | Release, verification, docs и rollback evidence готовы | Действий не требуется |

При unknown write outcome сначала читайте affected resource. Не повторяйте write первым действием.

## 11. Completion Gate

- [ ] Target identity machine-verified.
- [ ] Полномочия покрывают каждый side effect.
- [ ] Сохранён exact snapshot или prior version.
- [ ] Requested diff применён и read back.
- [ ] Protected controls не изменились.
- [ ] Publish resolved to stable version id.
- [ ] Live совпал с intended release.
- [ ] Schedules проверены отдельно.
- [ ] Apps проверены без раскрытия secrets.
- [ ] Required docs обновлены и перечитаны.
- [ ] Rollback basis применим.
- [ ] Remaining uncertainty указана явно.

Если обязательный пункт не выполнен, статус не может быть `DONE`.

## 12. Runbook Отката

Откат — отдельная исполнимая ветка релиза, а не побочный эффект сохранённого snapshot. Запускайте её, когда запрошен возврат к прежнему рабочему поведению.

### Rollback Preflight

1. Зафиксируйте точку возврата: какое поведение должно вернуться и когда оно было подтверждено.
2. Отделите откат от исправления вперёд: если пользователь хочет новое поведение, это обычный release, а не rollback.
3. Проверьте отдельное разрешение на активацию прежней версии — это внешнее изменяющее действие уровня publish.
4. Назовите, что после отката считается доказательством: version id, поведение, schedules, docs.

### Rollback Select

1. Прочитайте список deployments со stable version ids и временем публикации.
2. Выберите ближайшую предыдущую версию, подтверждённую как рабочая; при сомнении покажите кандидатов пользователю и не выбирайте молча.
3. Запрещено выбирать версию по названию, дате, release notes, screenshot или памяти без stable id.
4. Прочитайте конфигурацию выбранной версии и сравните её с текущим live: зафиксируйте, что именно вернётся и что будет потеряно.
5. Если список версий или их содержимое не читается, остановитесь в `BLOCKED_PRECHECK` и не активируйте ничего.

### Rollback Activate

1. Сохраните текущий live version id: он станет точкой возврата для обратного движения.
2. Активируйте выбранную версию штатной операцией платформы (restore, redeploy или publish сохранённой версии) ровно один раз.
3. Сохраните version id, который вернула операция.
4. При timeout или неоднозначном ответе перечитайте deployments; повторная активация вслепую запрещена.

### Rollback Verify

1. Прочитайте live: version id совпадает с выбранным.
2. Проверьте, что вернулось именно прежнее поведение, а protected controls не пострадали.
3. Отдельно re-list schedules: активация прежней версии не возвращает расписание автоматически. Если расписание расходится с восстановленной версией, приведите его в соответствие по stable id.
4. Проверьте apps и tools: откат мог вернуть прежний набор интеграций.
5. При недоступном readback используйте `PUBLISHED_UNVERIFIED` и не повторяйте активацию.

### Rollback Close

1. Обновите разрешённые recovery docs: какая версия live теперь, какая отменена, по какой причине и какое время проверки.
2. В отчёте назовите отменённую версию и путь обратно, если откат окажется ошибкой.
3. Статус `ROLLED_BACK` допустим, только когда live, schedules и обязательные docs проверены после активации.
