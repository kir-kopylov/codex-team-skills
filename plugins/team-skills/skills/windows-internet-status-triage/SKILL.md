---
name: windows-internet-status-triage
description: >-
  Используйте этот skill, когда Windows показывает "No internet", "Без доступа к Интернету", Offline или IPv4Connectivity != Internet, хотя браузер, curl, winget, Store, ChatGPT или отдельные сайты частично работают. Skill ведет по безопасной диагностике Windows internet-status/NCSI: сначала собрать факты только чтением, сравнить ожидаемый ActiveDnsProbeContent с реальным DNS-ответом dns.msftncsi.com, распознать fake-IP/VPN/proxy/sandbox шум, отделить неверный индикатор Windows от настоящей сетевой поломки, сделать backup перед временной правкой NCSI, перезапустить сетевые службы и проверить rollback. Триггеры: "Windows не видит интернет", "значок сети без интернета, но сайты открываются", "Store/winget думают offline", "NCSI", "dns.msftncsi.com", "198.18.x.x", "почини статус интернета Windows".
---

# Windows Internet Status Triage

## Согласие На Запуск

Явный вызов - slash-команда, имя skill или первая фраза из каталога - выполняйте сразу, без вопроса. При автосрабатывании на смысловое сходство сначала спросите одной строкой: "Задача похожа на экспериментальный team skill `windows-internet-status-triage` - он диагностирует случай, когда Windows ошибочно считает сеть offline при частично живом интернете. Применить или решить без него?" При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

Этот skill не чинит "интернет вообще". Он чинит и диагностирует более узкий симптом: Windows или зависящие от системного статуса приложения считают сеть offline, хотя фактическая связность частично есть.

Главная ловушка: NCSI проверяет интернет через ожидаемые ответы Microsoft. Если DNS, VPN, роутер, transparent proxy или fake-IP режим меняет ответ, Windows может поставить статус "нет интернета", даже когда TCP/HTTPS работают. В таком случае правильная работа - доказать расхождение, сделать backup, применить временный workaround только при необходимости и оставить понятный откат.

## Естественные Входы

- "Windows пишет без интернета, но браузер работает";
- "значок сети показывает No internet";
- "Store или winget не ставит приложение, потому что Windows не видит интернет";
- "Get-NetConnectionProfile показывает NoTraffic/LocalNetwork вместо Internet";
- "dns.msftncsi.com возвращает 198.18.x.x";
- "после VPN/прокси Windows думает, что offline";
- "почини NCSI / ActiveDnsProbeContent".

## Жесткие Правила

- Сначала собрать факты, потом менять состояние. Не править реестр, hosts, DNS, proxy, службы или VPN по догадке.
- Не считать `198.18.x.x` ошибкой само по себе. Это часто fake-IP режим прокси/VPN/роутера; ошибкой становится несовпадение между тем, что Windows ожидает, и тем, что реально возвращает DNS.
- Не выдавать sandbox-симптом за реальную поломку Windows. Если диагностика идет из Codex sandbox и видны `HTTP_PROXY=http://127.0.0.1:9`, странные `Access denied` на CIM или молчаливые падения `winget`, перепроверьте ключевые команды вне sandbox.
- Перед изменением NCSI обязательно сделать backup registry branch `HKLM\SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet`; перед правкой `hosts` - backup файла.
- NCSI workaround считать временным. Финальный ответ обязан сказать, что поменяли, где backup и как вернуть стандартное значение.
- После каждой правки закрывать той же контрольной пробой: `Get-NetConnectionProfile`, DNS probe, HTTP probe NCSI и прикладной симптом пользователя.

## Процесс

### 1. Снимите статус без изменений

Запустите `scripts/collect-network-status.ps1` или вручную соберите тот же минимум:

```powershell
Get-NetConnectionProfile
ipconfig /all
Resolve-DnsName dns.msftncsi.com
Resolve-DnsName www.msftconnecttest.com
curl.exe --max-time 15 http://www.msftconnecttest.com/connecttest.txt
Get-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet'
netsh winhttp show proxy
reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
cmd /c set HTTP
cmd /c set HTTPS
cmd /c set ALL_PROXY
```

Если `Get-NetConnectionProfile` или CIM-команды дают `Access denied` только в агентском окружении, перепроверьте их вне sandbox с повышением, прежде чем делать вывод.

### 2. Разделите три класса проблем

- **Реальная сеть мертва:** NCSI HTTP probe не отвечает, обычные HTTPS endpoints не открываются, шлюз/DNS выглядят сломанными. Этот skill не основной; передайте в обычную сетевую диагностику.
- **Сеть жива, Windows status неверный:** браузер/HTTPS/winget частично работают, но `IPv4Connectivity` не `Internet` или Store считает offline. Продолжайте NCSI-ветку.
- **Проблема только приложения:** Windows показывает `IPv4Connectivity : Internet`, а болит Store/winget/CLI. Закройте этот skill и переходите к skill для установки приложений или CLI runtime.

### 3. Сравните ожидание NCSI и реальный DNS

Смотрите:

- `ActiveDnsProbeHost`
- `ActiveDnsProbeContent`
- реальный `Resolve-DnsName <ActiveDnsProbeHost>`
- ответ через текущий DNS и, при необходимости, через публичный DNS.

Если Windows ожидает `131.107.255.255`, а DNS стабильно возвращает `198.18.x.x`, это вероятный fake-IP/proxy режим. Если Windows уже ожидает `198.18.x.x`, а DNS начал возвращать обычный Microsoft IP, надо не "чинить интернет", а вернуть NCSI к стандарту или синхронизировать ожидание с текущей сетевой политикой.

Для деталей прочитайте `references/ncsi-fake-ip.md`.

### 4. Делайте временную NCSI-правку только при доказанном расхождении

Условия для правки:

- фактическая сеть работает достаточно для задачи;
- Windows status неверный;
- DNS probe content не совпадает с ожидаемым;
- пользователь понимает, что это workaround под текущую DNS/VPN/роутер-политику.

Последовательность:

```powershell
.\scripts\backup-ncsi.ps1
.\scripts\set-ncsi-probe-content.ps1 -ExpectedContent "198.18.1.205"
.\scripts\collect-network-status.ps1
```

`ExpectedContent` не хардкодить. Брать из текущего DNS-ответа `ActiveDnsProbeHost`, если он стабилен и объяснен.

### 5. Обновите статус Windows

После правки очистите DNS cache и перезапустите только нужные службы:

```powershell
ipconfig /flushdns
Restart-Service -Name Dnscache -Force -ErrorAction SilentlyContinue
Restart-Service -Name NlaSvc -Force -ErrorAction SilentlyContinue
Restart-Service -Name netprofm -Force -ErrorAction SilentlyContinue
Start-Service -Name NcaSvc -ErrorAction SilentlyContinue
```

Не перезапускайте VPN/роутер/сетевые адаптеры без отдельного основания.

### 6. Закройте контрольной пробой

Минимальный финальный чек:

```powershell
Get-NetConnectionProfile
Resolve-DnsName dns.msftncsi.com
curl.exe --max-time 15 http://www.msftconnecttest.com/connecttest.txt
winget --info
```

Если исходный симптом был Store/winget, проверьте конкретную команду пользователя, а не только общий статус сети.

### 7. Дайте rollback

Если fake-IP на роутере/VPN уберут, NCSI workaround может стать неправильным. В финале всегда укажите backup и команду:

```powershell
.\scripts\restore-ncsi-backup.ps1 -BackupRegPath "<backup.reg>"
```

Если backup недоступен, стандартное значение обычно:

```powershell
Set-ItemProperty -LiteralPath 'HKLM:\SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet' -Name ActiveDnsProbeContent -Value '131.107.255.255' -Type String
```

Используйте это только после проверки текущей политики сети.

## Границы

Не используйте skill для обхода блокировок, настройки VPN-провайдера, ремонта полностью мертвой сети, замены DNS-политики организации, починки Store при уже корректном `IPv4Connectivity : Internet`, удаления драйверов VPN/TAP/WireGuard, чистки firewall, сброса TCP/IP stack и любых действий без понятного rollback.

Не коммитьте raw логи, IP-адреса локальной сети пользователя, имена Wi-Fi, приватные домены, токены, аккаунты Microsoft или содержимое `auth.json`. В skill переносите только обобщенный паттерн и sanitized симптомы.

## Опрос После Использования

После финального результата или явного стопа спросите один раз:

```text
Опрос по skill:
1. Что в этом использовании windows-internet-status-triage было полезно?
2. Что стоит доработать в skill или его формате?
Можно ответить коротко или написать "пропустить".
```

Если пользователь ответил, сохраните санированную карточку в `~/.codex/skill-runs/windows-internet-status-triage/usage-feedback.jsonl` - лучше через bundled script:

```bash
python3 scripts/log_usage_feedback.py --liked "..." --improve "..." --outcome "..."
```

Script перед записью редактирует приватные пути, контакты и token-like строки и сохраняет в JSONL `redaction_applied` и `redaction_types`. Если запись невозможна из-за sandbox, прав или отсутствия tools, не делайте вид, что лог сохранён: скажите об этом и покажите короткую JSONL-карточку для ручного сохранения. Raw-ответы, контакты, пути и секреты не коммитить.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/<skill-name>/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.
