# Repair State Bundle

`repair_state_bundle` - короткий набор артефактов, который агент перечитывает перед каждым новым экспериментом в длинной repair-задаче. Он нужен, чтобы после обрыва контекста, сна компьютера или смены VPN не повторять старые ходы и не закрывать цель по косвенному признаку.

## Минимальный Состав

```text
goal_contract.md
completion_gate.md
experiment_ledger.jsonl
do_not_repeat.md
current_layer_verdict.md
fresh_evidence/
```

## Completion Gate

```yaml
user_visible_success: "Что пользователь считает работающим состоянием."
direct_evidence: "Свежий внешний артефакт или подтверждение пользователя."
forbidden_false_positives:
  - "процесс запущен"
  - "форма входа открыта"
  - "spinner крутится"
  - "CLI-тест успешен"
freshness: "Когда evidence получено и почему оно ещё актуально."
human_gate: "Что может подтвердить только пользователь."
contradictions_checked: "Какие наблюдения могли спорить с выводом."
close_allowed: "yes/no"
```

## Experiment Ledger

Каждая запись описывает не только действие, но и состояние, при котором действие уже проверено.

```json
{
  "time": "ISO-8601 или локальная отметка",
  "state_fingerprint": "vpn=on; app_proxy=default; dns=fakedns; ui=offline",
  "hypothesis": "какую гипотезу различаем",
  "action": "одно действие или проверка",
  "owner": "assistant/user/system",
  "result": "что наблюдалось",
  "same_state_repeat": "forbidden",
  "repeat_allowed_if": "изменился VPN mode, app proxy, DNS, route или UI state",
  "evidence": "где лежит свежий артефакт без приватных данных"
}
```

## Do-Not-Repeat

Запрещайте повтор только при том же `state_fingerprint`. Ретест после изменения влияющего слоя не является бессмысленным повтором.

Плохое правило: "не перезапускать VPN никогда".

Хорошее правило: "не перезапускать VPN повторно при `vpn=on; app_proxy=default; ui=offline`, пока не изменён app proxy, VPN mode, route или DNS".

## Layer Verdict

```text
user-visible app UI:
process/sockets:
app proxy config:
Windows proxy/env:
DNS/fakeDNS:
routes/interfaces:
VPN core/local proxy:
external reachability:
next experiment:
expected observation:
what would falsify it:
rollback:
```

## Правило Возобновления

После compaction, reboot, сна или ручного действия пользователя сначала перечитайте bundle и обновите свежий state fingerprint. Не продолжайте старый план, пока не проверено, что состояние действительно то же самое.
