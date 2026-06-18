"""Поведенческие тесты генератора скилов scripts/new_skill.py.

Генератор — единственная санкционированная точка создания скила
(«никогда не создавай папку вручную»), поэтому регресс здесь молча
порождает скилы, проваливающие остальные контракты. Здесь мы реально
запускаем генератор в tmp-каталог и проверяем как нормализацию имени и
отказ от перезаписи, так и то, что сгенерированный каркас удовлетворяет
тем же инвариантам формы, что и весь остальной набор (consent gate первой
секцией, логирование сбоев, known-exceptions, секции примеров,
допустимые ключи frontmatter)."""

from __future__ import annotations

import importlib.util
import re

import pytest
import yaml

from conftest import ROOT


SCRIPT = ROOT / "scripts" / "new_skill.py"
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_FRONTMATTER_KEYS = {"name", "description", "license", "allowed-tools", "metadata"}
REGISTRY_REQUIRED_KEYS = {
    "owner",
    "status",
    "summary",
    "use_cases",
    "do_not_use_for",
    "natural_triggers",
    "example_files",
    "last_reviewed",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("new_skill", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _generate(mod, monkeypatch, tmp_path, name, **opts):
    """Запустить main() с переопределённым каталогом скилов, вернуть папку."""
    skills_dir = tmp_path / "skills"
    monkeypatch.setattr(mod, "SKILLS_DIR", skills_dir)
    argv = ["new_skill.py", name]
    for key, value in opts.items():
        argv += [f"--{key}", value]
    monkeypatch.setattr("sys.argv", argv)
    mod.main()
    return skills_dir / mod.normalize_name(name)


def _frontmatter(skill_md):
    content = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?", content, re.DOTALL)
    assert match, "SKILL.md должен начинаться с YAML frontmatter"
    return yaml.safe_load(match.group(1)), content[match.end() :]


# --- чистые функции ---------------------------------------------------------

def test_normalize_name_produces_kebab_case() -> None:
    mod = _load_module()
    assert mod.normalize_name("Daily Briefs Translator") == "daily-briefs-translator"
    assert mod.normalize_name("  Foo__Bar!!Baz  ") == "foo-bar-baz"
    assert mod.normalize_name("already-kebab") == "already-kebab"


def test_normalize_name_rejects_empty_or_garbage() -> None:
    mod = _load_module()
    for bad in ("", "   ", "!!!", "---"):
        with pytest.raises(SystemExit):
            mod.normalize_name(bad)


def test_write_new_refuses_to_overwrite(tmp_path) -> None:
    mod = _load_module()
    target = tmp_path / "f.txt"
    mod.write_new(target, "первый")
    with pytest.raises(SystemExit):
        mod.write_new(target, "второй")
    assert target.read_text(encoding="utf-8") == "первый"


# --- сквозная генерация -----------------------------------------------------

def test_generator_creates_expected_files(monkeypatch, tmp_path) -> None:
    mod = _load_module()
    skill_dir = _generate(mod, monkeypatch, tmp_path, "Sample Skill")
    assert skill_dir.name == "sample-skill"
    for rel in (
        "SKILL.md",
        "skill.yaml",
        "known-exceptions.yaml",
        "examples/good-01.md",
        "examples/good-02.md",
        "examples/good-03.md",
        "examples/anti-01.md",
        "examples/anti-02.md",
    ):
        assert (skill_dir / rel).exists(), f"генератор не создал {rel}"


def test_generated_skill_md_has_valid_shape(monkeypatch, tmp_path) -> None:
    mod = _load_module()
    skill_dir = _generate(mod, monkeypatch, tmp_path, "shape-check")
    frontmatter, body = _frontmatter(skill_dir / "SKILL.md")

    # frontmatter: только разрешённые ключи, name совпадает с папкой и kebab-case
    assert set(frontmatter) <= ALLOWED_FRONTMATTER_KEYS
    assert frontmatter["name"] == "shape-check"
    assert NAME_RE.match(frontmatter["name"])

    # consent gate обязан быть первой секцией body (как требует test_consent_gate)
    headings = [line for line in body.splitlines() if line.startswith("## ")]
    assert headings[0] == "## Согласие На Запуск"
    gate = body.split("## Согласие На Запуск", 1)[1].split("\n## ", 1)[0]
    assert "team skill `shape-check`" in gate
    for phrase in ("без вопроса", "Применить или решить без него?", "выйдите из skill молча"):
        assert phrase in gate

    # контракт логирования сбоев
    assert "## Логирование Сбоев" in body
    assert "known-exceptions.yaml" in body
    assert "exception-log.jsonl" in body
    assert "Raw logs не коммитить" in body


def test_generated_known_exceptions_is_empty_template(monkeypatch, tmp_path) -> None:
    mod = _load_module()
    skill_dir = _generate(mod, monkeypatch, tmp_path, "ke-check")
    data = yaml.safe_load((skill_dir / "known-exceptions.yaml").read_text(encoding="utf-8"))
    assert data == {"exceptions": []}


def test_generated_examples_have_required_sections(monkeypatch, tmp_path) -> None:
    mod = _load_module()
    skill_dir = _generate(mod, monkeypatch, tmp_path, "ex-check")
    for example in (skill_dir / "examples").glob("*.md"):
        text = example.read_text(encoding="utf-8")
        for section in ("## Вход", "## Ожидаемое Поведение", "## Нельзя"):
            assert section in text, f"{example.name} без секции {section}"


def test_generated_registry_has_required_keys_and_threads_options(monkeypatch, tmp_path) -> None:
    mod = _load_module()
    skill_dir = _generate(
        mod, monkeypatch, tmp_path, "reg-check",
        owner="@octocat", summary="Коротко: что делает skill",
    )
    registry = yaml.safe_load((skill_dir / "skill.yaml").read_text(encoding="utf-8"))
    assert REGISTRY_REQUIRED_KEYS <= set(registry)
    assert registry["owner"] == "@octocat"
    assert registry["summary"] == "Коротко: что делает skill"
    assert registry["status"] == "draft"
    # все пути example_files должны реально существовать
    for rel in registry["example_files"]:
        assert (skill_dir / rel).exists(), f"example_files указывает на отсутствующий {rel}"


def test_generator_refuses_existing_skill(monkeypatch, tmp_path) -> None:
    mod = _load_module()
    _generate(mod, monkeypatch, tmp_path, "dup-skill")
    with pytest.raises(SystemExit):
        _generate(mod, monkeypatch, tmp_path, "dup-skill")
