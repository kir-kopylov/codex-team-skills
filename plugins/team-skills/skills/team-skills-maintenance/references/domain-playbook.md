# Domain Playbook

## Что Нельзя Потерять

- Одна пользовательская фраза разрешает весь цикл; дополнительные согласия на заранее перечисленные шаги не нужны.
- Канонический источник всегда `kir-kopylov/codex-team-skills`, ref `main`, marketplace `codex-team-skills`, plugin `team-skills@codex-team-skills`.
- Marketplace сначала обновляется или подключается, затем plugin обязательно устанавливается повторно.
- Дубль определяется точным совпадением трёх имён: папка личного навыка, frontmatter `name` и имя в новом каноническом plugin.
- Очистка означает восстанавливаемое атомарное перемещение с manifest и SHA-256, а не удаление.
- Уникальные, неоднозначные, repo-scoped и системные навыки остаются неизменными.
- Установка на диске и видимость в новой сессии — разные состояния. Финал только `LIVE_VERIFIED`.
- Отсутствующий в сессии skill не устанавливает сам себя: первичный вход идёт через `START_HERE_CONNECT_CODEX_SKILLS.md` или процедуру переподключения.
- При отсутствующем plugin точные legacy-признаки проверяются до `marketplace add`; новая установка не должна смешиваться со старым состоянием.

## Что Надо Обезличить

- В публичный ответ и repo не переносить абсолютный домашний путь, имена профилей, содержимое личных навыков, токены и raw CLI logs.
- В локальном manifest допустим исходный путь относительно проверенного личного root; наружу выводить только имя навыка и статус.
- Ошибку CLI сокращать до команды, exit code и безопасного фрагмента без environment dump.
- Приватные exception/feedback logs хранить только в локальном `~/.codex/skill-runs/team-skills-maintenance/`.

## Interface Mechanics

1. `codex --version`, `codex plugin --help` и `codex plugin list --json` — обязательный preflight. Наличие wrapper-файла само по себе ничего не доказывает.
2. Для существующего канонического plugin: `codex plugin marketplace upgrade codex-team-skills --json`, затем `codex plugin add team-skills@codex-team-skills --json`.
3. Для отсутствующего plugin до первой установки проверяются точные следы из `START_HERE_RECONNECT_CODEX_SKILLS.md`: старый каталог, managed config block, cache/marketplace-файл и платформенные updater-объекты.
4. Если след найден, чистая установка запрещена: сначала процедура reconnect с точной проверкой владения. Только чистое состояние допускает `codex plugin marketplace add kir-kopylov/codex-team-skills --ref main --json`, затем `plugin add`.
5. Источник, `installedPath`, version и enabled-state берутся из JSON-ответов текущего запуска, а не из памяти или предполагаемой структуры cache.
6. Личный root должен быть наблюдаемым пользовательским корнем навыков. Не расширять поиск на проектные `.agents/skills` и чужие plugin-каталоги.
7. Карантин создаётся внутри локального Codex home отдельным UTC-каталогом запуска. Перемещение допустимо только атомарным rename без перезаписи.
8. Перед перезапуском пишется `pending.json`. После него проверяется список навыков именно новой сессии, а не только CLI или файловая система.

## Recovery And Edge Cases

- `ENOENT`, отсутствующая группа plugin, старая версия или невалидный JSON: `BLOCKED_CODEX_CLI`, без обходной доставки и без очистки дублей.
- Marketplace с другим source: остановиться; не переподключать его молча.
- Plugin отсутствует, но есть legacy-признак: `LEGACY_TRANSITION_REQUIRED`; недоказанное владение даёт `BLOCKED_LEGACY_OWNERSHIP`, без clean add.
- Candidate symlink, path escape, malformed frontmatter или unknown root: `BLOCKED_DUPLICATE_REVIEW`, кандидат остаётся на месте.
- Cross-filesystem move или существующий target карантина: остановиться до изменения кандидата.
- Безопасный restart/resume не подтверждён: сохранить `RESTART_PENDING`, вернуть `BLOCKED_RESTART_UNAVAILABLE` и одно ручное действие.
- Для восстановления прочитать manifest, убедиться, что каноническая копия не будет перезаписана, и атомарно вернуть ровно выбранный каталог в его исходный личный root. Восстановление — отдельная явная задача пользователя.
- Повторный запуск идемпотентен: существующий карантин не удаляется и не переносится снова; новый запуск получает новый timestamp и собственный manifest.
