# AGENTS.md

Guidance for Codex and other AI agents working in this repository.

## Scope And Source Of Truth

This root file applies to the whole repository. A nested `AGENTS.md` may add
more specific instructions for its own subtree.

The complete shared repository contract lives in `CLAUDE.md`. Read it in full
before editing code, prose, skills, installers, delivery scripts, or CI. Despite
its filename, `CLAUDE.md` is intentionally written for all AI assistants,
including Codex. It remains the authoritative source for:

- the repository purpose and user/author modes;
- the Russian-language policy;
- skill structure, registry fields, examples, and status rules;
- privacy and feedback-log boundaries;
- installer and delivery architecture;
- tests, CI, Git, and Pull Request etiquette.

This file is a Codex entry point and a runtime map. It must not become a copied
fork of `CLAUDE.md`: duplicated instructions drift and create contradictory
facts. When a shared rule changes, update `CLAUDE.md`. Update this file only
when Codex-specific guidance or the runtime map changes.

## Runtime Map: Do Not Conflate The Two Paths

The repository intentionally serves two different runtimes from the same
`plugins/team-skills/skills/` folders:

| Concern | Codex path | Claude Code path |
| --- | --- | --- |
| Plugin manifest | `plugins/team-skills/.codex-plugin/plugin.json` | `.claude-plugin/plugin.json` |
| Marketplace metadata | `.agents/plugins/marketplace.json` | `.claude-plugin/marketplace.json` |
| Delivery | signed bundle and installers in `installer/` | sync through `scripts/pull-skills.sh` |
| Local skill destination | managed by the Codex plugin installer | `~/.claude/skills/` |

The Claude Code manifest intentionally has no `version` field. The Codex
manifest has a semver `version`. Preserve both rules exactly as documented and
tested in `CLAUDE.md`.

Names such as `Claude Code`, `.claude-plugin`, `~/.claude/skills/`,
`CLAUDE_SKILLS_DIR`, `test_claude_manifest.py`, and `claude-sync-smoke` are
real interface or contract identifiers. They are not placeholders. Never turn
them into Codex names through global search-and-replace. Do not invent
capitalized plugin directories or a Codex skill-sync destination by analogy;
use only paths that exist in the repository or are documented by the runtime.

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
