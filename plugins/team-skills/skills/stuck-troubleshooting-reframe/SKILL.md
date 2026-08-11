---
name: stuck-troubleshooting-reframe
description: "Используйте этот экспериментальный skill, когда живая диагностика зациклилась: две попытки на одном слое дали тот же failed/partial или есть повторный no-outcome при зелёных промежуточных сигналах. Триггеры: «мы ходим кругами», «всё было мимо», «пересмотри предпосылки», «connected есть, а результата нет». Одна просьба найти, как другие решили проблему, без зацикленной локальной диагностики не запускает skill."
---

# Stuck Troubleshooting Reframe

## Согласие На Запуск

Явный вызов — команда, внутреннее имя skill или первая фраза из каталога — выполняйте сразу, без вопроса.

При автосрабатывании сначала проверьте, что в запросе есть зацикленная диагностика: названы недостигнутый outcome и либо две повторённые failed/partial попытки, либо повторный no-outcome при ложных зелёных сигналах. Одиночный ложный зелёный сигнал не открывает reframe. Одна просьба найти чужой опыт без repair-loop не является смысловым автотриггером: не показывайте карточку и передайте запрос в `kak-drugie-reshili`.

Для релевантного запроса извлеките действие пользователя, конкретную систему и различие между новым pivot gate и ещё одним действием в закрытой ветке. Затем без вводного объяснения заполните карточку:

Применить **«Выход из зацикленной диагностики»** (@kir-kopylov; экспериментальный) для выхода из <названной зацикленной диагностики>?

**С навыком:** Закроем повторённую ветку и выберем один новый локальный gate с falsifier, rollback и stop condition.

**Без навыка:** Продолжим обычную диагностику без обязательной фиксации повторов и смены слоя.

Перед отправкой замените угловые скобки сведениями из запроса: неизвестное не придумывайте. В карточке должны быть ровно три содержательные строки и не более 45 слов. «С навыком» и «Без навыка» занимают по одной строке и одному предложению, показывают только различие и не повторяют запрос. Не добавляйте таблицу, служебный жаргон, кодовую рамку или заголовок `Annotation N`.

После карточки ждите ответа. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Назначение

Этот skill нужен не для старта диагностики. Он включается, когда факты уже есть, но они не двигают пользовательский outcome.

Главное правило: действие без названного gate запрещено. Gate должен проверять новую гипотезу, а не обслуживать уже закрытую ветку.

Типовой симптом: listener поднят, TCP established, UI показывает connected, лог пишет progress, curl отвечает или welcome screen открылся, но результата, который пользователь назвал успехом, нет.

## Быстрый Роутинг

- Первый неоднозначный сбой ещё не зациклился: используйте
  `proverka-prichin-sboya`, чтобы выбрать одну безопасную проверку причин.
- Пользователь просит только найти, как другие решали похожую проблему, а повторённого local no-outcome нет: не запускайте reframe; используйте `kak-drugie-reshili`.
- Диагностика уже зациклилась, а внешний опыт нужен для смены слоя: применяйте skill, но используйте внешний кандидат только как вход в local gate.
- Пользователь говорит, что диагностика долго шла "мимо": применяйте skill, если есть журнал, список веток или текущий факт.
- В задаче два раза повторился одинаковый failed/partial на одном слое: применяйте skill перед третьим действием.
- Нет outcome, текущего факта или списка уже проверенных веток: не запускайте reframe; попросите один недостающий вход.

## Минимальные Входы

Заполните до анализа:

```text
outcome: успехом считается только ...
current_state: что сейчас наблюдаемо, с временем/источником
constraints: что нельзя менять, запускать, удалять, повторять
attempts: проверенные ветки и их факты
false_positive_signals: что выглядело зеленым, но не стало outcome
```

Если любого обязательного поля нет, остановитесь и запросите ровно один самый дешёвый факт. Опционально можно передать `external_practice_candidate`: карточку чужого опыта с происхождением и `local_status: NOT_TESTED`.

## Рабочий Протокол

1. `Known Exceptions Gate`: прочитайте `known-exceptions.yaml`, если он есть рядом с skill. Если симптом совпал, примените `do_next_time` без нового поиска.
2. `Outcome Contract Gate`: отделите успех от промежуточных признаков. Формула: "`X` доказал только `Y`, но не доказал `Z`".
3. `State Fingerprint Gate`: зафиксируйте состояние до нового действия. Без fingerprint нельзя считать "это уже пробовали".
4. `Layer Ledger Gate`: разложите попытки по слоям и посчитайте `same_state_count`.
5. `Reframe Eligibility Gate`: если `same_state_count < 2` и нет повторного no-outcome при ложных зелёных сигналах, вернитесь к обычной диагностике. Одиночный ложный зелёный сигнал не открывает reframe; просьба найти похожие кейсы не открывает reframe без повторного no-outcome.
6. `External Case Gate`: примите один `CandidatePacket v1` из `kak-drugie-reshili`. Кандидат должен дать локально проверяемый observable; его внешний статус не доказывает локальную причину. Если кандидата нет, а новый слой уже следует из локальных фактов, отметьте `external check: not performed`. Если без внешнего кандидата новый слой не выбрать, остановитесь до action и передайте один вопрос в `kak-drugie-reshili`; не начинайте открытый веб-поиск внутри skill.
7. `Pivot Gate`: закройте старую ветку и откройте новую только если она меняет слой или механизм.
8. `Action Gate`: назовите одно действие, владельца, ожидаемое наблюдение, falsifier, rollback и stop condition.
9. `Outcome Check Gate`: после действия сравните факт с исходным outcome. Не называйте успехом proxy-признак.

## Обязательные Поля

Любой ответ по skill должен содержать эти поля, даже если часть значений равна `unknown`:

```text
outcome:
current_state:
old_layer:
old_hypothesis:
same_state_count:
false_positive_signals:
state_fingerprint:
closed_branch:
external_case_matrix:
new_layer:
new_hypothesis:
gate:
action:
action_owner:
expected_observation:
falsifier:
rollback:
stop_condition:
do_not_repeat:
```

Если пользователь в стрессе, можно показать короткий блок, но эти поля должны быть заполнены внутренне до действия.

## Layer Taxonomy

Используйте фиксированные имена слоев, чтобы не спорить словами:

| layer | Что проверяет |
| --- | --- |
| `user-ui` | Видит ли пользователь outcome в интерфейсе |
| `target-process` | Жив ли нужный процесс, его окна, потоки, child-processes |
| `app-config` | Настройки самого приложения, proxy/auth/account/profile |
| `local-env-proxy` | Локальные listener, SOCKS/HTTP proxy, env proxy, PAC |
| `dns` | Разрешение имен, fake DNS, split DNS, DNS leak |
| `route-interface` | Маршруты, интерфейсы, TUN/TAP, метрики, binding |
| `vpn-core` | xray/sing-box/openvpn/wireguard core, правила, outbound |
| `remote-service` | Доступность сервера, DC, API, rate limit, регион |
| `auth-account` | QR/SMS/2FA/session/account challenge |
| `filesystem-state` | Профиль, cache, lock, permission, local DB |
| `test-harness` | Тайминги теста, fixtures, mocks, runner, CI env |
| `data-contract` | Миграции, schema, payload, validation, API contract |

Новая гипотеза должна перейти в другой `layer` или назвать новый механизм внутри старого слоя с новым observable.

## State Fingerprint

Fingerprint нужен, чтобы "два раза одно и то же" было проверяемым фактом, а не ощущением.

```text
state_fingerprint:
  target:
  timestamp:
  outcome_visible:
  layer:
  config_snapshot:
  process_socket_snapshot:
  route_env_snapshot:
  last_action:
  result:
  evidence:
```

Не включайте секреты, аккаунты, raw logs, приватные пути и токены. Сохраняйте только санированные признаки.

## Layer Ledger

Заполните кратко:

```text
layer_ledger:
  - layer:
    hypothesis:
    gate:
    action:
    fact:
    verdict: failed | partial | useful | success
```

Правило повторов: два `failed` или `partial` с тем же `state_fingerprint` закрывают ветку. Третье действие на том же слое запрещено до нового факта.

## External Case Matrix

Внешний кейс не доказывает локальную причину. Он только предлагает новый gate.

```text
external_case_matrix:
  - case:
    source_type: issue | forum | docs | incident | memory | user_report
    same_symptom:
    same_mechanism:
    fix_used:
    local_observable:
    applicable: yes | no | unknown
```

Принимается только кейс, у которого есть `local_observable`. Если observable нет, кейс идет в справку, но не в action.
Статус вроде `REVIEWED_EXTERNAL_PRACTICE_CANDIDATE` доказывает только точность передачи чужого опыта. До выполнения local gate его `local_status` остаётся `NOT_TESTED`.

## Pivot Gate Format

Используйте этот формат перед любым действием:

```text
Pivot gate:
- closed_branch_id:
- old_layer:
- old_hypothesis:
- why_closed:
- false_positive_signals:
- new_layer:
- new_hypothesis:
- gate:
- action:
- action_owner: assistant | user | both
- expected_observation:
- falsifier:
- rollback:
- stop_after:
- do_not_repeat:
```

`falsifier` должен быть конкретным: какой факт закроет новую гипотезу. `rollback` обязателен для любых изменений конфигурации, запуска фонового процесса, proxy/VPN, auth, firewall, repo state, данных или CI settings.

## Stop Conditions

Остановитесь и не выполняйте действие, если верно хотя бы одно:

1. Нет `outcome` или `current_state`.
2. Нет названного `gate`.
3. Действие не может изменить failing gate.
4. `same_state_count >= 2`, а действие снова идет в тот же `old_layer`.
5. Внешний кейс не дал `local_observable`.
6. Нет `action_owner`, `expected_observation`, `falsifier` или `rollback`.
7. Действие нарушает пользовательские запреты.
8. Действие меняет состояние с длительными последствиями без явного согласия или rollback.
9. Для домена есть более конкретный skill, а базовые факты еще не собраны.
10. Успех требует телефона, SMS, 2FA, платежа или приватного действия пользователя: дайте одну точную инструкцию и остановитесь.

## Precedence

Этот skill не заменяет доменные runbook. Если есть конкретный skill для Windows VPN, CI, browser automation, GitHub PR, data validation или repo workflow, сначала используйте его для базовых gates. При первом неоднозначном сбое используйте `proverka-prichin-sboya`; `stuck-troubleshooting-reframe` включайте после двух одинаковых неразличающих циклов, повторного no-outcome в доменной ветке или прямой просьбы сменить предпосылки. `kak-drugie-reshili` отвечает за происхождение и точность извлечения чужого кейса; этот skill отвечает за его превращение в локальную проверку.

## Анти-Правила

1. Не превращайте skill в "поищи еще ссылок". Поиск заканчивается, когда есть новый локальный gate.
2. Не объявляйте причину без текущего инструмента, лога, скрина или результата действия.
3. Не переписывайте историю так, будто новый вывод был очевиден с начала.
4. Не называйте `connected`, `established`, `listener`, `welcome`, `HTTP 200`, `raw CONNECT`, `green check` успехом, если outcome другой.
5. Не делайте третий restart/retry/reapply/wait с тем же fingerprint.
6. Не переносите raw logs, скриншоты, личные пути, аккаунты, токены и частную переписку в repo/examples.

## Границы

Используйте этот skill для repair-loop, CI/debug, browser/API troubleshooting, сетевых и UI-инцидентов, где есть ловушка "частичные признаки вместо outcome".

Не используйте его:

- в первые минуты задачи, пока не собраны базовые факты;
- для обычного code review;
- для one-shot вопроса без repair-loop;
- для отдельного поиска чужого опыта без повторённого локального no-outcome;
- когда уже есть точная failing assertion и следующий fix очевиден;
- когда задача требует только сформулировать новый team skill contract -- это `skill-methodologist`;
- когда нужно создать файлы skill в repo -- это `add-team-skill`.

## Опрос После Использования

Опрос задаётся один раз -- после выдачи pivot gate и проверки хотя бы одного нового gate либо после явного стопа, не посреди рабочего цикла. Если пользователь уже ответил «пропустить» в этой сессии, не переспрашивайте.

```text
Опрос по skill:
1. Что в этом использовании stuck-troubleshooting-reframe было полезно?
2. Что стоит доработать в skill или его формате?
Можно ответить коротко или написать "пропустить".
```

Если пользователь ответил, сохраните санированную карточку в `~/.codex/skill-runs/stuck-troubleshooting-reframe/usage-feedback.jsonl` -- лучше через bundled script:

```bash
python3 scripts/log_usage_feedback.py --liked "..." --improve "..." --outcome "..."
```

Script перед записью редактирует приватные пути, контакты и token-like строки и сохраняет в JSONL `redaction_applied` и `redaction_types`. Если запись невозможна из-за sandbox, прав или отсутствия tools, не делайте вид, что лог сохранён: скажите об этом и покажите короткую JSONL-карточку для ручного сохранения. Raw-ответы, контакты, пути и секреты не коммитить.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/stuck-troubleshooting-reframe/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.

## Definition Of Done

Skill завершил работу, когда есть:

- `outcome` и `current_state`;
- `state_fingerprint`;
- `layer_ledger` с закрытой старой веткой;
- список false-positive признаков;
- `external_case_matrix` или явная отметка, что external check не выполнен;
- `pivot gate` с новым `layer` или новым observable;
- `action_owner`, `expected_observation`, `falsifier`, `rollback`;
- стоп-условие, при котором новая ветка закрывается;
- короткое объяснение пользователю, что именно изменилось в модели и что делать дальше.
