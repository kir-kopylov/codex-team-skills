# CLAUDE.md

Guidance for AI assistants (Claude Code, Codex, etc.) working in this repository.

## What This Repository Is

`codex-team-skills` is a **public, read-only team registry of reusable AI
skills**, packaged as a single local Codex plugin named `team-skills`. The same
skill folders are also synced into Claude Code, so one registry serves **two
runtimes**. It is a *workflow*, not just a file store: a colleague finds the
skill that fits their task, learns the plain-language phrase that triggers it,
sees the owner / boundaries / examples, installs everything through one signed
installer, and receives updates via signed releases with auto-update every two
days.

There are two roles to keep in mind:

- **User mode** — a non-engineer who never clones the repo. They load
  `START_HERE_CONNECT_CODEX_SKILLS.md` into Codex, get an OS-specific signed
  installer, and run the latest CI-validated `team-skills` bundle.
- **Author mode** — a contributor who adds or edits skills via a Pull Request:
  create a branch, add/fill a skill, run `python -m pytest`, open a PR.

Most work an AI assistant does here is **author mode**.

## Language Contract (read this before editing any prose)

This is the single most important convention and it is enforced by CI
(`tests/test_language_policy.py`). Get it wrong and tests fail.

- **Human-facing text must be in Russian.** This includes: `README.md`,
  `catalog.md`, `quickstart.md`, `START_HERE_CONNECT_CODEX_SKILLS.md`,
  `admin-onboarding-guide.md`, `CONTRIBUTING.md`, `language-policy.md`,
  `docs/*.md` (including `docs/skill-exception-learning.md`),
  `.github/pull_request_template.md`, the `body` and `description` of every
  `SKILL.md`, every `examples/*.md`, human-readable strings in `plugin.json` /
  `marketplace.json` / `skill.yaml`, and any user-visible script/installer
  messages.
- **Technical contract terms must stay stable (do not translate):** file names
  (`SKILL.md`, `plugin.json`, `skill.yaml`, `catalog.md`,
  `known-exceptions.yaml`); YAML/JSON keys (`owner`, `status`, `summary`,
  `use_cases`, `do_not_use_for`, `natural_triggers`, `example_files`,
  `last_reviewed`); status values (`draft`, `team-ready`, `deprecated`,
  `internal-only`); commands (`python -m pytest`,
  `./scripts/install_plugin.sh`); paths, plugin/skill names, branch and repo
  names.
- The full policy lives in `language-policy.md`. The test also bans a list of
  specific old English UI phrases from returning (`FORBIDDEN_OLD_ENGLISH_PHRASES`
  in the test) — don't reintroduce English headings like "Quickstart",
  "Good Example", "Expected Behavior", "Input", etc. Skill prose may keep
  technical English terms but must stay majority-Russian (`min_ratio=0.7` for
  `SKILL.md`).

This `CLAUDE.md` file itself is **not** in the language-policy scope, so it is
intentionally written in English for AI assistants.

## Repository Layout

```text
plugins/team-skills/
  .codex-plugin/plugin.json        # plugin manifest read by Codex
  skills/<skill-name>/
    SKILL.md                       # instructions the model reads (YAML frontmatter + body)
    skill.yaml                     # team registry card (owner, status, triggers, examples)
    known-exceptions.yaml          # REQUIRED: known-failure memory for the skill
    examples/                      # good-*.md and anti-*.md evidence files
    references/                    # OPTIONAL: domain-playbook.md / heavier reference docs
    agents/openai.yaml             # OPTIONAL: UI name / short description / default prompt
    scripts/                       # OPTIONAL: skill-specific helper scripts
catalog.md                         # human catalog of team-ready skills
README.md / quickstart.md          # entry docs (Russian)
START_HERE_CONNECT_CODEX_SKILLS.md # the file a colleague sends to Codex to onboard
admin-onboarding-guide.md          # internal guide for whoever runs onboarding
language-policy.md                 # the language contract (enforced by tests)
docs/                              # platform-overview.md, seed-skill-example.md,
                                   #   skill-exception-learning.md
installer/                         # signed user-mode install / update / status / uninstall
                                   #   + bootstrap-*, refresh-team-skills.command
scripts/                           # install_plugin.sh, new_skill.py,
                                   #   build_release_bundle.py, pull-skills.sh
tests/                             # pytest suite (see Testing & CI)
.agents/plugins/marketplace.json   # local marketplace entry pointing at the plugin
.github/workflows/tests.yml        # CI: pytest + smoke tests + signed publish on main
pyproject.toml                     # Python project (requires-python >=3.11)
```

The authoritative list of skills and their statuses lives in `catalog.md`
(team-ready skills) and in each skill's `skill.yaml` (`status` field) — treat
those as the single source of truth rather than hardcoding a list here. The
`photo-photobomb-director` skill is the seed/example that demonstrates the
quality bar; `docs/seed-skill-example.md` walks through it.

## Development Workflow

### Setup

```bash
python -m pip install ".[test]"   # installs PyYAML + pytest + openpyxl (Python >= 3.11)
```

`openpyxl` is needed because some skills (e.g. `remont-smeta-builder`) ship
`scripts/` that build `.xlsx` output and have tests that exercise them.

### Adding or editing a skill

1. **Create the draft** with the generator (never hand-create the folder):

   ```bash
   python scripts/new_skill.py <skill-name> --owner @github-login --summary "Коротко: что делает skill"
   ```

   The name is normalized to `kebab-case` and must match the folder name. Avoid
   generic names like `helper`, `workflow`, `assistant`. The generator scaffolds
   `SKILL.md` (including the `## Логирование Сбоев` section),
   `skill.yaml`, an empty `known-exceptions.yaml` (`exceptions: []`), and five
   example stubs. If the skill already exists, edit it in place — do not re-run
   the generator (it refuses to overwrite).

2. **Fill in** `SKILL.md`, `skill.yaml`, and `examples/`. The `description` in
   `SKILL.md` frontmatter is the routing mechanism: it must include the natural
   trigger phrases so users don't need to remember the internal skill name
   (max 1024 chars, no `TODO`).

3. **Update `catalog.md`** with a row — required for any `team-ready` skill. The
   row must carry a real, non-empty "Первая фраза для Codex" cell (the phrase a
   colleague pastes to route to the skill) and link to the skill's `SKILL.md`.

4. **Run the checks** and fix the *cause* of any failure (never bypass a check):

   ```bash
   python -m pytest
   ```

5. **Open a Pull Request** that answers the four mandatory questions (see
   `CONTRIBUTING.md` and `.github/pull_request_template.md`):
   - What repeatable pain does this skill solve?
   - Who needs it?
   - When must it NOT be used?
   - Which examples prove it's useful?

### Skill statuses

- `draft` — early; structure exists, team should not rely on it yet.
- `team-ready` — has an owner, a `catalog.md` row, ≥3 `good-*` examples, ≥2
  `anti-*` examples, no template placeholders / `TODO`, and green tests.
- `internal-only` — useful but needs internal context or special limits.
- `deprecated` — must carry a `replacement` or `deprecation_reason` key.

### Local plugin install (authors/devs only)

```bash
./scripts/install_plugin.sh   # copies plugin to ~/plugins and registers local marketplace
```

End users instead use the signed installers in `installer/` (documented in
`quickstart.md`). `scripts/build_release_bundle.py` builds the validated
release bundle that CI signs and publishes.

## Failure-Learning System (known-exceptions)

This repo ships a lightweight v1 loop for teaching skills from their own
mistakes. The full design is in `docs/skill-exception-learning.md`; the
honest maturity note there matters — the automated half of the loop has not
been run end-to-end, so today's real value is the pre-filled
`known-exceptions.yaml` entries.

- **Every skill must have `known-exceptions.yaml`** next to `SKILL.md`
  (enforced by `tests/test_known_exceptions.py`). Minimal content is
  `exceptions: []`. Each entry, when present, requires the keys `symptom`,
  `root_cause`, `do_next_time`, `source_example` (all non-empty strings); the
  only allowed top-level key is `exceptions`.
- **Every `SKILL.md` must carry a `## Логирование Сбоев` section** that: tells
  the model to read `known-exceptions.yaml` before running, points raw failure
  cards at the private local log
  `~/.codex/skill-runs/<skill-name>/exception-log.jsonl`, and states
  `Raw logs не коммитить`. The generator emits this; do not delete it.
- **Raw failure logs stay private** (outside the repo). Only sanitized
  knowledge is promoted into the repo: a cleaned `known-exceptions.yaml` entry,
  a `SKILL.md` edit, a `references/domain-playbook.md` patch, a synthetic
  good/anti example, or a regression test. Never commit raw logs, PII, private
  paths, tokens, client transcripts, or screenshots.
- Two skills operate this loop: `skill-exception-reviewer` (turns sanitized
  cards into a patch *proposal* without applying it) and `skill-methodologist`
  (designs the skill contract up front).

## references/ and domain playbooks

`references/` holds heavier per-skill docs that don't belong in the short
`SKILL.md` body — e.g. `add-team-skill/references/discovery-gate.md`,
`skill-methodologist/references/skill-methodology.md`,
`dopsoglasheniya-po-oplate/references/bloki-DS.md`.

For domain/interface-heavy skills, `references/domain-playbook.md` is the
short service memory. When present it **must** contain the sections
`# Domain Playbook`, `## Что Нельзя Потерять`, `## Что Надо Обезличить`,
`## Interface Mechanics`, `## Recovery And Edge Cases` (enforced by
`tests/test_domain_playbook.py`). Add it only when a failure exposes concrete
interface mechanics (URL patterns, selectors, paid/no-payment paths, local
language keys); a generic, interface-independent failure does not need one.

## Key Conventions & Hard Rules

- **`SKILL.md` frontmatter** may only contain these keys: `name`,
  `description`, `license`, `allowed-tools`, `metadata` (enforced by
  `tests/test_skill_structure.py`). `name` must equal the folder name and be
  `kebab-case`. Keep the body short and procedural (overview, natural inputs,
  process, boundaries/safety, `## Логирование Сбоев`) — push long reference
  material into `references/`.
- **`skill.yaml` schema** requires: `owner` (starts with `@`, not a placeholder
  like `@owner`/`@github-login`), `status` (one of the allowed values),
  `summary`, `use_cases`, `do_not_use_for`, `natural_triggers`, `example_files`,
  `last_reviewed` (`YYYY-MM-DD`, a valid date). Every path in `example_files`
  must exist. Optional `authors` (human authorship, must NOT be `@`-handles) and
  `source_asset` go together — if you set `authors`, set `source_asset` too.
  Don't invent an unconfirmed GitHub handle for `owner`; keep the real author in
  `authors`/`source_asset` and put a confirmed maintainer in `owner`.
- **Examples** (`examples/*.md`) must each contain the sections `## Вход`,
  `## Ожидаемое Поведение`, `## Нельзя` (enforced by
  `tests/test_examples.py`). Good examples prove applicability; anti-examples
  show a boundary where the skill should refuse, ask, or defer.
- **Privacy** (`tests/test_privacy.py`): never commit API tokens, private keys,
  env-var assignments for secrets, personal absolute paths
  (`/Users/<name>/Downloads|Library|Desktop|Documents/...`), pasteboard/download
  paths, raw PII, or private client context. This repo is publicly readable.
  Caveat: the privacy test is regex-only — it does NOT catch real personal
  names (no NER detector) or relative `~/` paths, so a green `pytest` is not a
  privacy clearance; a human must still review before publishing.
- **`mac-app-uninstaller` scanner is scan-only**: its script must never contain
  deletion primitives (`rm -`, `.unlink(`, `rmtree`, `send2trash`, etc.) —
  enforced by `tests/test_mac_app_uninstaller.py`.
- **Plugin manifest** (`tests/test_plugin_manifest.py`): `name` is
  `team-skills`, `version` is semver, `skills` is `./skills/`, and the
  `interface.defaultPrompt` list has 1–3 entries each ≤128 chars.
- A skill should be triggerable by a normal human phrase, not just by
  `$skill-name`.

## Delivery Pipeline (two runtimes)

The same skill folders reach users two ways; both are covered by tests, so
changes here must keep the tests and the Russian user-facing messages intact.

- **Codex plugin** — the signed release bundle. `installer/` contains the full
  install / update / status / uninstall set for macOS (`.command` / `.sh`) and
  Windows (`.ps1` / `.cmd`), plus `bootstrap-team-skills.{sh,ps1}`. Auto-update
  runs every two days via a macOS LaunchAgent
  (`com.codex-team-skills.autoupdate`, interval `172800`) and a Windows
  Scheduled Task (`-Daily -DaysInterval 2`). Updates are verified against a
  signed `manifest.json` / `latest.json` using
  `installer/team-skills-public-key.pem`. `installer/team-skills-registry.py`
  idempotently manages the Codex `config.toml` marketplace/plugin stanzas
  (touching only `codex-team-skills`-owned entries).
- **Claude Code sync** — `scripts/pull-skills.sh` copies the repo's skill
  folders into `~/.claude/skills/` (overridable via `CLAUDE_SKILLS_DIR` /
  `TEAM_SKILLS_SRC`; `TEAM_SKILLS_PULL=0` skips the network `git pull`). It is
  fail-closed on bad frontmatter, marks managed skills with a `.team-skill`
  sentinel, and prunes only its own orphans — never a colleague's local-only
  skill. `installer/refresh-team-skills.command` chains update + sync + a
  detached app restart.

## Testing & CI

- Run the whole suite locally before finishing any change:

  ```bash
  python -m pytest
  ```

  Pytest config lives in `pyproject.toml` (`addopts = "-q"`,
  `testpaths = ["tests"]`). Shared helpers (`skill_dirs`, `load_frontmatter`,
  `load_registry`, `ROOT`, …) are in `tests/conftest.py`.

- The suite is organized by concern:
  - structure & registry: `test_skill_structure.py`, `test_registry.py`,
    `test_catalog.py`, `test_examples.py`, `test_known_exceptions.py`,
    `test_domain_playbook.py`, `test_plugin_manifest.py`
  - safety & policy: `test_privacy.py`, `test_language_policy.py`,
    `test_mac_app_uninstaller.py`
  - per-skill behavior: `test_dopsoglasheniya_po_oplate.py`,
    `test_remont_smeta_builder.py`, `test_translate_daily_briefs.py`
  - delivery: `test_installer_architecture.py`, `test_release_assets.py`,
    `test_team_skills_delivery.py`, `test_claude_sync.py`,
    `test_refresh_team_skills_command.py`

- CI (`.github/workflows/tests.yml`) runs on every PR and on push to `main`:
  1. `pytest` (includes language-policy and privacy checks) on Python 3.11;
  2. builds the release bundle via `scripts/build_release_bundle.py`;
  3. a Windows PowerShell smoke test validating the `.ps1` release assets
     (UTF-8 BOM present, no double BOM, parseable, `-ValidateOnly` runs);
  4. a `claude-sync-smoke` job exercising `scripts/pull-skills.sh`;
  5. on push to `main` only: signs `latest.json` / `manifest.json` and
     publishes an immutable GitHub release.

- If you touch `installer/`, `scripts/pull-skills.sh`, or the release bundle,
  run the delivery tests above and keep the Russian user-facing messages intact.

## Git & PR Etiquette

- Develop on a feature branch; do not commit directly to `main`.
- Commit only when asked; write clear, descriptive commit messages.
- Push with `git push -u origin <branch-name>`; retry transient network
  failures with exponential backoff.
- **Do not open a Pull Request unless explicitly requested.**
- For any push or PR (an externally visible action), first show the scope of
  what will be sent unless the user has explicitly asked you to publish.
