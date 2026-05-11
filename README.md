# Codex Team Skills Registry

Private team registry for reusable Codex skills packaged as one local plugin: `team-skills`.

The goal is practical reuse, not a file dump. Each team-ready skill must have:

- a clear natural-language entry point,
- an owner,
- concrete use cases and boundaries,
- good examples and anti-examples,
- passing lightweight CI checks.

Start with [quickstart.md](quickstart.md), then use [catalog.md](catalog.md) to find a skill by task.

## Repository Shape

```text
plugins/team-skills/
  .codex-plugin/plugin.json
  skills/<skill-name>/
    SKILL.md
    skill.yaml
    examples/
catalog.md
quickstart.md
scripts/
tests/
```

## Contribution Loop

1. Create a draft skill with `python scripts/new_skill.py <skill-name> --owner @yourname`.
2. Fill `SKILL.md`, `skill.yaml`, and examples.
3. Add or update the entry in `catalog.md`.
4. Run `python -m pytest`.
5. Open a PR that answers: pain solved, audience, when not to use, and examples that prove usefulness.

