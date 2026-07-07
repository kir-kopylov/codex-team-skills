# Анти-Пример

## Вход

"Store не ставит приложение, а Windows пишет No internet. `Get-NetConnectionProfile` показывает `IPv4Connectivity : NoTraffic`."

## Ожидаемое Поведение

Остановить этот skill. Сказать, что Store-диагностика преждевременна: сначала нужно привести Windows internet-status/NCSI к `IPv4Connectivity = Internet`. Передать задачу в сетевой/NCSI triage.

## Нельзя

Нельзя перезапускать Store-службы, чинить App Installer, менять loopback exemptions или запускать `winget install`, пока Windows сама не видит Internet.
