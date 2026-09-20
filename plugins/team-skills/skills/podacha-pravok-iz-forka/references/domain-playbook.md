# Domain Playbook

Предметная область: подача правок в командный repo через fork и Pull Request на GitHub.

## Что Нельзя Потерять

Сохраняйте эти понятия и проверки:

- `upstream` — исходный repo, куда пользователь хочет предложить изменения;
- `fork` — копия repo в аккаунте пользователя;
- `branch` — отдельная ветка с изменениями, не `main`;
- `Pull Request` / `PR` — запрос из fork/branch в upstream/base branch;
- `base` — куда вливать, обычно `kir-kopylov/codex-team-skills:main`;
- `head` — откуда вливать, обычно `<user>/codex-team-skills:agent/<task>`;
- кнопки GitHub: `Create fork`, `Contribute`, `Compare & pull request`, `New pull request`, `compare across forks`, `Create pull request`;
- флажок `Allow edits by maintainers` / `maintainer_can_modify`, если доступен;
- `review request` — более надежное уведомление владельцу repo, чем просто создание fork;
- статусы `draft`, `open`, `mergeable`, `merged`, `closed`;
- Actions status `action_required` для PR из fork — maintainer должен разрешить workflow.

## Что Надо Обезличить

Не переносите в публичный repo и examples:

- токены, cookies, PAT, OAuth-коды, SSH keys;
- raw-скриншоты GitHub с приватными вкладками, email, локальными путями или незамазанными приватными repo;
- личные пути Windows/macOS/Linux;
- реальные клиентские выгрузки, адреса квартир, ФИО, телефоны, платежные данные;
- полный raw transcript чата;
- приватные названия организаций, если они не нужны для публичного skill.

Публичные GitHub handles можно использовать только когда они уже подтверждены контекстом и нужны для ownership, например `@nadya90simarzina` как owner skill.

## Interface Mechanics

Быстрая диагностика по скриншоту GitHub

- Экран `Create a new fork`: пользователь еще не сделал PR. Следующий шаг — `Create fork`.
- Fork repo открыт и пишет `forked from ...`: fork создан, но PR может еще не существовать. Следующий шаг — `Contribute` или `Compare & pull request`.
- Страница `Pull requests` без PR пользователя: нужен `New pull request` и `compare across forks`.
- Страница compare: проверьте, что base — upstream `main`, head — fork пользователя и правильная branch.
- Страница PR с номером `#...`: PR уже существует. Дайте ссылку, проверьте reviewers/checks и не создавайте дубль.

## Сообщение Владельцу Repo

Если уведомление не гарантировано, дайте пользователю короткий текст:

```text
Я открыла PR с моим skill: <PR URL>. Посмотрите, пожалуйста, можно ли принять его в командный repo. Авторство указано на меня: <owner/author>.
```

Если есть GitHub-инструмент review request, сначала попробуйте запросить review у владельца repo, затем все равно дайте прямую ссылку.
## Recovery And Edge Cases

- Fork есть, PR нет: fork сам по себе не создаёт review-событие у maintainer-а. Проведите пользователя через `Contribute` или `compare across forks` и только после появления URL вида `https://github.com/<owner>/<repo>/pull/<number>` говорите, что PR создан.
- Кнопки `Compare & pull request` нет: откройте upstream repo, вкладку `Pull requests`, затем `New pull request` и `compare across forks`.
- На странице сравнения не тот `base` или `head`: перевыберите upstream `main` как base и ветку fork как head, не создавая новый fork.
- Уже открыт PR с тем же scope: обновите существующий PR новым push в ту же head branch, дубль не создавайте.
- Нет прав на запись в upstream: не имитируйте публикацию, честно скажите об этом и ведите пользователя по UI своими шагами.
- Actions показывает `action_required`: это не падение тестов, а правило repo для PR из fork — workflow должен разрешить maintainer. После разрешения проверьте checks заново.
- Владелец repo не заметил PR: он мог не быть reviewer, mentioned или подписан на repo. Запросите review, иначе дайте прямую ссылку и короткий текст для отправки.
- После каждого push в PR заново проверяйте checks, `mergeable` и новые review comments: прошлый статус уже недействителен.
- Инструменты GitHub недоступны или упали: выдайте ручной маршрут в интерфейсе и отдельной строкой скажите, что PR ещё не создан.
