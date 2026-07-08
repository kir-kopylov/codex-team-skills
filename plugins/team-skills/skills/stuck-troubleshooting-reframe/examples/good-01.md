# Хороший Пример

## Вход

Пользователь чинит desktop-приложение под VPN. Уже проверены локальный proxy listener, TCP established к серверу, "connected" в VPN UI и welcome screen приложения. Реального результата нет: приложение не показывает рабочие данные. Пользователь пишет: "мы четыре часа ходим кругами, найди как люди решали похожее".

## Ожидаемое Поведение

Агент не продолжает app-level proxy ветку. Он заполняет поля:

```text
outcome: видны чаты/обновления или сканируемый QR
current_state: proxy selected, connecting..., QR не отрисован
old_layer: app-config / local-env-proxy
same_state_count: 2
false_positive_signals: listener, TCP established, VPN UI connected, welcome screen
```

Затем агент строит `state_fingerprint`, `layer_ledger` и `external_case_matrix`. Похожие кейсы принимаются только если дают `local_observable`, например TUN interface, маршруты, VPN core process, DNS path. Новый `Pivot gate`:

```text
gate: проверить system-level route-interface/vpn-core вместо app-level proxy
action_owner: assistant
expected_observation: активный TUN/interface и route для приложения или их отсутствие
falsifier: TUN/routes есть, но приложение всё равно не достигает outcome при свежем UI check
rollback: не менять настройки приложения; только read-only проверка routes/processes
stop_after: один no-outcome с тем же fingerprint закрывает эту ветку
```

## Нельзя

Нельзя повторять "перезапусти приложение", "снова примени proxy" или "подожди QR/обновление", если эти действия уже дважды давали тот же no-outcome.
