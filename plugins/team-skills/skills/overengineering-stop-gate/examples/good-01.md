# Хороший Пример: Updater Не Пережил Gate

## Вход

Команда поддерживает небольшую библиотеку командных скиллов. В плане уже появились scheduler, подписанные metadata, rollback, cache invalidation и Windows PowerShell 5.1 end-to-end regression test. Пользователь спрашивает: «Зачем нам вообще updater? Он не нужен. Сноси его и оставь обычное ручное обновление».

## Ожидаемое Поведение

Codex явно фиксирует outcome одним предложением: команда должна предсказуемо устанавливать и вручную обновлять библиотеку скиллов.

В complexity ledger updater получает `delete`: отдельная пользовательская боль для фонового автообновления не доказана, а его дополнительный ownership cost включает scheduler, фоновую orchestration, state/repair, rollback, Windows-совместимость и поддержку legacy-задач. Штатный Git marketplace и повторный вызов `codex plugin add` получают отдельный `keep`: они закрывают доставку без собственного updater runtime.

PowerShell regression test полного updater-flow отменяется: он проверял механизм, который не пережил gate. Surviving invariant — чистая установка и ручное обновление библиотеки без updater. Поскольку пользователь явно разрешил удаление, единственный следующий шаг — передать точный scope в `subsystem-retirement-safeguard`.

## Нельзя

Нельзя продолжать строить Windows E2E старого updater «раз уж начали». Нельзя сохранять updater ради sunk cost. Нельзя расширять удаление на штатный Codex marketplace или на независимую доставку Claude Code.
