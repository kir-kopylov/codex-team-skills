# Хороший Пример

## Вход

Пользователь показывает вывод: внутри Codex `codex doctor` ругается на WebSocket, `winget --info` молча падает, в env есть `HTTP_PROXY=http://127.0.0.1:9`; но обычный терминал показывает `codex doctor` зеленым.

## Ожидаемое Поведение

Отнести эти симптомы к sandbox/agent environment, а не к Windows. Перепроверить ключевые команды вне sandbox/elevated и только потом делать вывод. Если вне sandbox `Get-NetConnectionProfile` и `winget --info` нормальные, закрыть NCSI-ветку и не менять системные настройки.

## Нельзя

Лечить Windows registry, Store, proxy или NCSI на основании ограничений агентского sandbox.
