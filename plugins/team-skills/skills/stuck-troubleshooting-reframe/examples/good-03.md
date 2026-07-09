# Хороший Пример

## Вход

Браузерная автоматизация не может нажать кнопку отправки формы. DOM содержит кнопку, selector стабилен, screenshot показывает форму, но submit не происходит. Агент уже пробовал click, JS click и scroll. Пользователь просит "пересмотреть предпосылки".

## Ожидаемое Поведение

Агент не делает четвертый click. Он фиксирует:

```text
outcome: появился network request submit или подтверждение отправки
current_state: selector найден, visible=true, submit не происходит
old_layer: user-ui
old_hypothesis: кнопка не получает click
same_state_count: 3
false_positive_signals: DOM element exists, visible screenshot, click command returned
```

Новый gate переводит задачу в `data-contract` или `app-config` слой:

```text
gate: проверить validation/disabled/event layer до нового click
action: read-only inspect computed disabled/aria state, validation errors, submit listeners и network log
action_owner: assistant
expected_observation: найден disabled/validation blocker или подтвержден реальный submit event без network
falsifier: нет validation blocker, event handler вызывается, network request уходит
rollback: read-only inspect, форму не отправлять и данные не менять
stop_condition: при falsifier закрыть validation ветку и перейти к network/auth layer
```

## Нельзя

Нельзя продолжать кликать координатами или менять данные формы, пока не проверен новый gate.
