# CLAUDE.md

Guidance for AI assistants (Claude Code, Codex, etc.) working in this repository.

## What This Repository Is

`codex-team-skills` is a **public, read-only team registry of reusable AI
skills**. Its runtime topology and delivery entrypoints are declared in
`runtime-contract.yaml`. It is a *workflow*, not just a file store: a colleague
finds the skill that fits their task, learns the plain-language phrase that
triggers it, sees the owner / boundaries / examples, connects through the
declared delivery path, and receives updates through that runtime's update
mechanism.

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
  skills/<skill-name>/
    SKILL.md                       # instructions the model reads (YAML frontmatter + body)
    skill.yaml                     # team registry card (owner, status, triggers, examples)
    known-exceptions.yaml          # REQUIRED: known-failure memory for the skill
    examples/                      # good-*.md and anti-*.md evidence files
    references/                    # OPTIONAL: domain-playbook.md / heavier reference docs
    agents/openai.yaml             # OPTIONAL: UI name / short description / default prompt
    scripts/                       # skill-specific helper scripts; log_usage_feedback.py is
                                   #   REQUIRED (byte-identical copy of scripts/templates/)
catalog.md                         # human catalog of team-ready skills
README.md / quickstart.md          # entry docs (Russian)
START_HERE_CONNECT_CODEX_SKILLS.md # the file a colleague sends to Codex to onboard
admin-onboarding-guide.md          # internal guide for whoever runs onboarding
language-policy.md                 # the language contract (enforced by tests)
docs/                              # platform-overview.md, seed-skill-example.md,
                                   #   skill-exception-learning.md, claude-code-marketplace.md
installer/                         # signed user-mode install / update / status / uninstall
                                   #   + bootstrap-*, refresh-team-skills.command
scripts/                           # install_plugin.sh, new_skill.py,
                                   #   runtime delivery helpers,
                                   #   templates/log_usage_feedback.py (canonical copy)
tests/                             # pytest suite (see Testing & CI)
runtime-contract.yaml              # machine-readable Codex/Claude topology
.github/workflows/tests.yml        # CI: pytest + smoke tests + signed publish on main
pyproject.toml                     # Python project (requires-python >=3.11)
```

`runtime-contract.yaml` is the authoritative source for runtime identities,
exact-case repo paths, manifest and marketplace locations, skill discovery,
version policy, and delivery entrypoints. Documentation may explain that
topology, but must not redefine it independently.

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
   `SKILL.md` (including the `## Опрос После Использования` and
   `## Логирование Сбоев` sections), `skill.yaml`, an empty
   `known-exceptions.yaml` (`exceptions: []`), a copy of
   `scripts/templates/log_usage_feedback.py`, and five example stubs. If the
   skill already exists, edit it in place — do not re-run the generator (it
   refuses to overwrite).

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
`quickstart.md`). The contract-declared builder creates the validated release
bundle that CI signs and publishes.

## Feedback-Learning System (known-exceptions + usage feedback)

This repo ships a lightweight v1 loop for teaching skills from their own
mistakes and from user feedback. The full design is in
`docs/skill-exception-learning.md`; the honest maturity note there matters —
the automated half of the loop has not been run end-to-end, so today's real
value is the pre-filled `known-exceptions.yaml` entries and the mandatory
feedback-collection contracts below. There are two private channels:
model-observed failures (`exception-log.jsonl`) and an explicit post-use user
survey (`usage-feedback.jsonl`).

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
- **Every `SKILL.md` must carry a `## Опрос После Использования` section
  BEFORE `## Логирование Сбоев`** (enforced by `tests/test_usage_feedback.py`).
  It asks the user, once per run after the final deliverable or an explicit
  stop, what was useful and what to improve (with a "пропустить" opt-out), and
  saves the sanitized answer to
  `~/.codex/skill-runs/<skill-name>/usage-feedback.jsonl` via the bundled
  `scripts/log_usage_feedback.py`. The honesty phrase
  «не делайте вид, что лог сохранён» and a "не коммитить" privacy clause are
  required strings. The timing sentence is per-skill; the rest is canonical.
- **Every skill must ship `scripts/log_usage_feedback.py`** as a byte-identical
  copy of `scripts/templates/log_usage_feedback.py` (enforced by
  `tests/test_usage_feedback.py`). The script derives the skill name from its
  folder — edit the template and re-copy it to all skills, never patch one copy.
- **Raw failure logs stay private** (outside the repo). Only sanitized
  knowledge is promoted into the repo: a cleaned `known-exceptions.yaml` entry,
  a `SKILL.md` edit, a `references/domain-playbook.md` patch, a synthetic
  good/anti example, or a regression test. Never commit raw logs, PII, private
  paths, tokens, client transcripts, or screenshots.
- Two skills operate this loop: `skill-exception-reviewer` (turns sanitized
  failure cards AND usage-feedback cards into a patch *proposal* without
  applying it) and `skill-methodologist` (designs the skill contract up front).
  Survey wishes become `SKILL.md`/example edits in the proposal;
  `known-exceptions.yaml` entries are reserved for failures.

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
  process, boundaries/safety, `## Опрос После Использования`,
  `## Логирование Сбоев`) — push long reference material into `references/`.
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
- **Plugin manifests**: runtime-specific locations, discovery rules, and
  version policies are generated from `runtime-contract.yaml` in the delivery
  section below. The manifest tests enforce the remaining runtime-specific
  interface fields.
- A skill should be triggerable by a normal human phrase, not just by
  `$skill-name`.

## Delivery Pipeline (two runtimes)

The topology between the two runtimes is generated and checked byte-for-byte.
Do not restate or edit these facts elsewhere in this document.

<!-- BEGIN GENERATED CLAUDE RUNTIME CONTRACT -->
The runtime facts below are generated from `runtime-contract.yaml`. Edit the
contract, not this block.

Both runtimes consume the same `plugins/team-skills/skills/` tree.

| Concern | Codex | Claude Code |
| --- | --- | --- |
| Plugin manifest | `plugins/team-skills/.codex-plugin/plugin.json` | `plugins/team-skills/.claude-plugin/plugin.json` |
| Marketplace metadata | `.agents/plugins/marketplace.json` | `.claude-plugin/marketplace.json` |
| Skill discovery | manifest field `skills` = `./skills/` | plugin-root convention `skills/` |
| Version policy | semver `version` is required | `version` is forbidden |
| Delivery | signed bundle built by `scripts/build_release_bundle.py` | native marketplace; legacy folder sync through `scripts/pull-skills.sh` |
| CI delivery job | `build-release-bundle` invokes the builder | `claude-sync-smoke` invokes the legacy sync |
| Folder-sync destination | not applicable | `~/.claude/skills/` via `CLAUDE_SKILLS_DIR` |

The legacy Claude Code sync reads `TEAM_SKILLS_SRC` as its source override.
<!-- END GENERATED CLAUDE RUNTIME CONTRACT -->

Operational guarantees outside the topology contract:

- The signed-bundle installer set covers macOS and Windows, verifies release
  metadata with the repository public key, updates on the established schedule,
  and changes only registry entries owned by this project.
- The legacy folder-sync path is fail-closed on malformed frontmatter, marks
  only its own managed copies, and never prunes a colleague's local-only skill.
- Changes to installers, sync mechanics, or release assets must preserve the
  Russian user-facing messages and pass their dedicated delivery tests.

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
    `test_usage_feedback.py`, `test_domain_playbook.py`,
    `test_plugin_manifest.py`
  - safety & policy: `test_privacy.py`, `test_language_policy.py`,
    `test_mac_app_uninstaller.py`
  - per-skill behavior: `test_dopsoglasheniya_po_oplate.py`,
    `test_remont_smeta_builder.py`, `test_translate_daily_briefs.py`
  - delivery: `test_installer_architecture.py`, `test_release_assets.py`,
    `test_team_skills_delivery.py`, `test_claude_sync.py`,
    `test_refresh_team_skills_command.py`, `test_runtime_contract.py`,
    `test_cross_runtime_delivery_parity.py`

- CI (`.github/workflows/tests.yml`) runs on every PR and on push to `main`:
  1. `pytest` (includes language-policy and privacy checks) on Python 3.11;
  2. builds the release bundle through the contract-declared builder;
  3. a Windows PowerShell smoke test validating the `.ps1` release assets
     (UTF-8 BOM present, no double BOM, parseable, `-ValidateOnly` runs);
  4. exercises the contract-declared legacy sync in its declared CI job;
  5. on push to `main` only: signs `latest.json` / `manifest.json` and
     publishes an immutable GitHub release.

- If you touch `installer/`, the contract-declared legacy sync, or the release
  bundle, run the delivery tests above and keep the Russian user-facing
  messages intact.

## Git & PR Etiquette

- Develop on a feature branch; do not commit directly to `main`.
- Commit only when asked; write clear, descriptive commit messages.
- Push with `git push -u origin <branch-name>`; retry transient network
  failures with exponential backoff.
- Push and opening a Pull Request are the normal completion of a change, not a
  step that waits for a separate publish request each time.
- Always show the scope of what will be sent before push - that is about
  transparency, not about asking permission.
- This repo has an automated `chatgpt-codex-connector[bot]` reviewer that
  comments on pull requests. Treat its comments as required triage, not
  optional noise: after opening or updating a PR, read what it posted. If you
  agree with a finding, fix it and push the fix. If you disagree, or you have
  a different read of the tradeoff, reply to the comment and explain your
  reasoning instead of silently ignoring it - do not just let it sit
  unanswered either way. The bot's own comments are exempt from the
  Russian-language PR-comment gate (`pr-language.yml`, sender-type check), but
  your replies are not: write them in Russian like any other human-facing PR
  comment, per `language-policy.md`.
