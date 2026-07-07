# Хороший Пример

## Вход

"Windows видит Internet, `winget show --source msstore` работает, но Store/App Installer не скачивает через включенный локальный VPN/proxy на `127.0.0.1`. Обычный браузер работает."

## Ожидаемое Поведение

Сначала собрать proxy-признаки: `netsh winhttp show proxy`, Internet Settings, proxy env vars, `CheckNetIsolation.exe LoopbackExempt -s`. Если есть локальный proxy/VPN и Store UWP не имеет доступа к loopback, добавить exemptions только для `Microsoft.WindowsStore_8wekyb3d8bbwe`, `Microsoft.StorePurchaseApp_8wekyb3d8bbwe`, `Microsoft.DesktopAppInstaller_8wekyb3d8bbwe`, затем повторить Store/winget установку.

## Нельзя

Нельзя добавлять loopback exemptions "на всякий случай", если proxy/VPN признаков нет.
