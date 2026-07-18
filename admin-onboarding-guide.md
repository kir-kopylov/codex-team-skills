# Гид Для Организатора Onboarding

Эта инструкция для человека, который помогает коллегам подключиться к общему хранилищу Codex skills.

Коллеге по-прежнему отправляйте один файл: [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md). Разница в том, что обычный пользователь больше не проходит ручное скачивание repo и не устанавливает plugin через отдельное desktop-приложение.

## Два Режима

**User mode** — для коллег, которые только пользуются skills. Им нужен Codex Desktop и один установщик; на macOS дополнительно нужен Python 3.11 или новее, которого система по умолчанию не гарантирует. GitHub аккаунт, локальная копия repo и Pull Request не нужны.

**Author mode** — для коллег, которые хотят добавить свои skills в общее хранилище. Им нужен GitHub аккаунт, локальная рабочая копия repo, branch, tests и Pull Request.

## User Mode: Что Делает Коллега

1. Открывает Codex Desktop.
2. Загружает [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md).
3. Отвечает, какая у него система: Windows или macOS.
4. Запускает одну команду, которую даст Codex.
5. Перезапускает Codex.
6. Проверяет фразой: `Покажи, какие командные skills доступны.`

Ситуация успеха: plugin `team-skills` установлен, коллега видит доступные командные skills.

## Что Делает Установщик

Установщик скачивает не сырой `main`, а последний подписанный release:

- `latest.json` — подписанный pointer на последний проверенный подписанный release (неизменяемый тег не гарантируется платформой);
- `manifest.json` — подписанная schema с `product_version`, `runtime_version`, `release_id`, commit, channel и checksum assets;
- `team-skills-bundle.zip` — plugin `team-skills`;
- служебные файлы для установки и удаления.

Перед заменой активного plugin установщик проверяет подпись metadata, checksum assets, распаковывает bundle во временную папку, проверяет `.codex-plugin/plugin.json`, регистрирует local marketplace в Codex config и только потом заменяет локальную версию. После успешной замены установщик инвалидирует snapshot `~/.codex/plugins/cache/codex-team-skills`, чтобы перезапуск Codex перечитал свежий plugin.

## Обновление

Автообновления нет. Чтобы получить новые skills, коллега повторно запускает ту же команду установки для своей системы и перезапускает Codex.

После публикации этой версии уже подключённые коллеги должны один раз повторно запустить installer: он удалит старую Scheduled Task или LaunchAgent и старые updater-файлы. Пока человек этого не сделал, ранее установленная фоновая задача остаётся на его компьютере.

Если интернет недоступен, подпись невалидна или bundle повреждён, установщик завершается с ошибкой и не должен принимать непроверенный bundle.

## Release Signing

Публикация release после merge требует GitHub Actions secret `TEAM_SKILLS_SIGNING_KEY_PEM`. Он должен содержать приватный ключ, соответствующий публичному ключу `installer/team-skills-public-key.pem`. Без этого CI должен падать на publish-step, потому что installer не должен принимать unsigned release.

Честно про bus-factor: приватный ключ хранится только офлайн и как GitHub Actions secret `TEAM_SKILLS_SIGNING_KEY_PEM`, и сейчас до него дотягивается только владелец repo. Это единая точка отказа: если ключ потерян или скомпрометирован, новые подписанные release выпускать некем. Восстановление — это смена доверенного якоря, а не починка старого ключа.

Ротация не должна зависеть от ещё не опубликованного release:

1. Офлайн сгенерируйте новую пару ключей. Приватный ключ не копируйте в repo.
2. В одном PR замените `installer/team-skills-public-key.pem`, значение `EXPECTED_PUBLIC_KEY_SHA256` в macOS installer, `$PinnedPublicKeyModulusBase64` и `$PinnedPublicKeyExponentBase64` в Windows installer.
3. До merge этим же PR соберите candidate metadata штатным `scripts/build_release_bundle.py`. В офлайн-среде подпишите полученный `latest.json` новым приватным ключом той же командой, что использует publish job:

   ```bash
   python scripts/build_release_bundle.py --dist <candidate-dist> --commit <candidate-commit> --run-number 0 --run-attempt 0
   openssl dgst -sha256 -sign <new-private-key.pem> -out tests/fixtures/windows-signature/latest.json.sig <candidate-dist>/latest.json
   ```

   Сам `latest.json` скопируйте из `<candidate-dist>` в `tests/fixtures/windows-signature/latest.json`. Эта публичная пара нужна для проверки нового ключа до merge; приватный ключ в fixture не входит.
4. PEM, macOS pin, встроенные RSA-параметры и fixture должны меняться одним PR. Полный suite и Windows PowerShell 5.1 smoke обязаны доказать соответствие и отклонить изменённый байт.
5. Только после зелёного PR замените GitHub Actions secret `TEAM_SKILLS_SIGNING_KEY_PEM`, сразу выполните merge и дождитесь свежего подписанного release. После публикации можно заменить candidate fixture публичной парой этого release отдельным PR без смены ключа.

Коллеги подхватят новый якорь доверия, заново запустив установщик; до этого у них остаётся ранее установленная версия. Если подпись невалидна, installer должен завершиться с ошибкой и не принимать новый bundle.

## Команды Поддержки

Для установки или обновления повторно используйте OS-specific команду из `START_HERE_CONNECT_CODEX_SKILLS.md`.

Для удаления:

- Windows: `%LOCALAPPDATA%\CodexTeamSkills\bin\uninstall-team-skills.ps1`;
- macOS: `~/Library/Application Support/CodexTeamSkills/bin/uninstall-team-skills.command`.

## Что Отправить Коллеге

Отправьте файл [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md) и короткий текст:

```text
Загрузи этот .md файл в Codex Desktop, нажми отправить и следуй инструкциям.

Codex определит твою систему и даст одну команду для установки командных skills.
```

## Author Mode: Если Коллега Хочет Добавлять Skills

Только для авторов нужен GitHub workflow:

1. GitHub аккаунт.
2. Локальная рабочая копия repo `codex-team-skills`.
3. Branch для изменения.
4. Черновик через `python scripts/new_skill.py`.
5. Заполненные `SKILL.md`, `skill.yaml`, `examples/`.
6. `python -m pytest`.
7. Pull Request.

Ситуация успеха: Pull Request создан, CI проходит, ревьюер видит цель skill, аудиторию, ограничения и примеры.

## Короткое Объяснение Для Коллег

```text
Чтобы получить новые командные skills, повторно запусти ту же команду установки и перезапусти Codex.
```
