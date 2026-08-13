#!/usr/bin/env python3
"""Статически проверяет подготовленную папку навыка и собирает минимальный ZIP."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import zipfile


MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 200
MAX_PACKAGE_BYTES = 30 * 1024 * 1024
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_FIELD_RE = re.compile(r"^([A-Za-z0-9_-]+):[ \t]*(.*)$")
XML_TAG_RE = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
PATH_TOKEN_RE = re.compile(r"[^\s`\"'<>()[\]{}]+")
MANAGED_ROOTS = ("scripts", "references", "assets", "resources")
RESERVED_NAME_WORDS = ("anthropic", "claude")
BLOCKED_SERVICE_NAMES = {"__MACOSX", "__pycache__"}
TRAILING_REFERENCE_PUNCTUATION = ".,;:!?)]}«»"
YAML_NON_STRING_WORDS = {"~", "null", "true", "false", "yes", "no", "on", "off", ".nan", ".inf", "+.inf", "-.inf"}
YAML_NUMBER_RE = re.compile(
    r"[-+]?(?:(?:0[xob][0-9a-f_]+)|(?:\d[\d_]*(?::\d[\d_]*)+)|(?:\d[\d_]*(?:\.[\d_]*)?(?:e[-+]?\d+)?)|(?:\.\d[\d_]*(?:e[-+]?\d+)?))",
    re.IGNORECASE,
)
YAML_DATE_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}(?:[Tt ]\S+)?")

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("private key", re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    ("OpenAI-style token", re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(rb"\b(?:gh[opsur]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("GitLab token", re.compile(rb"\bglpat-[A-Za-z0-9_-]{16,}\b")),
    ("AWS access key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
)
PERSONAL_PATH_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    (
        "Unix personal absolute path",
        re.compile(rb"(?<![A-Za-z0-9])/(?:Users|home)/[^/\s`\"'<>]+(?:/[^\s`\"'<>]*)?"),
    ),
    (
        "Windows personal absolute path",
        re.compile(rb"(?i)(?<![A-Za-z0-9])[A-Z]:\\Users\\[^\\\s`\"'<>]+(?:\\[^\s`\"'<>]*)?"),
    ),
)


class PackageError(RuntimeError):
    """Ошибка, при которой архив нельзя считать безопасно подготовленным."""


@dataclass(frozen=True)
class PackageFile:
    relative_path: PurePosixPath
    data: bytes
    mode: int


@dataclass(frozen=True)
class BuildResult:
    archive: Path
    files: tuple[str, ...]


def _parse_inline_scalar(raw_value: str, field: str) -> str:
    value = raw_value.strip()
    if not value or value in {"|", ">", "|-", ">-", "|+", ">+"}:
        raise PackageError(f"Поле {field} должно быть непустой однострочной строкой")

    if value[0] == '"':
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise PackageError(f"Поле {field} содержит некорректную строку") from exc
        if not isinstance(parsed, str):
            raise PackageError(f"Поле {field} должно быть строкой")
        return parsed

    if value[0] == "'":
        if len(value) < 2 or value[-1] != "'":
            raise PackageError(f"Поле {field} содержит некорректную строку")
        inner = value[1:-1]
        if "'" in inner.replace("''", ""):
            raise PackageError(f"Поле {field} содержит некорректную строку")
        return inner.replace("''", "'")

    lowered = value.lower()
    if (
        lowered in YAML_NON_STRING_WORDS
        or YAML_NUMBER_RE.fullmatch(value)
        or YAML_DATE_RE.fullmatch(value)
        or value[0] in "[{!&*"
        or value in {"---", "..."}
        or ": " in value
        or " #" in value
    ):
        raise PackageError(f"Поле {field} должно быть YAML-строкой, а не другим типом")

    return value


def read_metadata(skill_md: Path) -> tuple[str, str, str]:
    try:
        content = skill_md.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PackageError("SKILL.md должен быть корректным UTF-8") from exc
    except OSError as exc:
        raise PackageError(f"Не удалось прочитать SKILL.md: {exc}") from exc

    lines = content.splitlines()
    if not lines or lines[0] != "---":
        raise PackageError("SKILL.md должен начинаться с YAML frontmatter")
    try:
        closing_index = lines.index("---", 1)
    except ValueError as exc:
        raise PackageError("В SKILL.md не закрыт YAML frontmatter") from exc

    values: dict[str, str] = {}
    current_field: str | None = None
    for raw_line in lines[1:closing_index]:
        if not raw_line or raw_line.lstrip().startswith("#"):
            continue
        if raw_line.startswith((" ", "\t")):
            if current_field in {"name", "description"}:
                raise PackageError(f"Поле {current_field} должно занимать ровно одну строку frontmatter")
            continue
        match = FRONTMATTER_FIELD_RE.fullmatch(raw_line)
        if not match:
            raise PackageError("YAML frontmatter содержит неподдерживаемую строку")
        field, raw_value = match.groups()
        current_field = field
        if field not in {"name", "description"}:
            continue
        if field in values:
            raise PackageError(f"Поле {field} в frontmatter повторяется")
        values[field] = _parse_inline_scalar(raw_value, field)

    for field in ("name", "description"):
        if not values.get(field):
            raise PackageError(f"В frontmatter отсутствует однострочное поле {field}")

    name = values["name"]
    description = values["description"]
    for field, value in (("name", name), ("description", description)):
        if value != value.strip():
            raise PackageError(f"Поле {field} не должно начинаться или заканчиваться пробелом")
        if "\n" in value or "\r" in value:
            raise PackageError(f"Поле {field} должно быть однострочной строкой")
    if len(name) > MAX_NAME_LENGTH:
        raise PackageError(f"Поле name длиннее {MAX_NAME_LENGTH} символов")
    if not NAME_RE.fullmatch(name):
        raise PackageError("Поле name допускает только lowercase letters, digits и hyphens")
    if any(word in name for word in RESERVED_NAME_WORDS):
        raise PackageError("Поле name содержит зарезервированное слово")
    if len(description) > MAX_DESCRIPTION_LENGTH:
        raise PackageError(f"Поле description длиннее {MAX_DESCRIPTION_LENGTH} символов")
    if XML_TAG_RE.search(description):
        raise PackageError("Поле description не должно содержать XML-теги")

    return name, description, content


def _validate_component(name: str, relative_path: PurePosixPath) -> None:
    if (
        not name
        or name in {".", ".."}
        or "\\" in name
        or ":" in name
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise PackageError(f"Небезопасный путь в пакете: {relative_path.as_posix()}")
    if name.startswith(".") or name in BLOCKED_SERVICE_NAMES:
        raise PackageError(f"Скрытый или служебный путь запрещён: {relative_path.as_posix()}")


def _scan_file_content(relative_path: PurePosixPath, data: bytes) -> None:
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            raise PackageError(f"Файл {relative_path.as_posix()} содержит очевидный secret ({label})")
    for label, pattern in PERSONAL_PATH_PATTERNS:
        if pattern.search(data):
            raise PackageError(f"Файл {relative_path.as_posix()} содержит персональный абсолютный путь ({label})")


def collect_files(source: Path) -> tuple[PackageFile, ...]:
    collected: list[PackageFile] = []
    total_size = 0
    stack: list[tuple[Path, PurePosixPath]] = [(source, PurePosixPath())]

    while stack:
        current, current_relative = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda entry: entry.name)
        except OSError as exc:
            raise PackageError(f"Не удалось прочитать каталог {current_relative.as_posix() or '.'}: {exc}") from exc

        directories: list[tuple[Path, PurePosixPath]] = []
        for entry in entries:
            relative = current_relative / entry.name
            _validate_component(entry.name, relative)
            if entry.is_symlink():
                raise PackageError(f"Symlink запрещён: {relative.as_posix()}")
            try:
                if entry.is_dir(follow_symlinks=False):
                    directories.append((Path(entry.path), relative))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    raise PackageError(f"Допустимы только обычные файлы: {relative.as_posix()}")
                path = Path(entry.path)
                mode = 0o755 if path.stat(follow_symlinks=False).st_mode & 0o111 else 0o644
                data = path.read_bytes()
            except OSError as exc:
                raise PackageError(f"Не удалось прочитать {relative.as_posix()}: {exc}") from exc

            total_size += len(data)
            if total_size > MAX_PACKAGE_BYTES:
                raise PackageError("Общий объём файлов превышает 30 МБ")
            _scan_file_content(relative, data)
            collected.append(PackageFile(relative, data, mode))

        stack.extend(reversed(directories))

    collected.sort(key=lambda item: item.relative_path.as_posix())
    return tuple(collected)


def _managed_reference_tokens(skill_content: str) -> set[str]:
    references: set[str] = set()
    for match in PATH_TOKEN_RE.finditer(skill_content):
        original = match.group(0).strip(TRAILING_REFERENCE_PUNCTUATION)
        if not original or "://" in original:
            continue
        normalized = original.replace("\\", "/")
        positions = [
            normalized.find(f"{root}/")
            for root in MANAGED_ROOTS
            if f"{root}/" in normalized
        ]
        if not positions:
            continue
        position = min(positions)
        if position > 0 and normalized[position - 1] != "/":
            continue
        references.add(original.split("#", 1)[0].rstrip(TRAILING_REFERENCE_PUNCTUATION))
    return references


def validate_references(skill_content: str, files: tuple[PackageFile, ...]) -> None:
    available = {item.relative_path.as_posix() for item in files}
    for original in sorted(_managed_reference_tokens(skill_content)):
        if "\\" in original:
            raise PackageError(f"В SKILL.md упомянут отсутствующий или небезопасный путь: {original}")
        path_text = original
        if path_text.startswith("/") or path_text.startswith("../") or path_text.startswith("./../"):
            raise PackageError(f"В SKILL.md упомянут отсутствующий или небезопасный путь: {path_text}")
        normalized = path_text[2:] if path_text.startswith("./") else path_text
        path = PurePosixPath(normalized)
        if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] not in MANAGED_ROOTS:
            raise PackageError(f"В SKILL.md упомянут отсутствующий или небезопасный путь: {path_text}")
        if normalized.endswith("/"):
            if not any(candidate.startswith(normalized) for candidate in available):
                raise PackageError(f"В SKILL.md упомянут отсутствующий или небезопасный путь: {path_text}")
        elif normalized not in available:
            raise PackageError(f"В SKILL.md упомянут отсутствующий или небезопасный путь: {path_text}")


def _safe_output_path(source: Path, output: Path) -> Path:
    output = Path(os.path.abspath(output.expanduser()))
    try:
        resolved_parent = output.parent.resolve(strict=False)
    except OSError as exc:
        raise PackageError(f"Не удалось проверить каталог результата: {exc}") from exc

    resolved_output = resolved_parent / output.name
    if resolved_output == source or source in resolved_output.parents:
        raise PackageError("Output нельзя создавать внутри исходной папки")
    try:
        resolved_parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PackageError(f"Не удалось подготовить каталог результата: {exc}") from exc
    if os.path.lexists(resolved_output):
        raise PackageError("Output уже существует; перезапись запрещена")
    return resolved_output


def _zip_info(archive_name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build_archive(source: Path, output: Path) -> BuildResult:
    source_input = source.expanduser()
    if source_input.is_symlink():
        raise PackageError("Исходная папка не должна быть symlink")
    try:
        source = source_input.resolve(strict=True)
    except OSError as exc:
        raise PackageError(f"Исходная папка недоступна: {exc}") from exc
    if not source.is_dir():
        raise PackageError("Параметр --source должен указывать на папку")

    skill_md = source / "SKILL.md"
    if not skill_md.is_file() or skill_md.is_symlink():
        raise PackageError("В исходной папке нужен обычный файл SKILL.md")

    name, _description, skill_content = read_metadata(skill_md)
    files = collect_files(source)
    if not files or "SKILL.md" not in {item.relative_path.as_posix() for item in files}:
        raise PackageError("Пакет не содержит SKILL.md")
    validate_references(skill_content, files)

    output = _safe_output_path(source, output)
    expected_names = [f"{name}/{item.relative_path.as_posix()}" for item in files]
    created = False
    try:
        with output.open("xb") as raw_stream:
            created = True
            with zipfile.ZipFile(raw_stream, "w", allowZip64=False) as archive:
                for item, archive_name in zip(files, expected_names, strict=True):
                    archive.writestr(_zip_info(archive_name, item.mode), item.data, compresslevel=9)

        if output.stat().st_size > MAX_PACKAGE_BYTES:
            raise PackageError("Итоговый ZIP превышает 30 МБ")

        with zipfile.ZipFile(output, "r") as archive:
            actual_names = archive.namelist()
            if actual_names != expected_names or len(actual_names) != len(set(actual_names)):
                raise PackageError("Состав ZIP не совпал с подготовленной папкой")
            if any(PurePosixPath(name_in_zip).parts[0] != name for name_in_zip in actual_names):
                raise PackageError("ZIP должен содержать ровно одну корневую папку")
            bad_file = archive.testzip()
            if bad_file is not None:
                raise PackageError(f"Повреждена запись ZIP: {bad_file}")

        return BuildResult(
            archive=output,
            files=tuple(item.relative_path.as_posix() for item in files),
        )
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise PackageError(f"Не удалось создать или проверить ZIP: {exc}") from exc
    finally:
        if created and output.exists() and sys.exc_info()[0] is not None:
            output.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Проверяет подготовленную папку навыка и создаёт ZIP без загрузки в Claude."
    )
    parser.add_argument("--source", type=Path, required=True, help="Подготовленная папка навыка")
    parser.add_argument("--output", type=Path, required=True, help="Новый путь итогового ZIP")
    return parser


def _print_success(result: BuildResult) -> None:
    print("Статус: STATIC_VALIDATED")
    print(f"Архив: {result.archive}")
    print(f"Состав: {', '.join(result.files)}")
    print("Адаптации: не выполнялись упаковщиком; их перечисляет вызывающий skill")
    print("Загрузка в Claude: не выполнялась")


def _print_blocked(reason: str) -> None:
    print("Статус: BLOCKED", file=sys.stderr)
    print("Архив: —", file=sys.stderr)
    print("Состав: —", file=sys.stderr)
    print("Адаптации: не выполнялись упаковщиком", file=sys.stderr)
    print("Загрузка в Claude: не выполнялась", file=sys.stderr)
    print(f"Причина: {reason}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = build_archive(args.source, args.output)
    except PackageError as exc:
        _print_blocked(str(exc))
        return 1
    _print_success(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
