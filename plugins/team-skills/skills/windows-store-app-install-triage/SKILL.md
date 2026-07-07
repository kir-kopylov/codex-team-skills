---
name: windows-store-app-install-triage
description: >-
  Используйте этот skill, когда приложение не устанавливается через Microsoft Store или `winget --source msstore`, но Windows уже показывает `IPv4Connectivity = Internet`. Skill ведет диагностику Store ID, publisher/package name, `winget show`, входа Microsoft Store/WAM (`dsregcmd /status`), App Installer, служб Store, proxy/VPN loopback exemptions при наличии признаков proxy/VPN и только затем запускает установку. Триггеры: "Store не устанавливает приложение", "winget msstore не ставит", "проверь Microsoft Store install", "App Installer сломан", "Store просит вход/ничего не скачивает". Не использовать для NCSI/No internet/Offline-статуса Windows.
---

# Windows Store App Install Triage

## Согласие На Запуск

Явный вызов - slash-команда, имя skill или первая фраза из каталога - выполняйте сразу, без вопроса. При автосрабатывании на смысловое сходство сначала спросите одной строкой: "Задача похожа на экспериментальный team skill `windows-store-app-install-triage` от `@kir-kopylov` - чинит установку приложений через Microsoft Store/`winget msstore`, но только если Windows уже видит интернет. Применить или решить без него?" - и ждите ответа. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

Этот skill закрывает узкую задачу: Microsoft Store или `winget install --source msstore` не устанавливает конкретное приложение, при этом сама Windows уже считает сеть полноценной (`IPv4Connectivity = Internet`).

Это не сетевой skill. Его задача - не "починить интернет", а доказательно пройти путь установки:

1. подтвердить, что Windows internet-status уже зеленый;
2. убедиться, что ставится правильный Store product ID / publisher / package;
3. проверить, что `winget` видит приложение в source `msstore`;
4. проверить вход Microsoft Store и WAM;
5. проверить App Installer и Store-службы;
6. проверять loopback exemptions только при признаках proxy/VPN;
7. только после этого запускать установку и закрывать контрольной проверкой.

## Естественные Входы

- "Microsoft Store не устанавливает приложение";
- "`winget install --source msstore` падает";
- "Store пишет, что нет сети, но Windows уже показывает Internet";
- "проверь Store ID перед установкой";
- "App Installer или winget msstore не работает";
- "Store просит вход / не видит аккаунт / WAMDefaultSet";
- "надо поставить приложение из Microsoft Store по ID".

Если пользователь говорит "Windows не видит интернет", "значок сети без интернета", "`IPv4Connectivity` не `Internet`", "NCSI", `dns.msftncsi.com`, `ActiveDnsProbeContent` или `198.18.x.x`, не используйте этот skill как основной. Сначала нужна диагностика Windows internet-status/NCSI.

## Жесткий Входной Gate

Перед любыми Store/winget действиями выполните:

```powershell
Get-NetConnectionProfile | Select-Object Name,InterfaceAlias,NetworkCategory,IPv4Connectivity,IPv6Connectivity
```

Решение:

- есть активный профиль с `IPv4Connectivity : Internet` - продолжайте этот skill;
- `IPv4Connectivity` равно `NoTraffic`, `LocalNetwork`, `Disconnected` или вывода нет - остановитесь, не лечите Store, передайте задачу в Windows internet-status/NCSI triage;
- если команда выполнялась внутри sandbox/Codex и результат спорный, перепроверьте вне sandbox/elevated перед выводом о реальной Windows-сети.

Финальная формулировка при остановке: "Store сейчас не является первым подозреваемым: Windows сама не подтверждает IPv4Connectivity = Internet. Сначала надо чинить Windows internet-status/NCSI, иначе Store-диагностика даст ложные ветки."

## Быстрый Снимок

Если доступен PowerShell на Windows, используйте bundled read-only collector:

```powershell
.\scripts\collect-store-install-status.ps1 -StoreId "STORE_ID"
```

Скрипт ничего не меняет: собирает `Get-NetConnectionProfile`, `winget --info`, `winget source list`, `winget show --source msstore` для указанного ID, `dsregcmd /status`, Appx-пакеты Store/App Installer, службы, proxy-сигналы и loopback exemptions. Не подменяйте им решение: используйте JSON как снимок фактов.

## Процесс

Перед выполнением прочитайте локальный `known-exceptions.yaml` и применяйте подходящее `do_next_time` без нового поиска.

### 1. Зафиксировать, Что Ставим

Соберите минимум:

- Store product ID, например `9NBLGGH5R558`;
- Store URL, если есть;
- ожидаемое имя приложения;
- publisher;
- package name / package family name, если уже известны;
- точную команду установки и текст ошибки.

Если пользователь дал только "поставь приложение" без ID или URL, не угадывайте. Попросите Store-ссылку или название + publisher, затем проверьте через `winget search`/`winget show`.

Правило: product ID, package name и publisher не взаимозаменяемы. Не устанавливайте по похожему имени, пока `winget show` не подтвердил publisher и source.

### 2. Проверить `winget show`

Для Store product ID:

```powershell
winget show --id STORE_ID --source msstore
```

Решение:

- `winget show` нашел приложение, name/publisher совпадают - продолжайте;
- `No package found` / не тот publisher / не то имя - остановитесь и уточните Store URL или правильный ID;
- `winget` не найден, source `msstore` недоступен или `winget show` падает до поиска приложения - переходите к App Installer/source ветке, а не к установке.

Если пользователь дал Store URL, извлеките product ID из последнего сегмента URL или `productid=...`, затем все равно подтвердите через `winget show`.

### 3. Проверить Вход Microsoft Store И WAM

Снимите WAM-статус:

```powershell
dsregcmd /status
```

Ищите `WamDefaultSet`, ошибки в секции WAM, состояние AzureAD/Workplace join только как контекст. Не делайте из `AzureAdJoined : NO` проблему для личного Store-аккаунта само по себе.

Параллельно проверьте вручную Store GUI:

```powershell
Start-Process ms-windows-store://home
Start-Process ms-settings:emailandaccounts
```

Решение:

- Store явно не вошел в Microsoft account или WAM сломан - сначала восстановите вход/аккаунт; не рестартуйте службы вслепую;
- Store вошел, WAM выглядит нормально - переходите к App Installer;
- если установка требует покупки, региона, возраста, корпоративной политики или лицензии - это не техническая установка, не обходите ограничения.

### 4. Проверить App Installer И Sources

```powershell
winget --info
winget source list
Get-AppxPackage -Name Microsoft.DesktopAppInstaller
Get-AppxPackage -Name Microsoft.WindowsStore
Get-AppxPackage -Name Microsoft.StorePurchaseApp
```

Решение:

- `Microsoft.DesktopAppInstaller` отсутствует или `winget` не запускается - восстановите/обновите App Installer из Store или официального источника Microsoft;
- source `msstore` отсутствует/битый - используйте `winget source reset --force` или `winget source update` только после того, как показали пользователю, что source действительно сломан;
- App Installer и source нормальные - переходите к службам.

### 5. Проверить Службы Store

Сначала только чтение:

```powershell
Get-Service ClipSVC,InstallService,TokenBroker,wlidsvc,AppXSvc,LicenseManager,BITS,DoSvc,wuauserv -ErrorAction SilentlyContinue |
  Select-Object Name,Status,StartType,DisplayName
```

Если нужная служба остановлена или зависла, запускайте/перезапускайте только конкретно обоснованные службы, обычно elevated:

```powershell
Start-Service ClipSVC,InstallService,TokenBroker,wlidsvc,AppXSvc,LicenseManager -ErrorAction SilentlyContinue
```

Не начинайте с `wsreset.exe`, переустановки Store или массового "restart everything". Это поздние меры, а не диагностика.

### 6. Проверить Loopback Exemptions Только При Proxy/VPN Признаках

Эту ветку включайте только если есть признаки proxy/VPN:

- системный proxy или WinHTTP proxy указывает на `127.0.0.1`/`localhost`;
- переменные окружения `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`;
- Store/StorePurchase/App Installer как UWP не ходит в сеть, а обычные Win32-команды ходят;
- ранее включался локальный VPN/proxy-клиент.

Сначала чтение:

```powershell
netsh winhttp show proxy
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings" |
  Select-Object ProxyEnable,ProxyServer,AutoConfigURL
Get-ChildItem Env: | Where-Object Name -match "proxy"
CheckNetIsolation.exe LoopbackExempt -s
```

Добавляйте exemptions только при доказанном proxy/VPN признаке:

```powershell
CheckNetIsolation.exe LoopbackExempt -a -n=Microsoft.WindowsStore_8wekyb3d8bbwe
CheckNetIsolation.exe LoopbackExempt -a -n=Microsoft.StorePurchaseApp_8wekyb3d8bbwe
CheckNetIsolation.exe LoopbackExempt -a -n=Microsoft.DesktopAppInstaller_8wekyb3d8bbwe
```

Если proxy/VPN признаков нет, не трогайте loopback: это отвлекающий и потенциально вредный обход.

### 7. Установить И Проверить

Только после шагов выше:

```powershell
winget install --id STORE_ID --source msstore --accept-source-agreements --accept-package-agreements
```

Если нужен GUI Store:

```powershell
Start-Process "ms-windows-store://pdp/?productid=STORE_ID"
```

Контроль:

```powershell
winget list --id STORE_ID --source msstore
Get-AppxPackage | Where-Object { $_.PackageFamilyName -like "*EXPECTED_PART*" -or $_.Name -like "*EXPECTED_PART*" }
```

В финале назовите одну из развязок:

- установлен пакет и проверка это подтвердила;
- установка заблокирована аккаунтом/лицензией/регионом/политикой;
- неверный Store ID или publisher;
- сломан App Installer/source;
- Store-служба была остановлена и восстановлена;
- proxy/VPN требует loopback exemption;
- задача не из этого skill, потому что Windows не показывает `IPv4Connectivity = Internet`.

## Границы

Не используйте skill для:

- Windows/NCSI "No internet", если `IPv4Connectivity` не `Internet`;
- полностью мертвой сети;
- обхода блокировок, региона, возраста, оплаты, лицензии, корпоративных политик или Store-ограничений;
- установки приложений не из Microsoft Store/msstore source;
- починки Codex CLI, GitHub, npm, pip или обычного terminal networking;
- удаления Store/App Installer пакетов как первой меры;
- массовой правки DNS/proxy/firewall/hosts;
- blind-fix рецептов без `winget show`, WAM/App Installer/services evidence.

Сохраняйте приватность: не коммитьте Microsoft account, email, tenant IDs, raw `dsregcmd` целиком, Store purchase details, proxy credentials и локальные пути.

## Опрос После Использования

После финальной развязки - установлен пакет, доказанный блокер или явная передача в другой triage - задайте короткий опрос один раз. Не спрашивайте посреди установки и не повторяйте, если пользователь уже ответил "пропустить" в этой сессии.

```text
Опрос по skill:
1. Что в этом использовании windows-store-app-install-triage было полезно?
2. Что стоит доработать в skill или его формате?
Можно ответить коротко или написать "пропустить".
```

Если пользователь ответил, сохраните санированную карточку в `~/.codex/skill-runs/windows-store-app-install-triage/usage-feedback.jsonl` — лучше через bundled script:

```bash
python3 scripts/log_usage_feedback.py --liked "..." --improve "..." --outcome "..."
```

Script перед записью редактирует приватные пути, контакты и token-like строки и сохраняет в JSONL `redaction_applied` и `redaction_types`. Если запись невозможна из-за sandbox, прав или отсутствия tools, не делайте вид, что лог сохранён: скажите об этом и покажите короткую JSONL-карточку для ручного сохранения. Raw-ответы, контакты, пути и секреты не коммитить.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/<skill-name>/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.
