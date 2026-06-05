# CLAUDE.md

Guidance for AI assistants (Claude Code, Codex, etc.) working in this repository.

## What This Repository Is

`codex-team-skills` is a **public, read-only team registry of reusable Codex
skills**, packaged as a single local Codex plugin named `team-skills`. It is a
*workflow*, not just a file store: a colleague finds the skill that fits their
task, learns the plain-language phrase that triggers it, sees the owner /
boundaries / examples, installs everything through one signed installer, and
receives updates via signed releases with auto-update every two days.

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
  `docs/*.md`, `.github/pull_request_template.md`, the `body` and `description`
  of every `SKILL.md`, every `examples/*.md`, human-readable strings in
  `plugin.json` / `marketplace.json` / `skill.yaml`, and any user-visible
  script/installer messages.
- **Technical contract terms must stay stable (do not translate):** file names
  (`SKILL.md`, `plugin.json`, `skill.yaml`, `catalog.md`); YAML/JSON keys
  (`owner`, `status`, `summary`, `use_cases`, `do_not_use_for`,
  `natural_triggers`, `example_files`, `last_reviewed`); status values
  (`draft`, `team-ready`, `deprecated`, `internal-only`); commands
  (`python -m pytest`, `./scripts/install_plugin.sh`); paths, plugin/skill
  names, branch and repo names.
- The full policy lives in `language-policy.md`. The test also bans a list of
  specific old English UI phrases from returning (`FORBIDDEN_OLD_ENGLISH_PHRASES`
  in the test) — don't reintroduce English headings like "Quickstart",
  "Good Example", "Expected Behavior", "Input", etc.

This `CLAUDE.md` file itself is **not** in the language-policy scope, so it is
intentionally written in English for AI assistants.

## Repository Layout

```text
plugins/team-skills/
  .codex-plugin/plugin.json        # plugin manifest read by Codex
  skills/<skill-name>/
    SKILL.md                       # instructions Codex reads (YAML frontmatter + body)
    skill.yaml                     # team registry card (owner, status, triggers, examples)
    examples/                      # good-*.md and anti-*.md evidence files
    agents/openai.yaml             # OPTIONAL: UI name / short description / default prompt
    scripts/                       # OPTIONAL: skill-specific helper scripts
catalog.md                         # human catalog of team-ready skills
README.md / quickstart.md          # entry docs (Russian)
START_HERE_CONNECT_CODEX_SKILLS.md # the file a colleague sends to Codex to onboard
admin-onboarding-guide.md          # internal guide for whoever runs onboarding
language-policy.md                 # the language contract (enforced by tests)
docs/                              # platform-overview.md, seed-skill-example.md
installer/                         # signed user-mode install / update / status / uninstall
scripts/                           # install_plugin.sh, new_skill.py, build_release_bundle.py
tests/                             # pytest suite: structure, registry, examples, privacy, language, delivery
.agents/plugins/marketplace.json   # local marketplace entry pointing at the plugin
.github/workflows/tests.yml        # CI: pytest + Windows smoke + signed publish on main
pyproject.toml                     # Python project (requires-python >=3.11, PyYAML, pytest)
```

The current team-ready skills are: `add-team-skill`,
`conceptual-decomposition`, `team-skills-maintenance`, `mac-app-uninstaller`,
`production-forensic-auditor`, and `photo-photobomb-director` (the
seed/example skill that demonstrates the quality bar). See `catalog.md` for
the authoritative list.

## Development Workflow

### Setup

```bash
python -m pip install ".[test]"   # installs PyYAML + pytest (Python >= 3.11)
```

### Adding or editing a skill

1. **Create the draft** with the generator (never hand-create the folder):

   ```bash
   python scripts/new_skill.py <skill-name> --owner @github-login --summary "Коротко: что делает skill"
   ```

   The name is normalized to `kebab-case` and must match the folder name. Avoid
   generic names like `helper`, `workflow`, `assistant`. If the skill already
   exists, edit it in place — do not re-run the generator.

2. **Fill in** `SKILL.md`, `skill.yaml`, and `examples/`. The `description` in
   `SKILL.md` frontmatter is the routing mechanism: it must include the natural
   trigger phrases so users don't need to remember the internal skill name.

3. **Update `catalog.md`** with a row — required for any `team-ready` skill.

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
  `anti-*` examples, no template placeholders, and green tests.
- `internal-only` — useful but needs internal context or special limits.
- `deprecated` — must carry a `replacement` or `deprecation_reason` key.

### Local plugin install (authors/devs only)

```bash
./scripts/install_plugin.sh   # copies plugin to ~/plugins and registers local marketplace
```

End users instead use the signed installers in `installer/` (documented in
`quickstart.md`). `scripts/build_release_bundle.py` builds the validated
release bundle that CI signs and publishes.

## Key Conventions & Hard Rules

- **`SKILL.md` frontmatter** may only contain these keys: `name`,
  `description`, `license`, `allowed-tools`, `metadata` (enforced by
  `tests/test_skill_structure.py`). `name` must equal the folder name and be
  `kebab-case`. Keep the body short and procedural (overview, request routing,
  process, boundaries/safety, definition of done) — no long reference docs.
- **`skill.yaml` schema** requires: `owner` (starts with `@`), `status` (one of
  the allowed values), `summary`, `use_cases`, `do_not_use_for`,
  `natural_triggers`, `example_files`, `last_reviewed` (`YYYY-MM-DD`, a valid
  date). Every path in `example_files` must exist.
- **Examples** (`examples/*.md`) must each contain the sections `## Вход`,
  `## Ожидаемое Поведение`, `## Нельзя` (enforced by
  `tests/test_examples.py`). Good examples prove applicability; anti-examples
  show a boundary where the skill should refuse, ask, or defer.
- **Privacy** (`tests/test_privacy.py`): never commit API tokens, private keys,
  env-var assignments for secrets, personal absolute paths
  (`/Users/<name>/Downloads|Library|Desktop|Documents/...`), pasteboard/download
  paths, raw PII, or private client context. This repo is publicly readable.
- **`mac-app-uninstaller` scanner is scan-only**: its script must never contain
  deletion primitives (`rm -`, `.unlink(`, `rmtree`, `send2trash`, etc.) —
  enforced by `tests/test_mac_app_uninstaller.py`.
- **Plugin manifest** (`tests/test_plugin_manifest.py`): `name` is
  `team-skills`, `version` is semver, `skills` is `./skills/`, and the
  `interface.defaultPrompt` list has 1–3 entries each ≤128 chars.
- A skill should be triggerable by a normal human phrase, not just by
  `$skill-name`.

## Testing & CI

- Run the whole suite locally before finishing any change:

  ```bash
  python -m pytest
  ```

  Pytest config lives in `pyproject.toml` (`addopts = "-q"`,
  `testpaths = ["tests"]`). Test helpers are in `tests/conftest.py`.

- CI (`.github/workflows/tests.yml`) runs on every PR and on push to `main`:
  1. `pytest` (includes language-policy and privacy checks) on Python 3.11;
  2. builds the release bundle via `scripts/build_release_bundle.py`;
  3. a Windows PowerShell smoke test validating the `.ps1` release assets
     (UTF-8 BOM present, no double BOM, parseable, `-ValidateOnly` runs);
  4. on push to `main` only: signs `latest.json` / `manifest.json` and
     publishes an immutable GitHub release.

- The delivery contract (installer scripts, registry helper, workflow) is
  itself tested by `tests/test_installer_architecture.py`,
  `tests/test_release_assets.py`, and `tests/test_team_skills_delivery.py`. If
  you touch `installer/` or the release bundle, run these and keep the Russian
  user-facing messages intact.

## Git & PR Etiquette

- Develop on a feature branch; do not commit directly to `main`.
- Commit only when asked; write clear, descriptive commit messages.
- Push with `git push -u origin <branch-name>`; retry transient network
  failures with exponential backoff.
- **Do not open a Pull Request unless explicitly requested.**
- For any push or PR (an externally visible action), first show the scope of
  what will be sent unless the user has explicitly asked you to publish.
