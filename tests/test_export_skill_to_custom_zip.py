from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import zipfile

import pytest

from conftest import ROOT


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "export-skill-to-custom-zip"
SCRIPT_PATH = SKILL_DIR / "scripts" / "build_custom_skill_zip.py"


def load_packager():
    spec = importlib.util.spec_from_file_location("build_custom_skill_zip", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def packager():
    return load_packager()


def write_skill(
    parent: Path,
    *,
    name: str = "forensic-auditor",
    description: str = "Проверяет сложные решения перед их внедрением.",
    body: str = "# Инструкция\n\nПроверь необходимость механизма.",
) -> Path:
    source = parent / "prepared"
    source.mkdir()
    quoted_description = json.dumps(description, ensure_ascii=False)
    (source / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {quoted_description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return source


def snapshot(source: Path) -> dict[str, bytes]:
    return {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }


def test_minimal_archive_has_exact_root_and_unchanged_source(tmp_path: Path, packager) -> None:
    source = write_skill(tmp_path)
    before = snapshot(source)
    output = tmp_path / "dist" / "forensic-auditor-claude-custom.zip"

    result = packager.build_archive(source, output)

    assert result.files == ("SKILL.md",)
    assert snapshot(source) == before
    assert not hasattr(result, "sha256")
    with zipfile.ZipFile(output) as archive:
        assert archive.namelist() == ["forensic-auditor/SKILL.md"]
        assert archive.testzip() is None


def test_referenced_resource_is_required_and_preserved(tmp_path: Path, packager) -> None:
    source = write_skill(
        tmp_path,
        body="# Инструкция\n\nПеред работой прочитай `assets/rules.txt`.",
    )
    resource = source / "assets" / "rules.txt"
    resource.parent.mkdir()
    resource.write_text("Проверяй evidence до вывода.\n", encoding="utf-8")

    result = packager.build_archive(source, tmp_path / "with-resource.zip")

    assert result.files == ("SKILL.md", "assets/rules.txt")
    with zipfile.ZipFile(result.archive) as archive:
        assert archive.namelist() == [
            "forensic-auditor/SKILL.md",
            "forensic-auditor/assets/rules.txt",
        ]


def test_cli_reports_static_validation_without_claiming_upload(tmp_path: Path, packager, capsys) -> None:
    source = write_skill(tmp_path)
    output = tmp_path / "result.zip"

    assert packager.main(["--source", str(source), "--output", str(output)]) == 0

    stdout = capsys.readouterr().out
    assert "Статус: STATIC_VALIDATED" in stdout
    assert "Состав: SKILL.md" in stdout
    assert "SHA-256" not in stdout
    assert "Адаптации" not in stdout
    assert stdout.rstrip().endswith("Загрузка в Claude: не выполнялась")


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("Bad_name", "Корректное описание."),
        ("a" * 65, "Корректное описание."),
        ("claude-helper", "Корректное описание."),
        ("anthropic-helper", "Корректное описание."),
        ("valid-name", "x" * 201),
        ("valid-name", "Описание с <tag> внутри."),
    ],
)
def test_metadata_limits_are_fail_closed(tmp_path: Path, packager, name: str, description: str) -> None:
    source = write_skill(tmp_path, name=name, description=description)

    with pytest.raises(packager.PackageError):
        packager.build_archive(source, tmp_path / "invalid.zip")

    assert not (tmp_path / "invalid.zip").exists()


def test_multiline_description_is_rejected(tmp_path: Path, packager) -> None:
    source = tmp_path / "prepared"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: valid-name\ndescription: |\n  Многострочное описание\n---\n\n# Инструкция\n",
        encoding="utf-8",
    )

    with pytest.raises(packager.PackageError, match="однострочной"):
        packager.build_archive(source, tmp_path / "invalid.zip")


@pytest.mark.parametrize(
    ("name_value", "description_value"),
    [
        ('"valid-name "', '"Корректное описание."'),
        ('"valid-name"', '"' + "x" * 200 + ' "'),
        ('"valid-name"', '"line1\\nline2"'),
    ],
)
def test_quoted_metadata_is_not_silently_normalized(
    tmp_path: Path,
    packager,
    name_value: str,
    description_value: str,
) -> None:
    source = tmp_path / "prepared"
    source.mkdir()
    (source / "SKILL.md").write_text(
        f"---\nname: {name_value}\ndescription: {description_value}\n---\n\n# Инструкция\n",
        encoding="utf-8",
    )

    with pytest.raises(packager.PackageError):
        packager.build_archive(source, tmp_path / "invalid.zip")


@pytest.mark.parametrize(
    ("name_value", "description_value"),
    [
        ("123", '"Корректное описание."'),
        ("2026-08-05", '"Корректное описание."'),
        ("valid-name", "true"),
        ("valid-name", "1."),
        ("valid-name", "[не строка]"),
    ],
)
def test_unquoted_yaml_non_strings_are_rejected(
    tmp_path: Path,
    packager,
    name_value: str,
    description_value: str,
) -> None:
    source = tmp_path / "prepared"
    source.mkdir()
    (source / "SKILL.md").write_text(
        f"---\nname: {name_value}\ndescription: {description_value}\n---\n\n# Инструкция\n",
        encoding="utf-8",
    )

    with pytest.raises(packager.PackageError, match="YAML-строкой"):
        packager.build_archive(source, tmp_path / "invalid.zip")


def test_skill_md_must_be_utf8(tmp_path: Path, packager) -> None:
    source = tmp_path / "prepared"
    source.mkdir()
    (source / "SKILL.md").write_bytes(b"---\nname: valid-name\ndescription: \xff\n---\n")

    with pytest.raises(packager.PackageError, match="UTF-8"):
        packager.build_archive(source, tmp_path / "invalid.zip")


def test_indented_description_continuation_is_rejected(tmp_path: Path, packager) -> None:
    source = tmp_path / "prepared"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: valid-name\ndescription: Первая строка\n  <tag> вторая строка\n---\n\n# Инструкция\n",
        encoding="utf-8",
    )

    with pytest.raises(packager.PackageError, match="ровно одну строку"):
        packager.build_archive(source, tmp_path / "invalid.zip")


def test_total_size_limit_is_enforced(tmp_path: Path, packager, monkeypatch) -> None:
    source = write_skill(tmp_path)
    current_size = sum(len(data) for data in snapshot(source).values())
    monkeypatch.setattr(packager, "MAX_PACKAGE_BYTES", current_size)
    (source / "extra.bin").write_bytes(b"x")

    with pytest.raises(packager.PackageError, match="30 МБ"):
        packager.build_archive(source, tmp_path / "too-large.zip")


@pytest.mark.parametrize("managed_root", ["scripts", "references", "assets", "resources"])
def test_missing_referenced_file_is_blocked(tmp_path: Path, packager, managed_root: str) -> None:
    missing_path = f"{managed_root}/missing.txt"
    source = write_skill(
        tmp_path,
        body=f"# Инструкция\n\nПрочитай `{missing_path}` перед работой.",
    )

    with pytest.raises(packager.PackageError, match=missing_path):
        packager.build_archive(source, tmp_path / "missing.zip")


def test_reference_fragment_resolves_to_packaged_file(tmp_path: Path, packager) -> None:
    source = write_skill(
        tmp_path,
        body="# Инструкция\n\nПрочитай `references/rules.md#проверка`.",
    )
    reference = source / "references" / "rules.md"
    reference.parent.mkdir()
    reference.write_text("# Проверка\n", encoding="utf-8")

    result = packager.build_archive(source, tmp_path / "fragment.zip")

    assert result.files == ("SKILL.md", "references/rules.md")


@pytest.mark.parametrize(
    "unsafe_reference",
    [
        "../scripts/missing.py",
        "./../scripts/missing.py",
        "/scripts/missing.py",
        "/tmp/scripts/missing.py",
        r"scripts\missing.py",
        "scripts/../SKILL.md",
        "scripts/",
    ],
)
def test_unsafe_or_missing_managed_paths_are_blocked(
    tmp_path: Path,
    packager,
    unsafe_reference: str,
) -> None:
    source = write_skill(
        tmp_path,
        body=f"# Инструкция\n\nИспользуй `{unsafe_reference}`.",
    )

    with pytest.raises(packager.PackageError, match="небезопасный путь"):
        packager.build_archive(source, tmp_path / "unsafe-reference.zip")


def test_bare_managed_directory_reference_requires_packaged_files(tmp_path: Path, packager) -> None:
    source = write_skill(
        tmp_path,
        body="# Инструкция\n\nВыбери подходящий файл из `scripts/`.",
    )
    script = source / "scripts" / "run.py"
    script.parent.mkdir()
    script.write_text("print('готово')\n", encoding="utf-8")

    result = packager.build_archive(source, tmp_path / "directory-reference.zip")

    assert result.files == ("SKILL.md", "scripts/run.py")


def test_executable_bit_is_preserved_for_required_script(tmp_path: Path, packager) -> None:
    source = write_skill(
        tmp_path,
        body="# Инструкция\n\nЗапусти `scripts/run.sh`.",
    )
    script = source / "scripts" / "run.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/sh\nprintf 'готово\\n'\n", encoding="utf-8")
    script.chmod(0o755)
    if os.name == "nt" or not script.stat().st_mode & 0o111:
        pytest.skip("executable-bit недоступен на этой файловой системе")

    result = packager.build_archive(source, tmp_path / "executable.zip")

    with zipfile.ZipFile(result.archive) as archive:
        mode = archive.getinfo("forensic-auditor/scripts/run.sh").external_attr >> 16
    assert mode & 0o777 == 0o755


@pytest.mark.parametrize("hidden_path", [".DS_Store", "__MACOSX/item.txt", "nested/.service"])
def test_hidden_service_paths_are_blocked(tmp_path: Path, packager, hidden_path: str) -> None:
    source = write_skill(tmp_path)
    path = source / hidden_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("служебный файл", encoding="utf-8")

    with pytest.raises(packager.PackageError, match="Скрытый|служебный"):
        packager.build_archive(source, tmp_path / "hidden.zip")


def test_control_character_in_path_is_blocked(tmp_path: Path, packager) -> None:
    source = write_skill(tmp_path)
    path = source / "bad\tname.txt"
    try:
        path.write_text("данные", encoding="utf-8")
    except OSError as exc:
        pytest.skip(f"control-character filename недоступен: {exc}")

    with pytest.raises(packager.PackageError, match="Небезопасный путь"):
        packager.build_archive(source, tmp_path / "unsafe-name.zip")


def test_symlink_is_blocked(tmp_path: Path, packager) -> None:
    source = write_skill(tmp_path)
    target = source / "target.txt"
    target.write_text("данные", encoding="utf-8")
    link = source / "link.txt"
    try:
        link.symlink_to(target.name)
    except OSError as exc:
        pytest.skip(f"symlink недоступен: {exc}")

    with pytest.raises(packager.PackageError, match="Symlink"):
        packager.build_archive(source, tmp_path / "symlink.zip")


@pytest.mark.parametrize(
    "unsafe_content",
    [
        "sk-" + "A" * 24,
        "/Users/example/Documents/private.txt",
        r"C:\Users\example\Documents\private.txt",
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_secrets_and_personal_paths_are_blocked(tmp_path: Path, packager, unsafe_content: str) -> None:
    source = write_skill(tmp_path)
    (source / "unsafe.txt").write_text(unsafe_content, encoding="utf-8")

    with pytest.raises(packager.PackageError, match="secret|абсолютный путь"):
        packager.build_archive(source, tmp_path / "unsafe.zip")


def test_existing_output_is_never_overwritten(tmp_path: Path, packager) -> None:
    source = write_skill(tmp_path)
    output = tmp_path / "existing.zip"
    output.write_bytes(b"keep-me")

    with pytest.raises(packager.PackageError, match="перезапись запрещена"):
        packager.build_archive(source, output)

    assert output.read_bytes() == b"keep-me"


def test_output_inside_source_is_blocked(tmp_path: Path, packager) -> None:
    source = write_skill(tmp_path)
    forbidden_parent = source / "new-output-dir"

    with pytest.raises(packager.PackageError, match="внутри исходной папки"):
        packager.build_archive(source, forbidden_parent / "result.zip")

    assert not forbidden_parent.exists()


def test_blocked_cli_uses_honest_result_contract(tmp_path: Path, packager, capsys) -> None:
    source = write_skill(tmp_path, name="claude-helper")

    assert packager.main(["--source", str(source), "--output", str(tmp_path / "bad.zip")]) == 1

    stderr = capsys.readouterr().err
    assert "Статус: BLOCKED" in stderr
    assert "Причина:" in stderr
    assert "SHA-256" not in stderr
    assert "—" not in stderr
    assert "Загрузка в Claude: не выполнялась" in stderr


def test_skill_contract_keeps_export_minimal_and_out_of_scope_actions_separate() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    required_phrases = [
        "Не добавляйте автоматически `LICENSE.txt`",
        "не переименовывайте его молча",
        "Claude Code не является целевой поверхностью",
        "`scripts/`, `references/`, `assets/` или `resources/`",
        "исходная папка после выполнения байтово не изменилась",
        "Загрузка в Claude: не выполнялась",
        "https://support.claude.com/en/articles/12512198-how-to-create-custom-skills",
        "https://platform.claude.com/docs/en/build-with-claude/skills-guide",
    ]
    for phrase in required_phrases:
        assert phrase in content

    assert not (SKILL_DIR / "references").exists()
    assert not (SKILL_DIR / "assets").exists()
    assert not (SKILL_DIR / "agents" / "openai.yaml").exists()
