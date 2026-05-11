#!/usr/bin/env python3
"""Create a draft team skill with registry metadata and examples."""

from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "plugins" / "team-skills" / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_name(raw: str) -> str:
    name = raw.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    if not name or not NAME_RE.match(name):
        raise SystemExit(f"Invalid skill name after normalization: {name!r}")
    return name


def write_new(path: Path, content: str) -> None:
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="Skill name, normalized to kebab-case")
    parser.add_argument("--owner", default="@owner", help="Skill owner handle")
    parser.add_argument("--summary", default="TODO: short practical summary")
    args = parser.parse_args()

    skill_name = normalize_name(args.name)
    skill_dir = SKILLS_DIR / skill_name
    if skill_dir.exists():
        raise SystemExit(f"Skill already exists: {skill_dir}")

    title = " ".join(part.capitalize() for part in skill_name.split("-"))
    today = date.today().isoformat()

    write_new(
        skill_dir / "SKILL.md",
        f"""---
name: {skill_name}
description: TODO: Explain when to use this skill, including natural trigger phrases so users do not need to remember the skill name.
---

# {title}

## Overview

TODO: Explain the recurring task this skill handles and the expected user-facing behavior.

## Natural Entry Points

TODO: List ordinary phrases that should trigger this skill.

## Workflow

TODO: Describe the minimum decision process and tool usage.

## Boundaries

TODO: State when not to use this skill and what must be preserved or avoided.
""",
    )

    write_new(
        skill_dir / "skill.yaml",
        f"""owner: "{args.owner}"
status: "draft"
summary: "{args.summary}"
use_cases:
  - "TODO: concrete recurring use case"
do_not_use_for:
  - "TODO: boundary or unsafe/non-goal case"
natural_triggers:
  - "TODO: natural trigger phrase"
example_files:
  - "examples/good-01.md"
  - "examples/good-02.md"
  - "examples/good-03.md"
  - "examples/anti-01.md"
  - "examples/anti-02.md"
last_reviewed: "{today}"
""",
    )

    for filename, kind in [
        ("good-01.md", "Good Example"),
        ("good-02.md", "Good Example"),
        ("good-03.md", "Good Example"),
        ("anti-01.md", "Anti-Example"),
        ("anti-02.md", "Anti-Example"),
    ]:
        write_new(
            skill_dir / "examples" / filename,
            f"""# {kind}

## Input

TODO: realistic user request.

## Expected Behavior

TODO: expected routing, output, or tool behavior.

## Must Not

TODO: concrete behavior the skill must avoid.
""",
        )

    print(f"Created draft skill: {skill_dir}")
    print("Next: fill SKILL.md, skill.yaml, examples, and catalog.md before marking team-ready.")


if __name__ == "__main__":
    main()

