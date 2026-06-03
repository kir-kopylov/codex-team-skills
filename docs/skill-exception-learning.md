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
- synthetic good/anti example;
- regression test idea или тест.

Нельзя переносить raw logs, PII, приватные пути, токены, клиентские переписки, pasteboard paths и скриншоты.
