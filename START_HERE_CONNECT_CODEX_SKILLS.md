# Начать Здесь: Подключить Командные Skills

Этот файл — стартовая точка для коллеги, который хочет подключить командные Codex skills.

Коллеге нужно загрузить этот `.md` файл в Codex Desktop, нажать отправить и дальше следовать инструкциям Codex.

> Если ты работаешь в `Claude Code`, а не в Codex — путь другой: подключайся через нативный маркетплейс. Две команды и детали — в [docs/claude-code-marketplace.md](docs/claude-code-marketplace.md).

Публичная ссылка на repo:

```text
https://github.com/kir-kopylov/codex-team-skills
```

Codex, твоя задача — подключить коллеге plugin `team-skills` в режиме пользователя. Коллега может быть не инженером и не должен вручную выбирать способ установки.

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

Команда скачивает одноразовый установщик из последнего проверенного GitHub Release и ставит `team-skills`.

Дай одну команду для PowerShell:

```powershell
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $u="https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.ps1"; $p="$env:TEMP\install-team-skills.ps1"; $b=(New-Object System.Net.WebClient).DownloadData($u); $s=[System.Text.Encoding]::UTF8.GetString($b); if($s.Length -gt 0 -and $s[0] -eq [char]0xFEFF){$s=$s.Substring(1)}; $enc=New-Object System.Text.UTF8Encoding($true); [System.IO.File]::WriteAllText($p,$s,$enc); powershell.exe -NoProfile -ExecutionPolicy Bypass -File $p
```

Ситуация успеха: установщик пишет, какой release `team-skills` установлен, и просит перезапустить Codex.

В конце ты должен увидеть строку про готовность и просьбу перезапустить Codex, чтобы он перечитал plugin `team-skills`.

## Если У Коллеги macOS

Сначала открой оболочку: нажми Spotlight (лупа в углу или Cmd+Пробел), набери «Terminal» и открой его.

Сначала выполни `python3 --version`. Нужен Python 3.11 или новее; macOS не гарантирует, что он уже установлен. Если версия ниже или команда не найдена, остановись и помоги коллеге отдельно установить актуальный Python — не обещай, что основной installer сработает без него.

Эту команду запускаешь ТЫ сам в окне Terminal, а не Codex. Codex её не выполняет — он только подсказывает шаги.

Команда скачивает одноразовый установщик из последнего проверенного GitHub Release и ставит `team-skills`.

Дай одну команду для Terminal:

```bash
curl -fsSL -o /tmp/install-team-skills.command https://github.com/kir-kopylov/codex-team-skills/releases/latest/download/install-team-skills.command && chmod +x /tmp/install-team-skills.command && /tmp/install-team-skills.command
```

Скопируй и вставь эту команду целиком; не скачивай файл через браузер.

Ситуация успеха: установщик пишет, какой release `team-skills` установлен, и просит перезапустить Codex.

В самом конце ты должен увидеть просьбу перезапустить Codex, чтобы он перечитал plugin `team-skills`.

## Если Другая Система

Не выдумывай установку. Скажи:

```text
Для этой системы установщик ещё не описан. Не придумывай команды: остановись и передай задачу maintainer-у.
```

## Проверка После Перезапуска

Когда коллега перезапустил Codex, попроси написать:

```text
Покажи, какие командные skills доступны.
```

Ситуация успеха: Codex видит plugin `team-skills`, показывает доступные skills и первую фразу для запуска каждого готового skill.

## Обновление

Если коллега хочет получить новые skills, объясни одной фразой:

```text
Повторно запусти ту же команду установки для своей системы, затем перезапусти Codex.
```

Автообновления и отдельной update-команды нет. Для Claude Code действует отдельный нативный marketplace workflow из инструкции выше.

## Удаление

Если коллега больше не хочет пользоваться общими skills, скачай одноразовый uninstaller из последнего Release и запусти его:

- Windows: `uninstall-team-skills.ps1`;
- macOS: `uninstall-team-skills.command`.

Если uninstaller сообщает о старом автообновлении, сначала выполни официальный legacy cleanup из [admin-onboarding-guide.md](admin-onboarding-guide.md). Uninstaller не принимает решений за cleanup и не хранится на машине после запуска.

## Режим Автора

Если коллега хочет добавлять свои skills в общее хранилище, это отдельный путь. Тогда ему нужен GitHub аккаунт и Pull Request.

Скажи:

```text
Использование skills подключается одной командой установки. Для добавления своих skills нужен режим автора: GitHub аккаунт, локальная рабочая копия repo, branch, tests и Pull Request.
```

## Постоянное Правило

Если коллега пишет “что дальше?”, “я застрял”, “не вижу” или “не понимаю”:

1. остановись;
2. спроси, что он видит на экране;
3. назови только один следующий шаг;
4. скажи, какой результат должен появиться;
5. дождись ответа.

Не превращай onboarding в лекцию.
