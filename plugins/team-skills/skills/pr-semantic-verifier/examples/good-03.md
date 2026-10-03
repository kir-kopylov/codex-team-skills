# Одинаковое Падение На Base И Head

## Вход

Один и тот же focused test запущен в двух независимых временных копиях. На base и head он падает в одной фазе с одинаковой первичной ошибкой; test, fixture, lockfile и среда сопоставимы.

## Ожидаемое Поведение

```yaml
decision:
  run_verifier: true
  semantic_verdict: UNVERIFIED
  finding_types:
    - pre-existing-failure
  highest_proven_layer: local-test
  unverified_layers:
    - claim-outcome
  mutation_allowed: false
```

Skill записывает оба OID, сценарий, сигнатуру падения и предел вывода.

Итог:

- `finding_types`: `pre-existing-failure`;
- `introduced-regression` не назначается;
- общий verdict по обещанию PR остаётся `UNVERIFIED`, если других прямых доказательств нет;
- блокирующий старый сбой можно передать в `gh-fix-ci`, не приписывая его текущему PR.

## Нельзя

Нельзя называть PR причиной только потому, что check красный на head. Нельзя считать два ненулевых exit code одинаковой причиной без сравнения фазы и первичной ошибки.
