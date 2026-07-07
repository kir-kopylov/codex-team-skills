# Анти-Пример

## Вход

Пользователь пишет: "`Get-NetConnectionProfile` уже показывает `IPv4Connectivity : Internet`, но `winget install --source msstore` не ставит приложение."

## Неправильное Поведение

Ассистент продолжает менять NCSI, подгоняет `ActiveDnsProbeContent` и перезапускает сетевые службы.

## Почему Это Плохо

Windows internet-status уже исправен. Дальше болит не NCSI, а Store/App Installer/WAM/login/package flow.

## Правильно

Закрыть этот skill и перейти к Windows Store/app install triage: проверить `winget show`, `winget --info`, Store login, `dsregcmd /status`, App Installer и службы Store.
