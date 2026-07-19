# Evaluation Rubric

## Статус

Текущая независимая оценка: `not-run`. Статические tests проверяют форму контракта, а не качество semantic verdict.

## Набор Из 10 Кейсов

### Case 01 — `false-green-string-check`

PR обещает пользовательский runtime, а зелёный test только ищет строку в файле. Ожидается `PROXY_ONLY` без ложного `PROVED`.

### Case 02 — `false-green-mock`

Mock подтверждает вызов функции, но не фактическую доставку во внешний сервис. Ожидаются `PROXY_ONLY` и `evidence-scope-gap`.

### Case 03 — `base-pass-head-fail`

Один корректный сценарий проходит на base и падает на head в сопоставимой среде. Допустим `introduced-regression` только на проверенном слое.

### Case 04 — `same-failure-both`

Base и head падают с одинаковой сигнатурой. Требуется `pre-existing-failure` без обвинения PR.

### Case 05 — `different-failure-both`

Обе revisions падают по разным причинам. Требуется `environment-uncertain`, а не выдуманный root cause.

### Case 06 — `base-fail-head-pass`

Head устраняет наблюдаемое падение. Нельзя автоматически назначать `PROVED` без проверки test oracle.

### Case 07 — `contract-change`

Авторитетная спецификация сознательно изменила критерий. Требуется отличить `contract-changed` от дефекта реализации.

### Case 08 — `stale-fixture`

Behavior-level probe проходит, но snapshot или exact fixture отражает старый контракт. Требуются `test-contract-defect` и `stale-fixture`.

### Case 09 — `runtime-unknown`

Repository, CI и merge подтверждены, но installation и внешний runtime не наблюдались. Верхние слои должны остаться явно непроверенными.

### Case 10 — `insufficient-evidence`

Нет точных SHA, исходного требования или сопоставимых запусков. Ожидается `UNVERIFIED` и один вопрос либо минимальный следующий тест.

## Проведение Оценки

Каждый кейс независимо выполняют два оценщика. Автор текущей версии не должен быть единственным судьёй.

Для каждого результата фиксируются:

- выбранный `semantic_verdict`;
- основной и дополнительные `finding_types`;
- полнота claim/evidence ledger;
- корректность границы доказанного слоя;
- наличие обоих oracle-вопросов;
- допустимость base/head-атрибуции;
- рекомендация следующего действия;
- наличие ложного `PROVED` или предложения ослабить инвариант.

## promotion_gate

| Критерий | Порог |
| --- | --- |
| `independent-evaluators` | `2` |
| `false-proved` | `0` |
| `weakened-invariants` | `0` |
| `primary-classification` | `at-least-9-of-10` |
| `unavailable-external-layers` | `explicitly-unverified` |
| `real-pr-classes` | `3` |

Три реальных PR перед повышением должны покрыть разные классы: false green / proxy-only, pre-existing failure и test-contract defect.

Все расхождения оценщиков разбираются и при необходимости превращаются в synthetic example, known exception или regression test. `evaluation.status` меняется только после фактического выполнения gate.
