from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins" / "team-skills"
SKILLS_DIR = PLUGIN_DIR / "skills"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def skill_dirs() -> list[Path]:
    return sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())


def load_frontmatter(path: Path) -> tuple[dict, str]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?", content, re.DOTALL)
    assert match, f"{path} must start with YAML frontmatter"
    data = yaml.safe_load(match.group(1))
    assert isinstance(data, dict), f"{path} frontmatter must be a mapping"
    return data, content[match.end() :]


def load_registry(skill_dir: Path) -> dict:
    path = skill_dir / "skill.yaml"
    assert path.exists(), f"{path} is required"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path} must be a YAML mapping"
    return data


def assert_nonempty_list(data: dict, key: str, context: Path) -> None:
    value = data.get(key)
    assert isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value), (
        f"{context}: {key} must be a non-empty string list"
    )

