# Хороший Пример: Same-State Repeat Запрещён

## Вход

Пользователь уже три раза перезапускал VPN, закрывал приложение и снова запускал его. Результат не меняется. Он просит "продолжай сам, только не ходи кругами".

## Ожидаемое Поведение

Skill собирает state fingerprint:

```text
target_app=DesktopApp
vpn_ui=connected
app_proxy=default
windows_proxy=unknown
dns=fake-or-unknown
route=tun-or-unknown
ui=offline
last_action=restart_vpn
```

В `do_not_repeat` попадает запрет повторять `restart_vpn` при том же fingerprint. Повтор разрешён только если изменился один из влияющих слоёв: режим VPN, proxy внутри приложения, системный proxy, DNS/route или версия приложения.

## Нельзя

Нельзя снова перезапускать VPN "на всякий случай" без изменения состояния. Нельзя запрещать ретест навсегда: после реального изменения маршрута или proxy повтор может стать полезным.
