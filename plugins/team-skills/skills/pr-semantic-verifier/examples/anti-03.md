# Публикационный Lifecycle

## Вход

Пользователь просит создать ветку, закоммитить готовое изменение, запушить его, открыть PR, обработать review и после merge удалить ветки.

## Ожидаемое Поведение

```yaml
decision:
  run_verifier: false
  route_to: git-pr-lifecycle-safeguard
  secondary_route: add-team-skill
  mutation_allowed: false
```

Не запускать `pr-semantic-verifier` как управляющий workflow. Передать проверенный scope в `git-pr-lifecycle-safeguard`; для создания или изменения team skill использовать `add-team-skill`.

## Нельзя

Нельзя считать read-only semantic verification разрешением на commit, push, комментарии, merge, release или cleanup.
