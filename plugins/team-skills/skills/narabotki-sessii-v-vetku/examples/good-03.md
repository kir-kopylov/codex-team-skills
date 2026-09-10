# Хороший Пример: Неизменяемые Evidence Files И Windows EOL

## Вход

«В package есть manifest с SHA256 и size для семи approved файлов. Перенеси их без изменения байтов и докажи, что новый checkout воспроизводит manifest».

## Ожидаемое Поведение

Skill проверяет manifest отдельно по working tree и Git index до commit. При несовпадении только working bytes исследует EOL policy и `core.autocrlf`, не переписывая approved evidence. Добавляет узкую `.gitattributes` policy только если она действительно нужна для воспроизводимого checkout. После commit запускает `verify-manifest` по `commit,checkout`, где checkout создаётся независимым локальным clone. Публикация разрешена только при совпадении path, SHA256 и size во всех заявленных источниках.

## Нельзя

Нельзя пересчитать manifest от случайно изменённых файлов, объявить working copy единственным источником истины или принять совпадение staged blob без проверки fresh checkout.
