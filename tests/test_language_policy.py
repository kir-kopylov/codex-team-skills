from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from conftest import ROOT, load_frontmatter, load_registry, skill_dirs


CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
CYRILLIC_WORD_RE = re.compile(r"[А-Яа-яЁё]{3,}")
LATIN_WORD_RE = re.compile(r"\b[A-Za-z]{3,}\b")

STRICT_RUSSIAN_FILES = [
    ROOT / "README.md",
    ROOT / "catalog.md",
    ROOT / "quickstart.md",
    ROOT / "SEND_TO_COLLEAGUE.md",
    ROOT / "admin-onboarding-guide.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "language-policy.md",
    ROOT / "docs" / "platform-overview.md",
    ROOT / "docs" / "seed-skill-example.md",
    ROOT / ".github" / "pull_request_template.md",
]

FORBIDDEN_OLD_ENGLISH_PHRASES = [
    "Private team registry",
    "The goal is practical reuse",
    "Start with",
    "Repository Shape",
    "Contribution Loop",
    "Team Skills Catalog",
    "This is the human entry point",
    "Quickstart",
    "Install Or Update",
    "Expected behavior",
    "Contributing Skills",
    "Skill PR Checklist",
    "Pain solved",
    "Good Example",
    "Anti-Example",
    "Expected Behavior",
    "Must Not",
    "Input",
    "Plugin source not found",
    "Installed ",
    "Updated marketplace",
    "Restart Codex",
    "Created draft skill",
    "Next: fill",
]


def prose_for_language_check(path: Path) -> str:
    content = path.read_text(encoding="utf-8")
    content = re.sub(r"```.*?```", " ", content, flags=re.DOTALL)
    content = re.sub(r"`[^`]+`", " ", content)
    content = re.sub(r"https?://\S+", " ", content)
    content = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", content)
    return content


def assert_russian_interface(path: Path, *, min_ratio: float = 1.0) -> None:
    prose = prose_for_language_check(path)
    cyrillic_words = CYRILLIC_WORD_RE.findall(prose)
    latin_words = LATIN_WORD_RE.findall(prose)

    assert cyrillic_words, f"{path} должен содержать русский пользовательский текст"
    assert len(cyrillic_words) >= max(5, int(len(latin_words) * min_ratio)), (
        f"{path} выглядит слишком англоязычным: "
        f"русских слов={len(cyrillic_words)}, латинских слов={len(latin_words)}"
    )


def assert_contains_cyrillic(value: str, context: str) -> None:
    assert CYRILLIC_RE.search(value), f"{context} должен быть на русском для коллег"


def test_core_human_docs_are_russian() -> None:
    for path in STRICT_RUSSIAN_FILES:
        assert path.exists(), f"Не найден файл языковой политики: {path}"
        assert_russian_interface(path)


def test_skill_docs_and_examples_are_russian() -> None:
    for skill_dir in skill_dirs():
        assert_russian_interface(skill_dir / "SKILL.md", min_ratio=0.7)
        for example in (skill_dir / "examples").glob("*.md"):
            assert_russian_interface(example)


def test_human_metadata_fields_are_russian() -> None:
    manifest = json.loads((ROOT / "plugins/team-skills/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
    assert_contains_cyrillic(manifest["description"], "plugin.json description")
    interface = manifest["interface"]
    for key in ("displayName", "shortDescription", "longDescription", "developerName"):
        assert_contains_cyrillic(interface[key], f"plugin.json interface.{key}")
    for index, prompt in enumerate(interface["defaultPrompt"]):
        assert_contains_cyrillic(prompt, f"plugin.json defaultPrompt[{index}]")

    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    assert_contains_cyrillic(marketplace["interface"]["displayName"], "marketplace displayName")

    for skill_dir in skill_dirs():
        frontmatter, _ = load_frontmatter(skill_dir / "SKILL.md")
        assert_contains_cyrillic(frontmatter["description"], f"{skill_dir.name} SKILL.md description")

        registry = load_registry(skill_dir)
        assert_contains_cyrillic(registry["summary"], f"{skill_dir.name} summary")
        for key in ("use_cases", "do_not_use_for"):
            for index, item in enumerate(registry[key]):
                assert_contains_cyrillic(item, f"{skill_dir.name} {key}[{index}]")

        openai_yaml = skill_dir / "agents" / "openai.yaml"
        if openai_yaml.exists():
            data = yaml.safe_load(openai_yaml.read_text(encoding="utf-8"))
            interface = data.get("interface", {})
            for key in ("short_description", "default_prompt"):
                assert_contains_cyrillic(interface[key], f"{skill_dir.name} openai.yaml {key}")


def test_script_user_messages_are_russian() -> None:
    install_script = (ROOT / "scripts/install_plugin.sh").read_text(encoding="utf-8")
    assert "Источник plugin не найден" in install_script
    assert "установлен" in install_script
    assert "Перезапустите Codex" in install_script

    new_skill = (ROOT / "scripts/new_skill.py").read_text(encoding="utf-8")
    assert "Создан черновик skill" in new_skill
    assert "Дальше заполните" in new_skill
    assert "## Вход" in new_skill
    assert "## Ожидаемое Поведение" in new_skill
    assert "## Нельзя" in new_skill


def test_old_english_interface_phrases_do_not_return() -> None:
    checked_files = STRICT_RUSSIAN_FILES + [
        ROOT / "plugins/team-skills/.codex-plugin/plugin.json",
        ROOT / ".agents/plugins/marketplace.json",
        ROOT / "scripts/install_plugin.sh",
        ROOT / "scripts/new_skill.py",
    ]
    for skill_dir in skill_dirs():
        checked_files.append(skill_dir / "SKILL.md")
        checked_files.append(skill_dir / "skill.yaml")
        checked_files.extend(sorted((skill_dir / "examples").glob("*.md")))

    for path in checked_files:
        content = path.read_text(encoding="utf-8")
        for phrase in FORBIDDEN_OLD_ENGLISH_PHRASES:
            assert phrase not in content, f"{path} содержит старую англоязычную фразу: {phrase}"


def test_technical_contract_terms_are_preserved() -> None:
    quickstart = (ROOT / "quickstart.md").read_text(encoding="utf-8")
    assert "./scripts/install_plugin.sh" in quickstart
    assert "python -m pytest" in quickstart

    manifest = json.loads((ROOT / "plugins/team-skills/.codex-plugin/plugin.json").read_text(encoding="utf-8"))
    for key in ("name", "version", "description", "skills", "interface"):
        assert key in manifest
    assert manifest["name"] == "team-skills"
    assert manifest["skills"] == "./skills/"

    for skill_dir in skill_dirs():
        registry_text = (skill_dir / "skill.yaml").read_text(encoding="utf-8")
        for key in (
            "owner:",
            "status:",
            "summary:",
            "use_cases:",
            "do_not_use_for:",
            "natural_triggers:",
            "example_files:",
            "last_reviewed:",
        ):
            assert key in registry_text, f"{skill_dir.name} потерял технический ключ {key}"


def test_colleague_entrypoint_is_unambiguous() -> None:
    assert (ROOT / "SEND_TO_COLLEAGUE.md").exists()
    assert (ROOT / "admin-onboarding-guide.md").exists()
    assert not (ROOT / "colleague-codex-start.md").exists()
    assert not (ROOT / "colleague-onboarding.md").exists()

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "единственный файл" in readme
    assert "SEND_TO_COLLEAGUE.md" in readme
