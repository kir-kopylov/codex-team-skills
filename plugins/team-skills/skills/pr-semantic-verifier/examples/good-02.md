# Устаревший Test Oracle

## Вход

Авторитетная спецификация явно разрешила новую формулировку сообщения, сохранив прежнее поведение. Behavior-level probe на точном head проходит, но старый exact-string assertion всё ещё требует прежнюю фразу и делает CI красным.

## Ожидаемое Поведение

```yaml
decision:
  run_verifier: true
  semantic_verdict: PROVED
  finding_types:
    - test-contract-defect
    - contract-changed
    - stale-fixture
  highest_proven_layer: local-test
  mutation_allowed: false
```

Skill ставит источник требования выше старого assertion, проверяет оба oracle-вопроса и отделяет результат продукта от состояния test suite.

Итог:

- прямой behavior probe может дать `PROVED` на заявленной поверхности;
- `finding_types` включают `test-contract-defect`, `contract-changed` и `stale-fixture`;
- тест предлагается обновить только вместе с явным объяснением сохранённого инварианта;
- если пользователь попросил исправить CI, узкий scope передаётся в `gh-fix-ci` после semantic verdict.

## Нельзя

Нельзя исправлять ситуацию удалением behavior assertion, заменой его на проверку наличия файла или broad skip. Нельзя объявлять реализацию дефектной только потому, что устаревший test oracle красный.
