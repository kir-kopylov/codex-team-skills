# NCSI, Fake-IP И Границы Workaround

## Что Проверяет Windows

Windows NCSI хранит параметры в:

```text
HKLM\SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet
```

Ключевые поля:

- `ActiveDnsProbeHost` - DNS host для проверки, обычно `dns.msftncsi.com`.
- `ActiveDnsProbeContent` - ожидаемый IP-ответ, часто `131.107.255.255`.
- `ActiveWebProbeHost` и `ActiveWebProbePath` - HTTP probe, обычно `www.msftconnecttest.com/connecttest.txt`.
- `EnableActiveProbing` - активна ли проверка.

Диагноз строится на сравнении: что Windows ожидает, что DNS реально возвращает, и работает ли HTTP/HTTPS вне индикатора Windows.

## Как Читать 198.18.x.x

`198.18.0.0/15` часто используется fake-IP режимами прокси/VPN/роутеров. Это не самостоятельная поломка.

Положительный сигнал:

```text
dns.msftncsi.com -> 198.18.1.205
example.com -> 198.18.x.x
chatgpt.com -> 198.18.x.x
```

Такой паттерн означает, что DNS-ответы, вероятно, подменяются до Windows или на прозрачном сетевом слое.

Отсутствие `198.18.x.x` ничего не доказывает: VPN может работать без fake-IP DNS.

## Когда Менять ActiveDnsProbeContent

Менять только если:

- пользовательский симптом именно Windows internet-status;
- фактическая сеть частично работает;
- `ActiveDnsProbeContent` не совпадает с реальным стабильным DNS-ответом `ActiveDnsProbeHost`;
- есть backup;
- пользователь понимает, что при смене политики DNS workaround надо откатить.

Не менять, если:

- `IPv4Connectivity` уже `Internet`;
- проблема только в Store login, WAM, winget source, CLI auth или конкретном приложении;
- сеть полностью мертва;
- DNS-ответ нестабилен;
- нет прав или backup.

## Rollback-Модель

Если fake-IP убрали, вернуть NCSI к backup или стандарту:

```powershell
Set-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet' -Name ActiveDnsProbeContent -Value '131.107.255.255' -Type String
ipconfig /flushdns
Restart-Service -Name NlaSvc -Force -ErrorAction SilentlyContinue
Restart-Service -Name netprofm -Force -ErrorAction SilentlyContinue
```

После rollback снова проверить `Get-NetConnectionProfile` и HTTP probe.

## Sandbox-Шум

Codex/sandbox может добавлять proxy env vars или ограничивать network/CIM. Признаки:

- `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` указывают на `127.0.0.1:9`;
- `winget --version` или `winget --info` падают только внутри sandbox;
- `Get-NetConnectionProfile` дает `Access denied`, а вне sandbox работает;
- `codex doctor` ругается на WebSocket/reachability внутри sandbox, но зеленый вне него.

Эти признаки требуют перепроверки вне sandbox, а не правки Windows.
