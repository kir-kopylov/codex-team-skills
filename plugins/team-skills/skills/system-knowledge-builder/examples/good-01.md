# Discovery Без Runtime

## Вход

«Построй карту старой системы по локальным repo. Только чтение; `goalrt` пока не
установлен.»

## Ожидаемое Поведение

Skill запрашивает согласие на `SUPERVISED_SOFT_MODE`, запускает только read-only
filesystem/Git discovery, создаёт path-first inventory и отдельный observation
batch с явной пометкой мягкого режима. Не интерпретирует имена файлов как
business meaning.

## Нельзя

- создавать файл `journal.jsonl` и называть его runtime journal;
- обещать enforcement, budget stop или recovery;
- изменять исследуемые repositories.
