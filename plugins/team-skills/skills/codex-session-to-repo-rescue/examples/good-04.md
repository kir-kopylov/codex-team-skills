# Хороший Пример: Две Сессии С Одним Названием

## Вход

«Сохрани результат `Status Export Pass`, в интерфейсе она занимает 2,53 МБ». Рядом есть session 2,16 МБ, внутри которой встречается то же название.

## Ожидаемое Поведение

Skill сначала запускает `resolve-session` с точным title и size. Resolver возвращает единственный thread ID и создаёт immutable `target-lock.json`. Только затем `inventory-session` читает указанный lock. Если size не передан, resolver возвращает `identity_incomplete` и не начинает recovery map.

## Нельзя

Нельзя выбирать session по первому текстовому совпадению, начинать repo-анализ до `target_locked` или молча заменить target в существующем recovery run.
