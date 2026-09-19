# Repo Исправлен, Внешний Runtime Не Наблюдался

## Вход

Изменения находятся на точном head, focused tests и CI зелёные, review завершён, PR merged. На компьютере коллеги не подтверждены версия plugin, установка, discovery или фактический запуск.

## Ожидаемое Поведение

```yaml
decision:
  run_verifier: true
  semantic_verdict: PARTIAL
  finding_types:
    - evidence-scope-gap
  highest_proven_layer: merge
  unverified_layers:
    - installation
    - runtime
    - user-outcome
  mutation_allowed: false
```

Skill строит лестницу доказательств и не переносит merge на внешний runtime.

Итог:

- `semantic_verdict`: `PARTIAL` для обещания, включающего внешний пользовательский результат;
- `finding_types`: `evidence-scope-gap`;
- repository, test, CI, review и merge отмечаются доказанными;
- `installation`, `runtime` и `user-outcome` остаются `UNVERIFIED`;
- следующий владелец — человек или workflow, способный получить свежее наблюдение на целевом компьютере.

## Нельзя

Нельзя говорить «теперь у коллеги работает» по состоянию GitHub, merge или локальной установке автора. Нельзя подменять свежую проверку внешней машины старым логом.
