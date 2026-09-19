# CandidatePacket v1

## Назначение

Пакет фиксирует одно внешнее сообщение о практике. Он не является экспериментом, рекомендацией к изменению среды или доказательством локальной работоспособности.

Подробная структура отражена в валидаторе `scripts/validate_candidate_packet.py`. Не дублировать схему в нескольких изменяемых файлах: при расхождении источником правды считается исполняемый validator и его tests.

## Корневые Поля

```yaml
schema_version: 1
run_id:
candidate_id:
input_fingerprint:
status:
candidate_type:
reported_problem:
reported_intervention:
  components: []
  attribution_note:
reported_result:
local_status: NOT_TESTED
evidence_records: []
evidence_basis:
  independent_origin_count:
  corroboration:
  causal_support:
applicability:
  matches: []
  differences: []
  unknowns: []
  acceptance_evidence_not_addressed: []
review:
  researcher_id:
  reviewer_class:
  reviewer_id:
  reviewed_at:
  original_opened:
  disagreements: []
  resolution:
run_metrics:
  queries:
  sources_discovered:
  sources_opened:
  sources_readable:
  sources_rejected:
  duplicate_origins:
  retries:
  active_seconds:
  human_review_minutes:
  observable_cost:
    amount:
    currency:
  failure_codes: []
  discovery_records: []
  query_records: []
  source_attempts: []
resume:
  queued_leads: []
  exhausted_queries: []
  remaining_budget:
    active_minutes:
    queries:
    opened_sources:
  next_action:
```

## Идентификаторы

`candidate_id` — полный SHA-256 нормализованной тройки:

- `reported_problem`;
- список `reported_intervention.components`;
- `reported_result`.

Префикс: `cph-v1-`.

Нормализация выполняет Unicode NFKC, `casefold` и схлопывание пробелов. Это синтаксическая идемпотентность, а не semantic dedup: перефразирование может создать другой ID.

`input_fingerprint` имеет префикс `ifp-v1-`. При переданном `--input-contract` validator пересчитывает его из canonical YAML/JSON. Без input-contract проверяется только формат и выдаётся warning.

`canonical_origin_id` пересчитывается из `canonical_origin_url`. Копия, перевод и пересказ исходного материала обязаны иметь тот же origin ID.

## Тип Кандидата

- `atomic_mechanism`: ровно один компонент; `causal_support` равен `single_change_reported` или `controlled_isolation`.
- `reported_intervention_bundle`: два и более компонентов; `causal_support` равен `bundle_only`.

Validator проверяет только внутреннюю согласованность этих полей. Он не способен доказать, что автор источника действительно изолировал причинность.

## Evidence Record

Каждая запись содержит:

```yaml
origin_url:
canonical_origin_url:
canonical_origin_id:
relation: original | copy | translation | commentary
accessed_at:
published_at:
language:
accessibility: full_text | partial_text | snippet_only | unavailable | paywalled | auth_required
locator:
short_excerpt:
extract_sha256:
translation:
  text:
  method:
  reviewer_id:
reported_context:
reported_change:
reported_result:
```

Для `full_text` и `partial_text` обязательны locator, выдержка и SHA-256 точного UTF-8 текста выдержки. Хэш доказывает только неизменность сохранённой выдержки, но не её связь с веб-страницей.

Независимыми считаются только уникальные `canonical_origin_id` записей `relation=original` и `accessibility=full_text`.

## Promotion Rules

`REVIEWED_EXTERNAL_PRACTICE_CANDIDATE` допустим только когда:

- открыт хотя бы один полный оригинал;
- reviewer работает в свежем контексте;
- reviewer ID отличается от researcher ID;
- `review.resolution=agree`;
- разногласий нет;
- все обязательные поля evidence заполнены;
- `local_status=NOT_TESTED`.

Недоступный оригинал, snippet-only, same-context self-review и unresolved disagreement запрещают promotion.

## Честный Нулевой Результат

`NO_USABLE_PRACTICE_FOUND` — тоже полный `CandidatePacket v1`, но без кандидата:

```yaml
status: NO_USABLE_PRACTICE_FOUND
candidate_id: null
candidate_type: null
reported_problem: null
reported_intervention: null
reported_result: null
local_status: NOT_TESTED
evidence_records: []
evidence_basis:
  independent_origin_count: 0
  corroboration: none
  causal_support: not_applicable
applicability:
  matches: []
  differences: []
  unknowns: []
  acceptance_evidence_not_addressed: []
```

Неудачные открытия остаются в `run_metrics.source_attempts`, а перспективные, но непрочитанные ссылки — в `resume.queued_leads`. Статус требует `BUDGET_EXHAUSTED` и нулевой остаток хотя бы одного применимого лимита; преждевременную остановку этим статусом маскировать нельзя.

## Метрики

`source_attempts` — audit trail:

```yaml
- url:
  attempts:
  final_accessibility:
  disposition: evidence | duplicate | rejected
  failure_code:
```

Из него validator пересчитывает `sources_opened`, `sources_readable`, `sources_rejected`, `duplicate_origins` и `retries`. Это не доказывает реальное выполнение запросов, но устраняет арифметически несовместимые self-reports.

`sources_opened` считает уникальные канонизированные fetch-URL. Повтор того же URL увеличивает `retries`; альтернативный хост считается отдельным открытием, даже если reviewer позже отнесёт его к тому же первоисточнику.

Для URL, попавшего в `evidence_records`, `accessibility` обязана точно совпадать с `source_attempts.final_accessibility`; нельзя повысить `partial_text` в журнале до `full_text` в evidence.

`query_records` делает счётчик запросов и обнаруженных URL пересчитываемым:

```yaml
- query_id:
  query:
  language:
  rationale:
  executed_at:
  result_urls: []
```

`queries` равен числу записей. `result_urls` хранит только отобранные из выдачи ссылки, а не все показанные поисковиком результаты. `resume.exhausted_queries` содержит те же выполненные строки запросов.

`discovery_records` фиксирует происхождение каждой отобранной ссылки:

```yaml
- url:
  method: search_result | user_provided_lead | source_followup | resume_lead
  reference:
```

Для `search_result` reference равен `query_id`; для `user_provided_lead` URL обязан присутствовать в `input_contract.provided_leads`; для `source_followup` reference — URL родительского материала; для `resume_lead` URL и prior run обязаны совпасть с `input_contract.resume_envelope`. `sources_discovered` равен числу уникальных discovery records. Каждая такая ссылка должна быть либо открыта, либо сохранена в очереди. Это подтверждает внутреннюю арифметику происхождения, а не факт реального обращения к поиску.

Граф `source_followup` обязан быть ациклическим и заканчиваться корнем `search_result`, `user_provided_lead` или `resume_lead`. Родитель followup должен быть реально прочитан. Без переданного input-contract метод `user_provided_lead` невалиден: validator не может проверить происхождение ссылки.

При переданном input-contract validator также сверяет использованные и оставшиеся лимиты запросов, открытых URL, времени и попыток на URL. Если `active_seconds=unknown`, остаток времени обязан быть `unknown`, а eval соблюдения бюджета остаётся непроверяемым.

## Handoff

Пакет не разрешает эксперимент. Downstream-процесс обязан:

1. сослаться на `candidate_id`, `input_fingerprint` и hash пакета;
2. создать отдельный experiment ID;
3. заново проверить текущее состояние и полномочия;
4. сохранить новый evidence artifact;
5. не изменять внешний статус карточки задним числом.
