# Codex Team Skills Registry

Это командное хранилище Codex skills. Оно упаковано как один локальный plugin: `team-skills`. Репозиторий публично читаемый, но не open-source: все права защищены, внутреннее использование командой. Условия — в файле [LICENSE](LICENSE).

Смысл проекта — не склад файлов, а понятный рабочий процесс для команды:

- коллега находит нужный скилл по задаче;
- понимает, какой фразой запустить его в Codex;
- видит владельца, границы применения и примеры;
- может установить скиллы локально через один installer, который проверяет подпись release;
- получает новые скиллы повторным запуском той же команды установки;
- может предложить новый скилл через Pull Request;
- проверки не дают случайно добавить мусор, приватные данные или сломанный skill.

Если вы не инженер, начните с одного файла: [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md). Его можно загрузить в Codex, нажать отправить и дальше следовать инструкциям.

Если вы организуете подключение коллег, используйте [admin-onboarding-guide.md](admin-onboarding-guide.md). Это внутренний гид для организатора, а не основной файл для коллеги.

Если вы уверенно работаете с терминалом, используйте [quickstart.md](quickstart.md).

Если ваша команда работает в Claude Code, репозиторий подключается как нативный маркетплейс Claude Code — инструкция в [docs/claude-code-marketplace.md](docs/claude-code-marketplace.md) (ручная установка и авто-раздача на всю фирму через managed settings).

Чтобы понять, какие скиллы уже есть, откройте [catalog.md](catalog.md).

Чтобы не смешивать платформу и первый пример, прочитайте:

- [docs/platform-overview.md](docs/platform-overview.md) — что такое общее хранилище скиллов;
- [docs/seed-skill-example.md](docs/seed-skill-example.md) — почему фотобомбинг здесь только первый пример.

Языковой контракт проекта описан в [language-policy.md](language-policy.md): человеческий интерфейс на русском, технические ключи и команды остаются стабильными.

## Как Устроен Проект

```text
plugins/team-skills/
  .codex-plugin/plugin.json       # паспорт plugin для Codex
  skills/<skill-name>/
    SKILL.md                      # инструкция, которую читает Codex
    skill.yaml                    # карточка скилла для команды
    known-exceptions.yaml         # известные сбои и действия на следующий раз
    references/domain-playbook.md # только для domain/interface-heavy skills
    examples/                     # хорошие примеры и анти-примеры
catalog.md                        # каталог для людей
quickstart.md                     # короткий технический старт
START_HERE_CONNECT_CODEX_SKILLS.md # стартовый файл, который отправляют коллеге
admin-onboarding-guide.md         # внутренний гид для организатора onboarding
installer/                        # установка подписанного release и uninstall
scripts/                          # установка plugin и создание новых скиллов
tests/                            # проверки структуры, примеров и приватности
```

## User Mode И Author Mode

Обычный пользователь не клонирует repo руками. Он загружает [START_HERE_CONNECT_CODEX_SKILLS.md](START_HERE_CONNECT_CODEX_SKILLS.md) в Codex, получает OS-specific installer и ставит последнюю проверенную версию `team-skills` из release-bundle.

Автор скиллов работает через Pull Request: создаёт branch, добавляет skill, запускает `python -m pytest` и отправляет изменения на review.

## Как Добавляется Новый Скилл

1. Автор проверяет discovery gate: задача повторяемая, входы и результат понятны, есть реалистичные примеры, границы, проверки и maintainer.

2. Автор создаёт черновик:

   ```bash
   python scripts/new_skill.py <skill-name> --owner @github-login
   ```

3. Автор заполняет `SKILL.md`, `skill.yaml`, `known-exceptions.yaml` и `examples/`.
   Если исходный workflow передал другой коллега, сохраняйте его вклад через `authors` и `source_asset`, а в `owner` ставьте подтвержденного maintainer-а.
4. Автор добавляет строку в `catalog.md`.
5. Автор запускает проверки:

   ```bash
   python -m pytest
   ```

6. Автор открывает Pull Request и объясняет:
   - какую повторяющуюся боль решает skill;
   - для кого он нужен;
   - когда его нельзя применять;
   - какие примеры доказывают полезность.

## Что Считать Хорошим Скиллом

Хороший командный skill:

- запускается обычной человеческой фразой, а не только `$skill-name`;
- решает повторяемую задачу;
- имеет понятные границы применения;
- читает `known-exceptions.yaml` как список уже известных сбоев;
- содержит хорошие примеры и анти-примеры;
- не содержит токены, личные пути, приватные данные и сырой контекст клиентов.
- сохраняет очищенную специфику реальных сервисов: UI-состояния, selectors, лимиты, recovery, локальные языковые ключи и known exceptions, если именно они делают workflow быстрым.
- для domain/interface-heavy workflow хранит короткий `references/domain-playbook.md`, где механика сервиса отделена от личных значений.

## Как Skill Учится На Сбоях

Сырые карточки ошибок хранятся приватно вне repo:

```text
~/.codex/skill-runs/<skill-name>/exception-log.jsonl
```

Если пользователь поправил skill, tool упал, нарушен режим работы, пришлось искать workaround или skill сделал ложное предположение, исполнитель записывает короткую карточку ошибки. Reviewer-skill `skill-exception-reviewer` читает такие карточки и предлагает patch proposal, но не применяет его сам.

В repo попадает только очищенное знание: запись в `known-exceptions.yaml`, правка `SKILL.md`, `references/domain-playbook.md` для интерфейсной механики, example и test. Применение идёт через human approval, `python -m pytest` и git commit.

Подробный формат описан в [docs/skill-exception-learning.md](docs/skill-exception-learning.md).
