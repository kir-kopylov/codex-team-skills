---
name: skill-exception-reviewer
description: Используйте этот skill, когда нужно разобрать приватные карточки сбоев, очищенные exception logs или карточки пользовательского фидбека (usage-feedback.jsonl из опроса после использования) существующего Codex skill и предложить безопасный patch proposal к SKILL.md, known-exceptions.yaml, examples и tests. Skill срабатывает на фразы вроде "разбери exception log skill", "сделай reviewer по сбоям skill", "преврати карточки ошибок в patch proposal", "что добавить в known-exceptions", "разбери, почему skill повторяет ошибку", "разбери фидбек по skill". Reviewer только предлагает изменения и не применяет patch без отдельного явного запроса.
---

# Skill Exception Reviewer

## Согласие На Запуск

Явный вызов — slash-команда, имя skill или первая фраза из каталога — выполняйте сразу, без вопроса. При автосрабатывании на смысловое сходство сначала спросите одной строкой: «Задача похожа на team skill `skill-exception-reviewer` — превращает карточки сбоев skill в безопасный patch proposal. Применить или решить без него?» — и ждите ответа. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

Этот skill превращает сбои skill-а и пользовательский фидбек в проверяемые предложения по улучшению. Он не занимается саморефлексией исполнителя и не переписывает skill автоматически. Его задача - прочитать приватные карточки ошибок и карточки опроса после использования, отделить повторяемые или дорогие сигналы от случайного шума и предложить точечный patch proposal.

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
   - локальный `usage-feedback.jsonl` — карточки опроса после использования (`liked` / `improve` / `outcome`);
   - вставленные пользователем очищенные карточки ошибок или фидбека;
   - краткий фрагмент диалога, если raw log недоступен.
2. Проверьте privacy boundary:
   - не переносите raw private logs, PII, приватные пути, токены, клиентские переписки или скриншоты в repo;
   - если вход содержит приватные детали, сначала предложите sanitized summary.
3. Сгруппируйте сигналы:
   - повторяющийся сбой;
   - один дорогой или рискованный сбой;
   - единичный слабый сбой, который пока не должен становиться правилом;
   - пожелание из опроса: повторяющееся или явно дешёвое в реализации идёт в proposal как правка `SKILL.md` или example (без записи в `known-exceptions.yaml` — она только для сбоев), единичное вкусовое остаётся в приватном логе.
4. Для каждого кандидата сформулируйте:
   - наблюдаемый симптом;
   - root cause;
   - что делать в следующий раз сразу;
   - какой пример или regression test нужен.
5. Выдайте patch proposal, но не применяйте его:
   - запись для `known-exceptions.yaml`;
   - короткую правку к `SKILL.md`;
   - patch в `references/domain-playbook.md`, если сбой связан с интерфейсной механикой, selector, URL pattern, paid/no-payment path, локальным языковым ключом или повторяемым browser/API recovery;
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

## Опрос После Использования

Опрос задаётся один раз — после выдачи patch proposal, не посреди рабочего цикла. Если пользователь уже ответил «пропустить» в этой сессии, не переспрашивайте.

```text
Опрос по skill:
1. Что в этом использовании skill-exception-reviewer было полезно?
2. Что стоит доработать в skill или его формате?
Можно ответить коротко или написать "пропустить".
```

Если пользователь ответил, сохраните санированную карточку в `~/.codex/skill-runs/skill-exception-reviewer/usage-feedback.jsonl` — лучше через bundled script:

```bash
python3 scripts/log_usage_feedback.py --liked "..." --improve "..." --outcome "..."
```

Script перед записью редактирует приватные пути, контакты и token-like строки и сохраняет `redaction_applied` и `redaction_types`. Если запись невозможна из-за sandbox, прав или отсутствия tools, не делайте вид, что лог сохранён: скажите об этом и покажите короткую JSONL-карточку для ручного сохранения. Raw-ответы, контакты, пути и секреты не коммитить.

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

## Формат Usage Feedback Card

Карточки опроса после использования лежат рядом:

```text
~/.codex/skill-runs/<skill-name>/usage-feedback.jsonl
```

Поля записи: `ts`, `skill`, `liked`, `improve`, `outcome`, `context`, `redaction_applied`, `redaction_types`, `source`. Для reviewer главные поля — `improve` (кандидаты в правки) и `liked` (что нельзя сломать при правке).

## Patch Proposal

Ответ reviewer-а должен быть структурирован так:

```markdown
## Сводка Сбоев

## Кандидаты В Правила

## Patch Proposal

### known-exceptions.yaml

### SKILL.md

### references/domain-playbook.md

### examples/

### tests/

## Gate
```

В `Gate` всегда укажите: human approval, `python3 -m pytest`, commit с объяснением, какое исключение стало правилом.

## Definition Of Done

Review завершён, если:

- raw log не перенесён в repo;
- повторяющиеся или дорогие сигналы отделены от слабых единичных;
- patch proposal содержит для сбоев запись в `known-exceptions.yaml`, для пожеланий из опроса — правку инструкции или example, плюс playbook patch для интерфейсного сбоя и идею example/test;
- явно сказано, что patch не применён;
- следующий похожий сбой можно будет распознать без нового поиска решения.
