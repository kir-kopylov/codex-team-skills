# Domain Playbook

## Что Нельзя Потерять

- Целевой стек: Windows + PowerShell + Git for Windows + Git Credential Manager + GitLab over HTTPS.
- Различение состояний `TOKEN_CREATED`, `LOCAL_CREDENTIAL_READY` и `REMOTE_READ_VERIFIED`.
- GitLab показывает значение Personal Access Token один раз сразу после создания; после ухода со страницы его надо заменить новым.
- Текущий путь UI: avatar → `Edit profile` → `Access` → `Personal access tokens`. Если интерфейс изменился, нужен свежий экран, а не угаданная кнопка.
- `read_repository` даёт чтение Git over HTTP. `write_repository` даёт чтение и запись Git over HTTP и не поддерживает API-аутентификацию.
- PAT используется как password; username должен быть непустым.
- Git по умолчанию не различает path для HTTP credentials. `credential.useHttpPath=true` включает path-specific поведение; host-wide workflow должен выявлять это значение.
- Значение PAT нельзя помещать в URL: URL попадает в history, process list, логи и диагностический вывод.
- GCM `store/get/erase --no-ui` принимает credential protocol на stdin. Проверка `get` должна поглощать secret и выводить только наличие полей.
- Публичный repo не доказывает авторизацию. Для server-side проверки нужен приватный repo, который точно доступен пользователю.

## Что Надо Обезличить

- Значения PAT, пароли, recovery material и любые token-like строки.
- Реальные GitLab usernames, namespace, account nickname и private project names.
- Точные URL приватных репозиториев и self-managed GitLab hosts команды.
- Личные абсолютные пути, PowerShell history, raw terminal logs и screenshots.
- Реальные даты истечения, IP-адреса использования токена и внутренние project/group IDs.

## Interface Mechanics

### GitLab

- На странице создания выбирайте только права под фактическую Git-задачу: `read_repository` для чтения; `write_repository` для pull/push.
- Не требуйте одновременно оба scope: `write_repository` уже включает чтение. Оба отмеченных scope допустимы, но избыточны.
- `api`, `read_api` и `read_user` относятся к другой задаче. Их отсутствие нельзя диагностировать как отказ Git over HTTPS.
- Сразу после `Generate token` пользователь сохраняет значение вне чата и переходит к интерактивному PowerShell prompt.

### Git Credential Manager

- Git for Windows обычно поставляет GCM; факт проверяется `git credential-manager --version`, а не предположением по версии Git.
- Активный helper проверяется `git config --show-origin --get-all credential.helper`.
- При наличии GCM, но отсутствии helper, используется `git credential-manager configure`.
- Bundled script напрямую вызывает GCM, чтобы credential не попал в аргументы и случайный plaintext helper.
- `-Replace` вызывает host-level erase до store. Применять только когда подтверждена одна учётная запись на host.
- `-HostWide` ставит `credential.https://<host>.useHttpPath=false`; без этого флага script не меняет данную настройку.

### Лестница Проверки

1. GCM установлен и настроен — предпосылка.
2. `store` завершился без ошибки, затем `get --no-ui` вернул непустые username/password — `LOCAL_CREDENTIAL_READY`.
3. `git ls-remote` точного приватного repo прошёл — `REMOTE_READ_VERIFIED`.
4. Право записи подтверждается только запрошенной пользователем операцией push в конкретном repo; отдельный тестовый push не делать.

## Recovery And Edge Cases

- Token создан, но не скопирован: revoke и создать новый; значение не восстанавливается из списка.
- GCM возвращает старый credential: bundled script с `-Replace`, затем повторная локальная проверка.
- `/api/v4/user` возвращает `403`: если у PAT только repository scopes, остановить API-ветку как нерелевантную.
- Публичный `git ls-remote` успешен с неверным token: это анонимное чтение, не auth proof.
- `project not found or you don't have permission`: сначала сверить точный URL; сообщение объединяет несколько причин и не доказывает дефект token.
- Два аккаунта на одном host: не применять host-wide erase/store; передать в отдельный multi-account workflow.
- Self-managed GitLab: подставлять только подтверждённый host; не переносить `gitlab.com` автоматически.
- GCM отсутствует: восстановить Git for Windows/GCM; не переключаться на `credential.helper=store`, который хранит secret в открытом виде.

## Official References

- GitLab Personal Access Tokens: https://docs.gitlab.com/user/profile/personal_access_tokens/
- GitLab access token scopes: https://docs.gitlab.com/security/tokens/access_token_scopes/
- Git credential contexts and `useHttpPath`: https://git-scm.com/docs/gitcredentials
- Git credential `fill/approve/reject`: https://git-scm.com/docs/git-credential
- Git Credential Manager: https://github.com/git-ecosystem/git-credential-manager
- Windows `cmdkey`: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmdkey
