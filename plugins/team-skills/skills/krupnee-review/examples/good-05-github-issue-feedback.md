# Хороший Пример: Обратная Связь Через Технический Канал

## Вход

Ответственный за skill передаёт тело задачи из технического канала. Внутри есть `krupnee_review_packet`, `feedback_channel: github_issue`, `skill_name: krupnee-runtime`, `actual_behavior`, `expected_behavior` и `suspected_issue`.

## Ожидаемое Поведение

Codex использует `krupnee-review` как ручной offline-evaluator: принимает технический канал как равноценный способ доставки обратной связи, выдаёт verdict, предлагает eval case, patch proposal и отмечает, нужен ли changelog.

## Нельзя

Нельзя описывать технический канал как второстепенный запасной путь. Нельзя автоматически менять runtime без подтверждения maintainer.
