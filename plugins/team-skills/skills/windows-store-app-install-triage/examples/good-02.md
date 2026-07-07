# Хороший Пример

## Вход

"Microsoft Store открывается, сеть у Windows нормальная, `winget show` находит приложение, но Store просит войти и установка не начинается. Проверь WAM."

## Ожидаемое Поведение

Не трогать сеть и NCSI. Проверить `dsregcmd /status`, обратить внимание на `WamDefaultSet` и ошибки WAM, открыть `ms-windows-store://home` и `ms-settings:emailandaccounts` для проверки входа. Если Store account не подтвержден, сначала восстановить вход, затем повторить установку.

## Нельзя

Нельзя делать вывод, что сломан App Installer или службы Store, пока проблема выглядит как account/WAM gate.
