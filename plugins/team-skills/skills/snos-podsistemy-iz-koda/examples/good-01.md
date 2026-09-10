# Хороший Пример: Удаление Updater

## Вход

Пользователь явно просит убрать автоматический updater из небольшой библиотеки командных скиллов. После удаления новые версии должны устанавливаться и обновляться через штатный Git marketplace командами `codex plugin`. На старых машинах могла остаться scheduled task.

## Ожидаемое Поведение

Codex сначала доказывает target repo и branch, затем фиксирует остаточный контракт одной фразой. Он находит updater runtime, scheduler registration, repair/status entrypoints, release assets, manifest entries, docs, tests, fixtures и CI. Эти поверхности удаляются.

Переход со старой установки выполняется локальными командами агента: scheduled task удаляется только после проверки exact owned identifier и действия внутри доказанного каталога Team Skills. Скачиваемый очиститель не создаётся. После изменения Codex подтверждает отсутствие старых release assets, выполняет repo-wide negative scan, запускает native marketplace smoke в Windows и macOS и полный suite.

## Нельзя

Нельзя оставить updater assets «для совместимости», продолжать обещать auto-update в docs или заменить удалённый scheduler новой repair platform. Нельзя считать task отсутствующей на всех машинах только потому, что её больше нет в repo.
