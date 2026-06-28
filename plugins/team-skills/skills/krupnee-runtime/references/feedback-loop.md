# Feedback Loop

Этот контур нужен для нетехнического пользователя. Если runtime помешал, пользователь не должен вручную копировать trace, выбирать между log/fixture/issue, знать GitHub или понимать repo-структуру.

## Базовое Поведение

Когда пользователь недоволен вмешательством `krupnee-runtime`:

1. Признать, что вмешательство могло быть неудачным.
2. Предложить отправить автору skill материал для разбора.
3. Задать 1-3 коротких вопроса только если не хватает expected behavior.
4. Самостоятельно сформировать `krupnee_review_packet`.
5. Записать строку в `Team Codex Skill Feedback Inbox`, если channel и connector реально подключены.
6. Сообщить пользователю результат без просьбы вручную копировать packet.

## Разделение Слоёв

- `schema` - формат строки и packet.
- `channel` - куда отправлять feedback.
- `connector` - техническая возможность записи в channel.
- `review` - offline/manual разбор переданного packet.

Не смешивай эти слои. Нельзя утверждать, что Sheet уже существует или что запись выполнена, если channel/connector не подтверждены.

## Feedback Channels

Есть два равноценных канала доставки feedback автору skill. Оба используют один и тот же `krupnee_review_packet`.

### Team Codex Skill Feedback Inbox

Канал для нетехнических пользователей и командного inbox:

```text
Team Codex Skill Feedback Inbox
repo: codex-team-skills
```

Не создавать отдельный Sheet на каждый skill. Не использовать один общий Sheet на все взаимодействия команды с Codex.

### GitHub Issue

Канал для более продвинутых участников команды и maintainers. Это равноценный feedback channel, а не запасной или второстепенный путь. Он может использовать тот же `krupnee_review_packet` в issue body.

## Feedback Row / Issue Body

Feedback row:

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

## Connector Boundary

Если выбранный channel и connector подключены:

- записать feedback row или создать GitHub Issue;
- поставить `author_notified: true`, только если уведомление реально отправлено, issue назначен owner-у или channel гарантирует owner notification;
- сказать пользователю: "Материал отправлен автору skill."

Если channel или connector не подключён:

- сформировать packet;
- не обещать отправку;
- сказать пользователю: "Я подготовил материал для автора skill; автоматическая запись в Feedback Inbox сейчас не подключена."

## Авторский Loop

Когда автор skill получает rows, Codex может сказать:

```text
У тебя новые feedback rows по krupnee-runtime. Разобрать?
```

После согласия автора:

1. Сгруппировать похожие жалобы.
2. Предложить eval cases.
3. Предложить patch в runtime/review docs.
4. Предложить changelog update.
5. Подготовить изменения в repo.

## Privacy

Не сохраняй raw private logs, tokens, private URLs, контакты или приватные пути. Минимизируй dialogue excerpt до нескольких обезличенных строк, достаточных для review.
