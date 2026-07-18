# Хороший Пример: Удаление Updater

## Вход

Пользователь явно просит убрать автоматический updater из небольшой библиотеки командных скиллов. После удаления новые версии должны устанавливаться повторным ручным запуском подписанного installer. На старых машинах могла остаться scheduled task.

## Ожидаемое Поведение

Codex сначала доказывает target repo и branch, затем фиксирует остаточный контракт одной фразой. Он находит updater runtime, scheduler registration, repair/status entrypoints, release assets, manifest entries, docs, tests, fixtures и CI. Эти поверхности удаляются.

Отдельно сохраняется только идемпотентная одноразовая очистка exact owned scheduled-task identifier в installer или uninstaller. Она не запускает фоновые процессы и не превращается в новый updater. После изменения Codex проверяет фактический release bundle, выполняет repo-wide negative scan, запускает installer smoke в заявленном shell и полный suite.

## Нельзя

Нельзя оставить updater assets «для совместимости», продолжать обещать auto-update в docs или заменить удалённый scheduler новой repair platform. Нельзя считать task отсутствующей на всех машинах только потому, что её больше нет в repo.
