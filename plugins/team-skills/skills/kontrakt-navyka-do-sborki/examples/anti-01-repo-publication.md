# Запрос На Публикацию В Repo

## Вход

Пользователь пишет: "Добавь новый skill в командный repo, создай `SKILL.md`, `skill.yaml`, examples, catalog row, запусти tests и подготовь PR."

## Ожидаемое Поведение

Codex не использует `kontrakt-navyka-do-sborki` как основной workflow. Он передает задачу в `dobavlenie-navyka-v-biblioteku`, потому что пользователь просит repo packaging, examples, catalog, tests и Pull Request.

Если контракта будущего skill еще нет, Codex может сначала коротко сформулировать недостающие элементы, но выполнение изменений в repo остается зоной `dobavlenie-navyka-v-biblioteku`.

## Нельзя

Нельзя отвечать только методологическим шаблоном и игнорировать явную просьбу создать repo files. Нельзя смешивать два режима так, чтобы `kontrakt-navyka-do-sborki` сам открывал PR или обещал team-ready без проверок.
