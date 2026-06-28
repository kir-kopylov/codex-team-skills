# Хороший Пример: Feedback Row Из Sheet

## Вход

Maintainer пишет: "У тебя новые feedback rows по krupnee-runtime. Разобрать?" и передаёт sanitized row из `Team Codex Skill Feedback Inbox` с `trace_source: dissatisfaction_feedback`, `skill_name: krupnee-runtime`, `dissatisfaction_signal: "это мешает"`, `actual_behavior`, `expected_behavior` и `review_packet`.

## Ожидаемое Поведение

Codex использует `krupnee-review` как offline/manual evaluator: принимает row как явно переданный материал, выдаёт verdict, предлагает eval case, patch proposal и отмечает, нужен ли changelog. Если rows несколько, он группирует похожие жалобы перед предложением patch.

## Нельзя

Нельзя утверждать, что Codex сам прочитал Sheet или имеет доступ к чужим эпизодам. Нельзя автоматически менять runtime без подтверждения maintainer.
