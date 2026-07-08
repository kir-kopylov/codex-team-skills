# Хороший Пример

## Вход

CI падает на одном интеграционном тесте. Агент уже три раза менял timeout и retry, потому что логи показывали "service started" и порт был открыт. Пользователь говорит: "это всё мимо, тест всё равно красный".

## Ожидаемое Поведение

Агент закрывает timeout ветку:

```text
old_layer: test-harness
old_hypothesis: сервис не успевает стартовать
false_positive_signals: service started, port open
same_state_count: 2
why_closed: timeout/retry не изменили failing assertion
```

В `external_case_matrix` он принимает только кейсы с локальным observable. Например: health endpoint зеленеет раньше миграций. Новый gate:

```text
new_layer: data-contract
gate: проверить, завершились ли migrations/seed до первого failing request
action: собрать timestamps миграций и failing request
action_owner: assistant
expected_observation: миграция/seed позже первого запроса или подтверждение обратного
falsifier: миграции завершены до запроса, schema/seed совпадают, assertion всё равно падает
rollback: read-only сбор логов, состояние CI не менять
stop_condition: если falsifier сработал, не увеличивать timeout; перейти к payload/API contract
```

## Нельзя

Нельзя увеличивать timeout ещё раз без нового факта, который показывает, что проблема действительно во времени ожидания.
