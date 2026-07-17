# Fixture Проверки Подписи Windows

Файлы `latest.json` и `latest.json.sig` взяты из публичного release
`team-skills-vr210.1-eed9043`. Они нужны, чтобы Windows PowerShell 5.1
проверял тот же production public key и тот же формат detached signature,
которые использует updater.

Приватного ключа здесь нет. При ротации signing key обновите public key,
закреплённые RSA parameters и эту публичную пару одним изменением. Новую пару
готовьте и подписывайте офлайн до merge по `admin-onboarding-guide.md`; первый
release с новым ключом не может быть предварительным условием зелёного CI.
