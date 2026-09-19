# Публикационный Lifecycle

## Вход

Пользователь просит создать ветку, закоммитить готовое изменение, запушить его, открыть PR, обработать review и после merge удалить ветки.

## Ожидаемое Поведение

```yaml
decision:
  run_verifier: false
  route_to: provedenie-vetki-do-uborki
  secondary_route: dobavlenie-navyka-v-biblioteku
  mutation_allowed: false
```

Не запускать `pr-semantic-verifier` как управляющий workflow. Передать проверенный scope в `provedenie-vetki-do-uborki`; для создания или изменения team skill использовать `dobavlenie-navyka-v-biblioteku`.

## Нельзя

Нельзя считать read-only semantic verification разрешением на commit, push, комментарии, merge, release или cleanup.
