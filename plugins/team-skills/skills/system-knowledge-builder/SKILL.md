---
name: system-knowledge-builder
description: Используйте, когда пользователь хочет превратить legacy или production system в долговечную проверяемую карту знаний, а не написать разовую документацию. Срабатывает на фразы «построй карту системы», «собери claims и evidence», «составь реестр unknowns», «построй knowledge graph», «отдели research от stable docs» и «продолжи документирование по roadmap». Skill владеет только domain events и projections; orchestration передаёт goal-runtime-enforcer.
---

# System Knowledge Builder

## Запуск Навыка

При явном вызове или однозначном смысловом совпадении применяйте навык сразу. Перед первым шагом покажите ровно одну короткую контекстную строку (не более 30 слов) и продолжайте работу в том же ответе, не ожидая реакции:

Применяю экспериментальный навык **«Проверяемая карта системы»** (обратная связь — @kir-kopylov): <кратко назовите конкретную пользу для текущего запроса>; продолжаю без ожидания.

Не включайте в строку `author_github`, внутреннее имя папки или пересказ всего запроса. Не спрашивайте, применять ли навык.

Не завершайте первый ответ уведомлением, планом или обещанием будущей разведки. Сразу после строки запуска самостоятельно определите границу системы из запроса, доступного контекста и read-only источников, затем сами найдите и прочитайте доступные файлы, Git, документы, CSV, журналы или подключённые источники. В том же ответе верните первые `claims`, связанное с ними `evidence`, `unknowns` и начальные связи `graph`, отделяя наблюдаемые факты от выводов. Если границу системы нельзя однозначно определить из запроса, контекста или инструментов, задайте один ближайший вопрос, ответ на который меняет target; не просите пользователя выполнять техническую проверку, доступную агенту.

Первичный read-only проход и его краткая выдача не являются записью domain events и не ждут `goalrt` или `SUPERVISED_SOFT_MODE`; gate ниже действует перед сохранением событий.

Если одновременно подходят совместимые навыки, выберите минимальный набор и покажите одну общую строку. Если подходы ведут к несовместимым результатам и запрос не позволяет выбрать, спросите только о желаемом результате, не о разрешении применить навык.

Запуск навыка не расширяет полномочия. Выполните всю безопасную и уже разрешённую часть; запросите подтверждение только непосредственно перед ещё не разрешённым внешним или изменяющим действием. Не запрашивайте повторно уже данное разрешение и не дублируйте системное окно подтверждения.

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
