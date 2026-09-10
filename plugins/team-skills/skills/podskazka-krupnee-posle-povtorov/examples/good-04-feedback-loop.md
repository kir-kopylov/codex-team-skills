# Хороший Пример: Недовольство Вмешательством

## Вход

После `offer_lift` пользователь пишет: "Зачем ты это предложил? Это мешает, просто сделай."

## Ожидаемое Поведение

Codex признаёт, что вмешательство могло быть неудачным, возвращается к лёгкому выполнению просьбы и предлагает отправить автору skill короткий feedback. Он сам формирует `krupnee_review_packet` с `trace_source: dissatisfaction_feedback`, `review_trigger: user_dissatisfaction`, `suspected_issue: false_positive` или `overlong_runtime`.

Если `Team Codex Skill Feedback Inbox` или `GitHub Issue` channel и соответствующий connector подключены, Codex отправляет packet выбранным каналом и сообщает, что материал отправлен автору. Если channel/connector не подключён, Codex не обещает отправку и говорит, что packet подготовлен.

## Нельзя

Нельзя спорить с пользователем, требовать вручную копировать trace, отправлять GitHub issue, разбираться в repo-структуре или утверждать, что Sheet записан, если connector не подключён.
