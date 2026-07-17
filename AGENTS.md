# AGENTS.md

Guidance for Codex and other AI agents working in this repository.

## Scope And Source Of Truth

This root file applies to the whole repository. A nested `AGENTS.md` may add
more specific instructions for its own subtree.

The complete shared repository workflow lives in `CLAUDE.md`, while the
machine-readable two-runtime topology lives in `runtime-contract.yaml`. Read
both before editing code, prose, skills, installers, delivery scripts, or CI.
Despite its filename, `CLAUDE.md` is intentionally written for all AI
assistants, including Codex. It remains the authoritative source for:

- the repository purpose and user/author modes;
- the Russian-language policy;
- skill structure, registry fields, examples, and status rules;
- privacy and feedback-log boundaries;
- installer and delivery architecture;
- tests, CI, Git, and Pull Request etiquette.

This file is a Codex entry point and a rendered runtime map. It must not become
a copied fork of `CLAUDE.md`: duplicated instructions drift and create
contradictory facts. When a shared workflow rule changes, update `CLAUDE.md`.
When runtime topology changes, update `runtime-contract.yaml` and regenerate
the marked table below. Update other parts of this file only for Codex-specific
guidance.

## Runtime Map: Do Not Conflate The Two Paths

The block between the markers is rendered from `runtime-contract.yaml` and
checked byte-for-byte. Do not edit its facts by hand.

<!-- BEGIN GENERATED RUNTIME CONTRACT -->
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
<!-- END GENERATED RUNTIME CONTRACT -->

Every identifier inside the generated block is literal, not a placeholder.
Never derive another runtime's names by analogy or global search-and-replace.
If a required identifier is absent from `runtime-contract.yaml`, stop and
verify the live repository instead of inventing one.

## Non-Negotiable Working Rules

- Human-facing repository text must be in Russian, subject to the exact scope
  and exceptions in `language-policy.md` and `CLAUDE.md`.
- Keep technical filenames, schema keys, status values, commands, paths,
  plugin names, and skill names stable; do not translate them.
- Treat the repository as public. Never commit secrets, raw feedback logs,
  private transcripts, personal data, private paths, or screenshots.
- Use `python scripts/new_skill.py ...` to create a new skill; do not hand-build
  a new skill directory.
- Every skill must keep the required `SKILL.md`, `skill.yaml`, examples,
  `known-exceptions.yaml`, and feedback logger contracts described in
  `CLAUDE.md`.
- Develop changes on a feature branch, never directly on `main`.
- Run the complete suite before finishing a change:

  ```bash
  python -m pytest
  ```

- Fix the cause of a failed check. Do not weaken, skip, or bypass repository
  protections.
- Do not commit unless the user asks. Before any push, show the exact scope that
  will be sent. After opening or updating a PR, triage the automated reviewer
  and answer human-facing PR comments in Russian.

## Codex Reality Check

Before changing Git state, verify the actual repository, current branch,
upstream, staged/unstaged/untracked files, and remote state. Do not infer local
installation, remote publication, CI success, or runtime availability from one
another: they are separate evidence layers.

When documentation and the filesystem disagree, inspect the live files and
tests first. State the discrepancy explicitly; do not repair it by guessing a
new path or renaming another runtime's identifiers.

## Maintenance Rule

Keep this file short. Its purpose is to route Codex into the shared contract
and prevent cross-runtime name corruption. Detailed workflow documentation,
schemas, test inventories, and release mechanics belong in `CLAUDE.md` and the
repository documents it references.
