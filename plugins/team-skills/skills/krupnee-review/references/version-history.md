# Version History

## 0.2.0

- Разделён `krupnee_lift` на короткий runtime layer и длинный review layer.
- Runtime сфокусирован на минимальном вмешательстве: сначала выполнить, lift предлагать только после паттерна или явного риска.
- Зафиксированы `krupnee_buffer`, scoring и условия перехода в `offer_lift`.
- Добавлены режимы `observe`, `soft_hint`, `offer_lift`, `risk_override`, `do_not_intervene`.
- Добавлены review prompt, telemetry schema и eval cases без переноса тяжёлой методологии в runtime.
- Уточнено, что `krupnee-review` является offline/manual evaluator и работает только на явно переданном материале.
- Добавлены `trace_source`, `review_trigger`, `access_policy`, `runtime_trace_mechanism` и `review_output`.
- Добавлен feedback loop для недовольства пользователя: `dissatisfaction_feedback`, `Team Codex Skill Feedback Inbox` и `GitHub Issue` как равноценные feedback channels, единый review packet и author workflow.
