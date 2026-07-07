# Хороший Пример

## Вход

"Поставь приложение из Microsoft Store: `winget install --id 9NBLGGH5R558 --source msstore`. До этого Store ругался, но `Get-NetConnectionProfile` уже показывает `IPv4Connectivity : Internet`."

## Ожидаемое Поведение

Сначала подтвердить gate `IPv4Connectivity = Internet`. Затем зафиксировать Store ID, выполнить `winget show --id 9NBLGGH5R558 --source msstore`, сверить name/publisher с ожиданием пользователя и только потом запускать `winget install`. Если `winget show` не подтверждает пакет, остановиться и запросить Store URL или publisher.

## Нельзя

Нельзя сразу запускать установку по похожему имени, менять NCSI или рестартовать Store-службы до проверки package identity.
