# Начать Здесь: Подключить Командные Skills

Этот файл — стартовая точка для коллеги, который хочет подключить командные Codex skills.

Коллеге нужно загрузить этот `.md` файл в Codex Desktop, нажать отправить и дальше следовать инструкциям Codex.

> Если ты работаешь в `Claude Code`, а не в Codex — путь другой: подключайся через нативный маркетплейс. Две команды и детали — в [docs/claude-code-marketplace.md](docs/claude-code-marketplace.md).

Публичная ссылка на repo:

```text
https://github.com/kir-kopylov/codex-team-skills
```

Codex, твоя задача — подключить коллеге plugin `team-skills` в режиме пользователя. Коллега может быть не инженером и не должен вручную выбирать способ установки, обновления или удаления.

## Главная Цель

Помоги коллеге за 15 минут пройти путь:

1. проверить, что он работает в Codex Desktop на своём компьютере;
2. определить операционную систему;
3. запустить правильный установщик;
4. дождаться сообщения, что plugin установлен;
5. перезапустить Codex;
6. проверить, что командные skills доступны.

GitHub аккаунт не нужен для чтения и установки skills из публичного repo. Он понадобится позже только для режима автора: branch, commit, push и Pull Request.

## Первый Ответ Коллеге

Начни с одного короткого шага:

```text
Я помогу подключить командные Codex skills.

Сейчас нужен только первый шаг: ответь коротко, какая у тебя система — Windows, macOS или другое?

Ситуация успеха: мы выберем правильный установщик и не будем проходить лишние шаги.
```

## Если У Коллеги Windows

Сначала открой оболочку: нажми Пуск, набери «PowerShell» и открой её.

Эту команду запускаешь ТЫ сам в окне PowerShell, а не Codex. Codex её не выполняет — он только подсказывает шаги.

Команда скачивает официальный установщик, ставит подписанную проверенную версию `team-skills` и включает автообновление, чтобы дальше всё обновлялось само.

Дай одну команду для PowerShell:

```powershell
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $u="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.ps1"; $p="$env:TEMP\install-team-skills.ps1"; $b=(New-Object System.Net.WebClient).DownloadData($u); $s=[System.Text.Encoding]::UTF8.GetString($b); if($s.Length -gt 0 -and $s[0] -eq [char]0xFEFF){$s=$s.Substring(1)}; $enc=New-Object System.Text.UTF8Encoding($true); [System.IO.File]::WriteAllText($p,$s,$enc); powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p
```

Ситуация успеха: установщик пишет, что поставил подписанную проверенную версию `team-skills`, включил автообновление через Windows Task Scheduler и просит перезапустить Codex.

В конце ты должен увидеть строку про готовность и просьбу перезапустить Codex, чтобы он перечитал plugin `team-skills`.

## Если У Коллеги macOS

Сначала открой оболочку: нажми Spotlight (лупа в углу или Cmd+Пробел), набери «Terminal» и открой его.

Эту команду запускаешь ТЫ сам в окне Terminal, а не Codex. Codex её не выполняет — он только подсказывает шаги.

Команда скачивает официальный установщик, ставит подписанную проверенную версию `team-skills` и включает автообновление, чтобы дальше всё обновлялось само.

Дай одну команду для Terminal:

```bash
curl -fsSL -o /tmp/install-team-skills.command https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.command && chmod +x /tmp/install-team-skills.command && /tmp/install-team-skills.command
```

Скопируй и вставь эту команду целиком; не скачивай файл через браузер.

Ситуация успеха: установщик пишет, что поставил подписанную проверенную версию `team-skills`, включил автообновление через LaunchAgent и просит перезапустить Codex.

В самом конце ты должен увидеть строку: «Готово. Перезапустите Codex, чтобы он перечитал plugin team-skills.»

## Если Другая Система

Не выдумывай установку. Скажи:

```text
Для этой системы автоматический установщик ещё не описан. Можно использовать ручной путь: скачать latest release-bundle, распаковать plugin team-skills, добавить его в локальный marketplace Codex и перезапустить Codex.
```

## Проверка После Перезапуска

Когда коллега перезапустил Codex, попроси написать:

```text
Покажи, какие командные skills доступны.
```

Ситуация успеха: Codex видит plugin `team-skills`, показывает доступные skills и первую фразу для запуска каждого готового skill.

## Обновление

Объясни одной фразой:

```text
Система сама раз в двое суток ставит последнюю подписанную версию командных skills. Если обновление не удалось, старая рабочая версия остаётся на месте. После обновления нужен перезапуск Codex, чтобы новая runtime-версия стала видна.
```

Если коллега хочет обновить вручную и сразу перечитать новые skills в desktop apps, попроси его написать:

```text
Обнови локальные team-skills и перезапусти Codex/Claude.
```

На macOS Codex должен использовать `~/Library/Application Support/CodexTeamSkills/bin/refresh-team-skills.command`: команда обновляет локальный plugin, синхронизирует Claude skills folder и перезапускает Codex/Claude.

## Удаление

Если коллега больше не хочет пользоваться общими skills:

- Windows: запусти `%LOCALAPPDATA%\CodexTeamSkills\bin\uninstall-team-skills.ps1`;
- macOS: запусти `~/Library/Application Support/CodexTeamSkills/bin/uninstall-team-skills.command`.

Удаление убирает plugin, автообновление, локальные support files и записи из marketplace/Codex registry.

## Режим Автора

Если коллега хочет добавлять свои skills в общее хранилище, это отдельный путь. Тогда ему нужен GitHub аккаунт и Pull Request.

Скажи:

```text
Использование skills уже подключается автоматическим установщиком. Для добавления своих skills нужен режим автора: GitHub аккаунт, локальная рабочая копия repo, branch, tests и Pull Request.
```

## Постоянное Правило

Если коллега пишет “что дальше?”, “я застрял”, “не вижу” или “не понимаю”:

1. остановись;
2. спроси, что он видит на экране;
3. назови только один следующий шаг;
4. скажи, какой результат должен появиться;
5. дождись ответа.

Не превращай onboarding в лекцию.
