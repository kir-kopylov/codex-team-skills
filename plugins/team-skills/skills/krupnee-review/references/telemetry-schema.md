# Telemetry Schema

Сохраняй только минимальный trace, когда `krupnee_lift` оценивается или применяется.

```yaml
skill: krupnee_lift
version: 0.2.0
trace_source: pasted_dialogue # pasted_dialogue | local_sanitized_trace | feedback_packet | eval_fixture | runtime_self_report | unknown
review_trigger: user_complaint # user_complaint | user_dissatisfaction | maintainer_review | author_feedback_review | eval_runner | runtime_feedback | unknown
feedback_channel: none # none | team_codex_skill_feedback_inbox | github_issue
feedback_row_status: none # none | new | reviewing | patch_proposed | closed
mode: observe # observe | soft_hint | offer_lift | risk_override | do_not_intervene
microstep_count: 1 # 1 | 2 | 3+
trigger_reason: ""
user_choice: ignored # execute_only | lift | ignored
source_messages_count: 1
final_krupnee_prompt_created: false
review_output: verdict # verdict | eval_case | patch_proposal | changelog_needed | no_action
feedback: unknown # useful | unnecessary | missed | unknown
```

## Field Notes

- `skill`: всегда `krupnee_lift`.
- `version`: стартовая версия `0.2.0`.
- `trace_source`: откуда review получил материал; допустимы также `dissatisfaction_feedback` и `feedback_inbox_row`, если они пришли из feedback loop.
- `review_trigger`: кто или что запустило review.
- `feedback_channel`: channel, через который пришёл feedback. `team_codex_skill_feedback_inbox` и `github_issue` - равноценные каналы доставки одного `krupnee_review_packet`.
- `feedback_row_status`: состояние строки feedback, если source пришёл из inbox.
- `mode`: выбранный режим вмешательства.
- `microstep_count`: считай только связанные микрошаги в активном окне.
- `trigger_reason`: короткая причина без raw-приватного текста.
- `user_choice`: `execute_only`, если пользователь выбрал работу по кускам; `lift`, если выбрал сборку prompt; `ignored`, если выбор не спрашивался или не был дан.
- `source_messages_count`: число последних сообщений, которые реально учитывались.
- `final_krupnee_prompt_created`: `true` только если был собран полный prompt для агента.
- `review_output`: что produced review после анализа.
- `feedback`: `useful`, `unnecessary`, `missed` или `unknown`.

## Storage Boundary

Этот schema описывает формат, а не механизм записи. В текущем MVP нет автоматического sink для telemetry.

Допустимые источники для review:

- вставленный пользователем диалог;
- очищенный local trace;
- feedback packet;
- dissatisfaction feedback packet;
- строка из Team Codex Skill Feedback Inbox, если channel и connector подключены;
- GitHub Issue body, если GitHub channel и connector подключены или maintainer явно передал issue content;
- eval fixture;
- runtime self-report в текущем диалоге.

Без явно переданного источника review не должен утверждать, что telemetry существует или доступна.

## krupnee_review_packet

```yaml
krupnee_review_packet:
  trace_source: dissatisfaction_feedback
  review_trigger: user_dissatisfaction
  repo: codex-team-skills
  skill_name: krupnee-runtime
  skill_version: 0.2.0
  dissatisfaction_signal: ""
  minimal_dialogue_excerpt:
    - user: ""
    - assistant: ""
  actual_behavior: ""
  expected_behavior: ""
  suspected_issue: unknown # false_positive | missed_lift | overlong_runtime | ignored_preference | risk_override_error | unknown
  privacy_note: raw private context excluded
  requested_review_output:
    - verdict
    - eval_case
    - patch_proposal
```

## Feedback Inbox Row

```yaml
created_at: ""
repo: codex-team-skills
skill_name: krupnee-runtime
skill_version: 0.2.0
feedback_channel: team_codex_skill_feedback_inbox # team_codex_skill_feedback_inbox | github_issue
user_signal: ""
dissatisfaction_signal: ""
what_happened: ""
expected_behavior: ""
actual_behavior: ""
suspected_issue: unknown
minimal_dialogue_excerpt: []
privacy_level: sanitized
owner: "@kir-kopylov"
status: new
next_action: review_with_krupnee-review
review_packet: {}
author_notified: false
```

## Privacy Rules

- Не храни raw-приватные сообщения, если достаточно короткой причины.
- Не храни tokens, credentials, личные контакты, private URLs или private file paths.
- Предпочитай labels вроде `client_message`, `public_post`, `code_change`, `commit_risk` вместо копирования чувствительного текста.
