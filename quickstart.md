# Quickstart

## Install Or Update

From the repo root:

```bash
./scripts/install_plugin.sh
```

Then restart Codex so the local plugin and skills are reloaded.

## First Smoke Run

In Codex, attach a photo and write:

```text
Сделай фотобомбинг: друзья, уровень 2, людей и фон не трогать.
```

Expected behavior: Codex should use the photobomb skill without you remembering its internal name, preserve existing subjects and background, and add only new comic photobomb elements.

## Add A Skill

```bash
python scripts/new_skill.py my-skill --owner @yourname --summary "Short practical summary"
python -m pytest
```

Update `catalog.md` before marking a skill `team-ready`.

## Private Repo Setup

This repository is intended to be private. Keep raw client data, tokens, pasteboard paths, downloads paths, and personal examples out of committed skill content.

