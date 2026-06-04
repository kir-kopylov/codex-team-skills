# Разбор Сбоев Skill

Этот документ описывает лёгкий v1-процесс обучения skill на ошибках. Цель - не саморефлексия агента, а короткий проверяемый путь:

```text
ошибка -> карточка -> reviewer -> правило -> example/test -> human approval -> commit
```

## Приватный Лог

Сырые карточки ошибок хранятся только локально вне repo:

```text
~/.codex/skill-runs/<skill-name>/exception-log.jsonl
```

Писать карточку нужно, если:

- пользователь поправил skill;
- tool, browser, API или connector упал;
- skill нарушил заявленный режим работы;
- пришлось искать workaround;
- skill сделал ложное предположение.

Минимальные поля одной JSONL-записи:

```json
{
  "run_id": "2026-06-03-example",
  "skill_name": "example-skill",
  "trigger": "естественная фраза пользователя",
  "intended_action": "что skill собирался сделать",
  "actual_action": "что реально сделал",
  "failure_point": "где сломалось",
  "false_assumption": "какая предпосылка оказалась ложной",
  "user_correction": "что поправил пользователь или reviewer",
  "next_time_rule": "что сделать сразу в следующий раз",
  "severity": "low|medium|high"
}
```

Если поле неизвестно, используйте `unknown`, а не выдумывайте.

## Known Exceptions

Каждый новый или изменяемый skill должен иметь рядом с `SKILL.md` файл:

```text
known-exceptions.yaml
```

Минимальный пустой файл:

```yaml
exceptions: []
```

Запись известного сбоя:

```yaml
exceptions:
  - symptom: "Что видно пользователю или Codex."
    root_cause: "Почему skill ошибается."
    do_next_time: "Что сделать сразу в следующий раз."
    source_example: "Какой sanitized packet, example или test подтверждает правило."
```

Перед выполнением skill должен читать `known-exceptions.yaml` как список уже известных случаев.

## Reviewer Gate

`skill-exception-reviewer` читает приватные карточки или sanitized packets и предлагает patch proposal. Он не применяет patch сам.

Правило попадает в skill, если сбой повторяется или один раз оказался дорогим, рискованным или нарушающим режим работы. Слабый единичный сбой можно оставить в приватном логе без изменения skill.

В публичный repo можно переносить только:

- очищенную запись в `known-exceptions.yaml`;
- правку `SKILL.md`;
- patch в `references/domain-playbook.md`, если сбой связан с интерфейсной механикой, URL pattern, selector, paid/no-payment path, локальным языковым ключом или повторяемым browser/API recovery;
- synthetic good/anti example;
- regression test idea или тест.

Нельзя переносить raw logs, PII, приватные пути, токены, клиентские переписки, pasteboard paths и скриншоты.

## Сохранять Специфику, А Не Только Абстракцию

Очищение приватных данных не должно уничтожать главное знание, ради которого skill создаётся. Если сбой или workaround связан с конкретным сервисом, рынком или интерфейсом, переносите в repo именно эту механику в очищенном виде.

Примеры знания, которое надо сохранять:

- названия публичных вкладок, кнопок и статусов;
- стабильные URL patterns, selectors, data-testid, лимиты полей и обязательные поля;
- последовательность recovery после ошибок browser/API/connector;
- поведение после сохранения или публикации, например повторная модерация;
- paid upsell и безопасный no-payment path;
- локальные языковые ключи и поисковые формулировки, если они повышают discoverability;
- различение количества записей и фактического покрытия предметов/заказов/кейсов.

Примеры того, что надо заменить синтетикой:

- реальные имена, телефоны, email, адреса и номера объектов;
- реальные IDs объявлений, платежей, заказов и клиентов;
- приватные файлы, медиа, скриншоты и raw transcript.

Правило для reviewer: если proposed patch делает skill более "общим", но теряет интерфейсные детали, которые уже стоили команде времени, patch слабый. Лучше добавить sanitized known exception, selector note, example или anti-example, чем стереть сервисную специфику.

## Domain Playbook V1

`references/domain-playbook.md` добавляется только к domain/interface-heavy skills. Это короткая память о сервисе, а не новая тяжёлая схема.

Минимальные секции:

```markdown
# Domain Playbook

## Что Нельзя Потерять

## Что Надо Обезличить

## Interface Mechanics

## Recovery And Edge Cases
```

Если private failure показывает конкретную механику сервиса, reviewer предлагает playbook patch вместе с `known-exceptions.yaml`. Если сбой общий и не зависит от интерфейса, playbook не нужен.
