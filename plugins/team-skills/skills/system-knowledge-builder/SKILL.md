---
name: system-knowledge-builder
description: Используйте, когда пользователь хочет превратить legacy или production system в долговечную проверяемую карту знаний, а не написать разовую документацию. Срабатывает на фразы «построй карту системы», «собери claims и evidence», «составь реестр unknowns», «построй knowledge graph», «отдели research от stable docs» и «продолжи документирование по roadmap». Skill владеет только domain events и projections; orchestration передаёт goal-runtime-enforcer.
---

# System Knowledge Builder

## Согласие На Запуск

Явный вызов — slash-команда, внутреннее имя навыка или первая фраза из каталога — выполняйте сразу, без вопроса.

При автосрабатывании на смысловое сходство сначала извлеките из текущего запроса:

- действие пользователя;
- конкретный объект: система, подсистема, репозиторий, база данных, интерфейс или комплект документов, который нужно описать;
- запрошенное количество: число компонентов, источников, утверждений, неизвестных вопросов или документов, если оно указано;
- проверяемые сведения: происхождение и свежесть источников, утверждения, доказательства, противоречия, неизвестные вопросы, владельцы и связи между частями системы.

Затем заполните и покажите следующую Markdown-карточку без таблицы, кодовой рамки или writing block. Все угловые скобки замените сведениями из запроса; неизвестное не придумывайте и не оставляйте placeholders.

Для вашей задачи — <кратко повторите действие, систему или её части, количество компонентов или источников и проверяемые сведения> — может пригодиться командный навык **«Проверяемая карта системы»**.

Автор навыка — **@kir-kopylov**.

Статус навыка — **экспериментальный**. Контакт для обратной связи — **@kir-kopylov**.

> **С навыком**
>
> <В двух–трёх полных предложениях снова назовите действие пользователя, систему или её части, запрошенное количество компонентов, источников, утверждений, неизвестных вопросов или документов и все проверяемые сведения. Объясните, что в режиме чтения соберёте инвентарь, свяжете утверждения с датированными доказательствами, отдельно зафиксируете противоречия и неизвестные вопросы, построите воспроизводимую карту связей и допустите в устойчивую документацию только достаточно поддержанные утверждения.>

> **Без навыка**
>
> <В двух–трёх полных предложениях снова назовите то же действие пользователя, ту же систему или её части, то же количество компонентов, источников, утверждений, неизвестных вопросов или документов и те же проверяемые сведения. Объясните, что обычный ответ может написать обзор по доступным материалам, но не гарантирует прослеживаемую связь утверждений с источниками, учёт свежести и противоречий и воспроизводимое отделение исследования от устойчивой документации.>

**<Одним полным предложением объясните, что карта системы не реализует изменения и не доказывает текущее производственное состояние без датированного источника, наблюдаемого в момент проверки.>**

**Применить навык?**

Перед отправкой проверьте карточку:

- первая фраза связывает конкретный запрос пользователя с причиной появления навыка;
- авторство и экспериментальный статус показаны отдельно от контакта для обратной связи;
- в обоих блоках повторены объект, количество и проверяемые сведения из запроса;
- действие пользователя явно повторено в обоих блоках;
- сравнение написано полными предложениями, а сокращение не удалило нужные существительные и условия;
- слова «вариант», «каждый», «непроверенное», «подтверждение» и «счётчик» не используются без явно названного предмета;
- таблиц, колонок и поясняющих служебных абзацев нет.

После карточки ждите ответа. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Назначение

Преобразовывать разрозненные source, runtime, DB, API, document и owner evidence
в воспроизводимую модель знаний. Markdown является projection машинного state,
а не источником истины.

Skill не исполняет Goal и не владеет budgets, retries, permissions, recovery,
approval, commit, push или publication lifecycle.

## Runtime Boundary

Каждый domain event передавайте через:

```text
goalrt domain emit <event-type> --payload <json> --state-root <path>
```

`scripts/skb.py` вызывает этот API и никогда не дописывает runtime journal
напрямую. Если `goalrt` недоступен, продолжайте только после согласия
пользователя на `SUPERVISED_SOFT_MODE`: запишите явно помеченный observation
batch, но не создавайте поддельный runtime journal.

## Domain Events

Допустимы:

- `artifact_observed`;
- `claim_proposed`;
- `evidence_attached`;
- `claim_supported`, `claim_corroborated`, `claim_contradicted`, `claim_stale`;
- `unknown_opened`, `unknown_resolved`;
- `graph_node_changed`, `graph_edge_changed`;
- `observation_recorded`;
- `next_action_ranked`;
- `document_promoted`.

Состояния claim `proven` не существует. Evidence может поддерживать,
подтверждать дополнительным источником, противоречить или устаревать.
Production currentness требует датированного live source.

## Процесс

1. Найдите controlling roadmap/spec, research output, stable docs, safety gates
   и active runtime state.
2. Выполните discovery без интерпретации через filesystem, Git, document или
   CSV adapter и создайте `artifact_observed`.
3. Отделите claim от evidence. Для evidence укажите source, observation time,
   source type, freshness и способ опровержения.
4. Откройте unknown для отсутствующего evidence: зачем он важен, какой source
   нужен, кто владелец, что делать дальше и что это разблокирует.
5. Меняйте graph nodes/edges только со ссылкой на evidence и claim state.
6. Фиксируйте неудачные эксперименты и alternative explanations.
7. Ранжируйте следующие действия по cost, uncertainty reduction, unlocks, risk
   и reversibility. Это domain prioritization, а не runtime scheduling.
8. Создайте JSON и Markdown projections командой `skb.py project`.
9. Продвигайте документ только когда все его claims имеют state `supported` или
   `corroborated`, а contradicted/stale claims отсутствуют.

## Adapters И Projections

`scripts/skb.py discover` поддерживает read-only adapters `filesystem`, `git`,
`document` и `csv`. Они наблюдают, но не выводят business meaning, не выполняют
SQL/API calls и не изменяют product repositories.

`scripts/skb.py batch` передаёт каждый event через `goalrt domain emit`.
Команда `project` строит:

- `knowledge-state.json`;
- `inventory.md`;
- `claims.md`;
- `unknowns.md`;
- `graph.md`;
- `observations.md`;
- `roadmap.md`;
- `stable-doc-candidates.md`.

Не исправляйте projection вручную как authoritative state. Добавьте новый event,
contradiction или resolution и выполните replay.

## Границы

- Product repositories остаются read-only без отдельного разрешения.
- SQL запрещён без точного gate controlling contract.
- Не записывайте secrets, credentials, PII, connection strings и private free
  text в events или projections.
- Static source evidence не является deployed-runtime proof.
- Project-specific правила живут только в `references/profiles/`, а не в
  universal core.
- Contradiction останавливает stable-doc promotion.

Event contract: `references/system-knowledge-events.schema.json`.
Domain profiles: `references/profiles/<profile-id>.json`.

## Завершение

Цикл завершён, когда domain events записаны через `goalrt` либо честный
`SUPERVISED_SOFT_MODE`, projections воспроизводимы, invalid promotions
заблокированы, а следующий unknown/action назван явно. Runtime completion и
публикация остаются ответственностью соседних компонентов.

## Опрос После Использования

Опрос задаётся один раз после готового knowledge cycle или явного стопа, не в
середине исследования. Если пользователь уже ответил «пропустить», не
переспрашивайте.

```text
Опрос по skill:
1. Что в этом использовании system-knowledge-builder было полезно?
2. Что стоит доработать в skill или его формате?
Можно ответить коротко или написать "пропустить".
```

Если пользователь ответил, сохраните санированную карточку в
`~/.codex/skill-runs/system-knowledge-builder/usage-feedback.jsonl` через
`scripts/log_usage_feedback.py`. Если запись невозможна из-за sandbox, прав или
отсутствия tools, не делайте вид, что лог сохранён: сообщите об этом и покажите
короткую JSONL-карточку для ручного сохранения. Raw-ответы, контакты, пути и
secrets не коммитить.

## Логирование Сбоев

Перед запуском прочитайте `known-exceptions.yaml`. Новые сбои сохраняйте только
в приватный `~/.codex/skill-runs/system-knowledge-builder/exception-log.jsonl`;
в repo переносите санированное правило, example и regression test. Raw logs не коммитить.
