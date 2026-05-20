---
name: team-skills-maintenance
description: Используйте этот skill, когда пользователь хочет проверить статус командных Codex skills, обновить team-skills вручную, удалить общие skills, понять автообновление или восстановить установку после сбоя. Skill должен срабатывать на обычные фразы вроде "проверь статус командных skills", "обнови team-skills сейчас", "удали командные skills", "почему не появились новые скиллы", "проверь автообновление team-skills".
---

# Team Skills Maintenance

## Обзор

Этот skill помогает обслуживать пользовательскую установку plugin `team-skills`: проверить статус, запустить обновление вручную, объяснить автообновление или удалить установку.

Работайте в режиме пользователя. Не переводите человека в author workflow, если он не просит добавлять свои skills в repo.

## Быстрый Роутер

- "проверь статус" -> определить ОС и запустить status script;
- "обнови сейчас" -> определить ОС и запустить update script;
- "удали командные skills" -> определить ОС и запустить uninstall script после явного подтверждения пользователя;
- "новые skills не появились" -> проверить status, last_success_at, перезапуск Codex и только потом обновлять вручную;
- "хочу добавить свой skill" -> передать в author workflow через `add-team-skill`.

## Команды

Windows:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\team-skills-status.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\update-team-skills.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$env:LOCALAPPDATA\CodexTeamSkills\bin\uninstall-team-skills.ps1"
```

macOS:

```bash
"$HOME/Library/Application Support/CodexTeamSkills/bin/team-skills-status.command"
"$HOME/Library/Application Support/CodexTeamSkills/bin/update-team-skills.sh"
"$HOME/Library/Application Support/CodexTeamSkills/bin/uninstall-team-skills.command"
```

## Границы

Не обещайте, что новый skill появится без перезапуска Codex: после установки или обновления Codex может перечитать plugin только после restart.

Не чините author workflow через uninstall. Если пользователь хочет публиковать skills, нужен GitHub аккаунт, branch, tests и Pull Request.

## Definition Of Done

Пользователь понимает текущий статус установки, последнюю успешную версию, состояние автообновления и следующий безопасный шаг: restart Codex, update now, uninstall или author workflow.
