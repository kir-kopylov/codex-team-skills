---
name: skill-exception-reviewer
description: Используйте этот skill, когда нужно разобрать приватные карточки сбоев или очищенные exception logs существующего Codex skill и предложить безопасный patch proposal к SKILL.md, known-exceptions.yaml, examples и tests. Skill срабатывает на фразы вроде "разбери exception log skill", "сделай reviewer по сбоям skill", "преврати карточки ошибок в patch proposal", "что добавить в known-exceptions", "разбери, почему skill повторяет ошибку". Reviewer только предлагает изменения и не применяет patch без отдельного явного запроса.
---

# Skill Exception Reviewer

## Обзор

Этот skill превращает сбои skill-а в проверяемые предложения по улучшению. Он не занимается саморефлексией исполнителя и не переписывает skill автоматически. Его задача - прочитать приватные карточки ошибок, отделить повторяемые или дорогие сбои от случайного шума и предложить точечный patch proposal.

Базовый цикл:

```text
exception card -> grouped failure -> known exception -> example/test idea -> human approval -> git commit
```

## Естественные Входы

Запускайте skill по обычным формулировкам:

- "разбери exception log skill";
- "сделай reviewer по сбоям skill";
- "преврати эти карточки ошибок в patch proposal";
- "что добавить в known-exceptions";
- "skill снова повторил ошибку, разбери лог";
- "какое правило нужно добавить в SKILL.md после этого сбоя".

## Процесс

1. Определите источник:
   - локальный `exception-log.jsonl`;
   - вставленные пользователем очищенные карточки ошибок;
   - краткий фрагмент диалога, если raw log недоступен.
2. Проверьте privacy boundary:
   - не переносите raw private logs, PII, приватные пути, токены, клиентские переписки или скриншоты в repo;
   - если вход содержит приватные детали, сначала предложите sanitized summary.
3. Сгруппируйте сбои:
   - повторяющийся сбой;
   - один дорогой или рискованный сбой;
   - единичный слабый сбой, который пока не должен становиться правилом.
4. Для каждого кандидата сформулируйте:
   - наблюдаемый симптом;
   - root cause;
   - что делать в следующий раз сразу;
   - какой пример или regression test нужен.
5. Выдайте patch proposal, но не применяйте его:
   - запись для `known-exceptions.yaml`;
   - короткую правку к `SKILL.md`;
   - good/anti example;
   - regression test idea;
   - human approval question.

## Границы

Используйте этот skill только для улучшения существующих skills по следам реальных сбоев. Если пользователь просит создать новый skill из общего диалога, используйте skill mining workflow вместо exception review.

Нельзя:

- применять patch без отдельного явного запроса пользователя;
- коммитить raw exception logs;
- превращать единичный слабый сбой в обязательное правило;
- переносить приватный контекст в публичные examples;
- ослаблять privacy tests или обходить gate ради быстрого merge.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/<skill-name>/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.

## Формат Exception Card

Приватный лог хранится вне repo, обычно:

```text
~/.codex/skill-runs/<skill-name>/exception-log.jsonl
```

Минимальные поля записи:

```text
run_id
skill_name
trigger
intended_action
actual_action
failure_point
false_assumption
user_correction
next_time_rule
severity
```

Если поле неизвестно, оставьте `unknown`, а не выдумывайте.

## Patch Proposal

Ответ reviewer-а должен быть структурирован так:

```markdown
## Сводка Сбоев

## Кандидаты В Правила

## Patch Proposal

### known-exceptions.yaml

### SKILL.md

### examples/

### tests/

## Gate
```

В `Gate` всегда укажите: human approval, `python3 -m pytest`, commit с объяснением, какое исключение стало правилом.

## Definition Of Done

Review завершён, если:

- raw log не перенесён в repo;
- повторяющиеся или дорогие сбои отделены от слабых единичных;
- patch proposal содержит запись для `known-exceptions.yaml`, правку инструкции и идею example/test;
- явно сказано, что patch не применён;
- следующий похожий сбой можно будет распознать без нового поиска решения.
