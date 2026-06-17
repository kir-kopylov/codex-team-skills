---
name: team-skills-maintenance
description: Используйте этот skill, когда пользователь хочет проверить статус командных Codex skills, обновить team-skills вручную, обновить локальные team-skills и перезапустить Codex/Claude, удалить общие skills, понять автообновление или восстановить установку после сбоя. Skill должен срабатывать на обычные фразы вроде "проверь статус командных skills", "обнови team-skills сейчас", "обнови локальные team-skills и перезапусти Codex/Claude", "удали командные skills", "почему не появились новые скиллы", "проверь автообновление team-skills".
---

# Team Skills Maintenance

## Согласие На Запуск

Явный вызов — slash-команда, имя skill или первая фраза из каталога — выполняйте сразу, без вопроса. При автосрабатывании на смысловое сходство сначала спросите одной строкой: «Задача похожа на team skill `team-skills-maintenance` — проверяет, обновляет и чинит установку командных skills. Применить или решить без него?» — и ждите ответа. При отказе выйдите из skill молча: решите задачу с нуля и больше не упоминайте skill.

## Обзор

Этот skill помогает обслуживать пользовательскую установку plugin `team-skills`: проверить статус, запустить обновление вручную, объяснить автообновление или удалить установку.

Работайте в режиме пользователя. Не переводите человека в author workflow, если он не просит добавлять свои skills в repo.

## Быстрый Роутер

- "проверь статус" -> определить ОС и запустить status script;
- "обнови сейчас" -> определить ОС и запустить update script;
- "обнови локальные team-skills и перезапусти Codex/Claude" -> на macOS запустить refresh script, который делает update, Claude sync и restart desktop apps;
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
"$HOME/Library/Application Support/CodexTeamSkills/bin/refresh-team-skills.command"
"$HOME/Library/Application Support/CodexTeamSkills/bin/uninstall-team-skills.command"
```

## Границы

Не обещайте, что новый skill появится без перезапуска Codex: после установки или обновления Codex может перечитать plugin только после restart. Если пользователь прямо просит обновить локальные team-skills и перезапустить Codex/Claude, используйте `refresh-team-skills.command`, а не список ручных команд.

Не чините author workflow через uninstall. Если пользователь хочет публиковать skills, нужен GitHub аккаунт, branch, tests и Pull Request.

## Логирование Сбоев

Перед выполнением прочитайте локальный `known-exceptions.yaml` как список уже известных случаев и применяйте подходящее `do_next_time` без нового поиска.

Если пользователь поправил skill, tool/API/browser упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, запишите приватную карточку в `~/.codex/skill-runs/<skill-name>/exception-log.jsonl`.

Пишите факты: что skill хотел сделать, что сделал, где сломался, какая предпосылка была ложной и что сделать в следующий раз. Если поле неизвестно, пишите `unknown`. Raw logs не коммитить.

## Definition Of Done

Пользователь понимает текущий статус установки, последнюю успешную версию, состояние автообновления и следующий безопасный шаг: refresh and restart, update now, restart Codex, uninstall или author workflow.
