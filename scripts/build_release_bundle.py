#!/usr/bin/env python3
"""Build the validated team-skills release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


SUPPORT_NAMES = (
    "install-team-skills.cmd",
    "install-team-skills.ps1",
    "install-team-skills.command",
    "bootstrap-team-skills.ps1",
    "bootstrap-team-skills.sh",
    "update-team-skills.ps1",
    "update-team-skills.sh",
    "uninstall-team-skills.ps1",
    "uninstall-team-skills.command",
    "team-skills-status.ps1",
    "team-skills-status.command",
    "refresh-team-skills.command",
    "pull-skills.sh",
    "team-skills-registry.py",
    "team-skills-public-key.pem",
)

WINDOWS_POWERSHELL_ASSETS = {
    "install-team-skills.ps1",
    "bootstrap-team-skills.ps1",
    "update-team-skills.ps1",
    "uninstall-team-skills.ps1",
    "team-skills-status.ps1",
}

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
GIT_REGULAR_MODES = {0o100644, 0o100755}
BUILDER_REPO_PATH = PurePosixPath("scripts/build_release_bundle.py")
WINDOWS_INVALID_CHARS = frozenset('<>:"\\|?*')
WINDOWS_RESERVED_STEMS = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def validate_release_source_path(path: PurePosixPath) -> None:
    """Reject generated operating-system and Python cache artifacts."""

    folded_parts = tuple(component.casefold() for component in path.parts)
    folded_name = path.name.casefold()
    if (
        "__pycache__" in folded_parts
        or folded_name == ".ds_store"
        or folded_name.endswith((".pyc", ".pyo"))
    ):
        raise ValueError(f"Release source содержит запрещённый служебный файл: {path}")


@dataclass(frozen=True)
class GitIndexFile:
    repo_path: PurePosixPath
    object_id: str
    git_mode: int
    content: bytes

    @property
    def permissions(self) -> int:
        return self.git_mode & 0o777


def validate_windows_component(component: str) -> None:
    invalid_character = next(
        (
            character
            for character in component
            if character in WINDOWS_INVALID_CHARS or ord(character) < 32
        ),
        None,
    )
    if invalid_character is not None:
        raise ValueError(
            "Путь plugin несовместим с Windows: "
            f"компонент {component!r} содержит {invalid_character!r}"
        )
    if component.endswith((" ", ".")):
        raise ValueError(
            "Путь plugin несовместим с Windows: "
            f"компонент {component!r} оканчивается пробелом или точкой"
        )

    reserved_stem = component.split(".", 1)[0].rstrip(" .").upper()
    if reserved_stem in WINDOWS_RESERVED_STEMS:
        raise ValueError(
            "Путь plugin несовместим с Windows: "
            f"зарезервированный компонент {component!r}"
        )


def validate_portable_paths(paths: list[PurePosixPath]) -> None:
    """Reject names that collapse onto one path on common user filesystems."""

    spellings: dict[str, str] = {}
    for path in sorted(paths, key=lambda item: item.as_posix()):
        for component in path.parts:
            validate_windows_component(component)
        for depth in range(1, len(path.parts) + 1):
            spelling = PurePosixPath(*path.parts[:depth]).as_posix()
            portable_key = unicodedata.normalize("NFC", spelling).casefold()
            previous = spellings.setdefault(portable_key, spelling)
            if previous != spelling:
                raise ValueError(
                    "Пути plugin конфликтуют на файловой системе без учёта "
                    f"регистра: {previous!r} и {spelling!r}"
                )


def _require_git_root(root: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        error = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Не удалось определить корень Git repository: {error}")
    git_root = Path(os.fsdecode(result.stdout.rstrip(b"\r\n"))).resolve()
    if git_root != root:
        raise ValueError(
            f"--root должен указывать на Git worktree root: получено {root}, Git root {git_root}"
        )


def _read_index_blobs(root: Path, metadata: list[tuple[PurePosixPath, str, int]]) -> list[GitIndexFile]:
    object_ids = [object_id for _, object_id, _ in metadata]
    result = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input="".join(f"{object_id}\n" for object_id in object_ids).encode("ascii"),
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        error = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Не удалось прочитать blobs из Git index: {error}")

    cursor = 0
    files: list[GitIndexFile] = []
    for repo_path, expected_object_id, git_mode in metadata:
        header_end = result.stdout.find(b"\n", cursor)
        if header_end < 0:
            raise RuntimeError(f"Git cat-file вернул неполный header для {repo_path}")
        header = result.stdout[cursor:header_end].split()
        cursor = header_end + 1
        if len(header) != 3:
            raise RuntimeError(f"Git cat-file вернул невалидный header для {repo_path}: {header!r}")
        object_id, object_type, raw_size = header
        if object_id.decode("ascii") != expected_object_id or object_type != b"blob":
            raise RuntimeError(f"Git index object для {repo_path} не является ожидаемым blob")
        size = int(raw_size)
        content = result.stdout[cursor : cursor + size]
        cursor += size
        if len(content) != size or result.stdout[cursor : cursor + 1] != b"\n":
            raise RuntimeError(f"Git cat-file вернул неполный blob для {repo_path}")
        cursor += 1
        files.append(
            GitIndexFile(
                repo_path=repo_path,
                object_id=expected_object_id,
                git_mode=git_mode,
                content=content,
            )
        )

    if cursor != len(result.stdout):
        raise RuntimeError("Git cat-file вернул неожиданные данные после последнего blob")
    return files


def git_index_source_files(root: Path, pathspecs: list[Path]) -> list[GitIndexFile]:
    """Read the repository snapshot from Git index, excluding author-mode WIP.

    Untracked and unstaged files are intentionally not release inputs: they are
    author workspace state, not part of a repository/release snapshot.
    """

    root = root.resolve()
    _require_git_root(root)
    relative_pathspecs: list[PurePosixPath] = []
    for pathspec in pathspecs:
        try:
            relative = pathspec.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Источник release находится вне корня репозитория: {pathspec}") from exc
        relative_pathspecs.append(PurePosixPath(*relative.parts))

    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-files",
            "--stage",
            "-z",
            "--",
            *(path.as_posix() for path in relative_pathspecs),
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        error = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Не удалось получить файлы Git index: {error}")

    metadata: list[tuple[PurePosixPath, str, int]] = []
    for raw_record in result.stdout.split(b"\0"):
        if not raw_record:
            continue
        try:
            raw_metadata, raw_path = raw_record.split(b"\t", 1)
            raw_mode, raw_object_id, raw_stage = raw_metadata.split()
        except ValueError as exc:
            raise RuntimeError(f"Git ls-files вернул невалидную запись: {raw_record!r}") from exc
        repo_path = PurePosixPath(os.fsdecode(raw_path))
        validate_release_source_path(repo_path)
        stage = int(raw_stage)
        if stage != 0:
            raise RuntimeError(f"Git index содержит unresolved stage {stage} для {repo_path}")
        git_mode = int(raw_mode, 8)
        if git_mode not in GIT_REGULAR_MODES:
            kind = "symbolic link" if git_mode == 0o120000 else f"mode {raw_mode.decode()}"
            raise ValueError(f"В release разрешены только Git regular files; {repo_path}: {kind}")

        worktree_path = root.joinpath(*repo_path.parts)
        try:
            worktree_mode = worktree_path.lstat().st_mode
        except FileNotFoundError as exc:
            raise RuntimeError(f"Tracked release file отсутствует в worktree: {repo_path}") from exc
        if not stat.S_ISREG(worktree_mode):
            raise ValueError(f"Tracked release file не является regular file в worktree: {repo_path}")
        metadata.append((repo_path, raw_object_id.decode("ascii"), git_mode))

    metadata.sort(key=lambda item: item[0].as_posix())
    return _read_index_blobs(root, metadata)


def resolve_release_commit(root: Path, commit: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Release commit не существует или не является commit: {commit}")
    return result.stdout.decode("ascii").strip()


def commit_blob(root: Path, commit: str, repo_path: PurePosixPath) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{commit}:{repo_path.as_posix()}"],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        error = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(
            f"Release commit {commit} не содержит ожидаемый файл {repo_path}: {error}"
        )
    return result.stdout


def ensure_executed_builder_matches_commit(
    root: Path,
    commit: str,
    executed_builder: Path,
) -> None:
    """Bind the running builder bytes to the commit named in release metadata."""

    root = root.resolve()
    resolved_commit = resolve_release_commit(root, commit)
    expected_builder = root.joinpath(*BUILDER_REPO_PATH.parts)
    actual_builder = Path(os.path.abspath(executed_builder))
    if actual_builder != expected_builder:
        raise RuntimeError(
            "Выполняемый builder находится не по ожидаемому repository path: "
            f"{actual_builder} != {expected_builder}"
        )
    try:
        builder_mode = actual_builder.lstat().st_mode
    except FileNotFoundError as exc:
        raise RuntimeError(f"Выполняемый builder отсутствует: {actual_builder}") from exc
    if not stat.S_ISREG(builder_mode):
        raise RuntimeError(f"Выполняемый builder не является regular file: {actual_builder}")

    expected_content = commit_blob(root, resolved_commit, BUILDER_REPO_PATH)
    if actual_builder.read_bytes() != expected_content:
        raise RuntimeError(
            "Выполняемые worktree-байты builder расходятся с заявленным "
            f"release commit {resolved_commit}: {BUILDER_REPO_PATH}"
        )


def ensure_index_matches_commit(
    root: Path,
    commit: str,
    entries: list[GitIndexFile],
    pathspecs: list[Path],
) -> None:
    relative_pathspecs = [
        path.resolve().relative_to(root).as_posix()
        for path in pathspecs
    ]
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            commit,
            "--",
            *relative_pathspecs,
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        error = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Не удалось прочитать release commit {commit}: {error}")

    commit_state: dict[PurePosixPath, tuple[int, str]] = {}
    for raw_record in result.stdout.split(b"\0"):
        if not raw_record:
            continue
        try:
            raw_metadata, raw_path = raw_record.split(b"\t", 1)
            raw_mode, raw_type, raw_object_id = raw_metadata.split()
        except ValueError as exc:
            raise RuntimeError(f"Git ls-tree вернул невалидную запись: {raw_record!r}") from exc
        if raw_type != b"blob":
            raise ValueError(
                f"Release commit содержит не-file entry: {os.fsdecode(raw_path)} ({raw_type.decode()})"
            )
        commit_state[PurePosixPath(os.fsdecode(raw_path))] = (
            int(raw_mode, 8),
            raw_object_id.decode("ascii"),
        )

    index_state = {
        entry.repo_path: (entry.git_mode, entry.object_id)
        for entry in entries
    }
    if index_state != commit_state:
        changed_paths = sorted(
            path.as_posix()
            for path in set(index_state) | set(commit_state)
            if index_state.get(path) != commit_state.get(path)
        )
        preview = ", ".join(changed_paths[:10])
        if len(changed_paths) > 10:
            preview += f", ... (+{len(changed_paths) - 10})"
        raise RuntimeError(
            f"Git index расходится с release commit {commit} для payload paths: {preview}"
        )


def release_source_files(
    root: Path,
    pathspecs: list[Path],
    commit: str,
) -> tuple[list[GitIndexFile], str]:
    root = root.resolve()
    resolved_commit = resolve_release_commit(root, commit)
    entries = git_index_source_files(root, pathspecs)
    ensure_index_matches_commit(root, resolved_commit, entries, pathspecs)
    return entries, resolved_commit


def copy_git_index_tree(
    *,
    entries: list[GitIndexFile],
    source_root: PurePosixPath,
    destination_root: Path,
) -> dict[PurePosixPath, int]:
    permissions: dict[PurePosixPath, int] = {}
    for entry in entries:
        try:
            relative = entry.repo_path.relative_to(source_root)
        except ValueError:
            continue
        destination = destination_root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(entry.content)
        permissions[relative] = entry.permissions
    return permissions


def write_deterministic_zip_file(
    archive: zipfile.ZipFile,
    source: Path,
    archive_name: PurePosixPath,
    permissions: int,
) -> None:
    info = zipfile.ZipInfo(archive_name.as_posix(), date_time=ZIP_TIMESTAMP)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | permissions) << 16
    archive.writestr(
        info,
        source.read_bytes(),
        compress_type=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    )


def asset_metadata(name: str, path: Path, release_base: str) -> dict[str, str | int]:
    return {
        "name": name,
        "url": f"{release_base}/{name}",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size": path.stat().st_size,
    }


def copy_support_file(source: GitIndexFile, destination: Path) -> None:
    if source.repo_path.name in WINDOWS_POWERSHELL_ASSETS:
        content = source.content.decode("utf-8-sig")
        destination.write_text(content, encoding="utf-8-sig")
    else:
        destination.write_bytes(source.content)
    destination.chmod(source.permissions)


def support_source_path(root: Path, name: str) -> Path:
    if name == "pull-skills.sh":
        return root / "scripts" / name
    return root / "installer" / name


def build_release_bundle(
    *,
    root: Path,
    dist: Path,
    commit: str,
    run_number: str,
    run_attempt: str,
) -> None:
    root = root.resolve()
    plugin_root = root / "plugins" / "team-skills"
    manifest_path = plugin_root / ".codex-plugin" / "plugin.json"
    builder_path = root.joinpath(*BUILDER_REPO_PATH.parts)
    support_paths = [support_source_path(root, name) for name in SUPPORT_NAMES]
    index_entries, commit = release_source_files(
        root,
        [builder_path, plugin_root, *support_paths],
        commit,
    )
    ensure_executed_builder_matches_commit(root, commit, Path(__file__))
    index_by_path = {entry.repo_path: entry for entry in index_entries}
    plugin_root_relative = PurePosixPath(*plugin_root.relative_to(root).parts)
    plugin_entries = [
        entry
        for entry in index_entries
        if entry.repo_path.is_relative_to(plugin_root_relative)
    ]
    validate_portable_paths(
        [entry.repo_path.relative_to(plugin_root_relative) for entry in plugin_entries]
    )

    manifest_relative = PurePosixPath(*manifest_path.relative_to(root).parts)
    if manifest_relative not in index_by_path:
        raise RuntimeError(f"Plugin manifest отсутствует в Git index: {manifest_relative}")
    plugin_manifest = json.loads(index_by_path[manifest_relative].content.decode("utf-8"))

    shutil.rmtree(dist, ignore_errors=True)
    dist.mkdir(parents=True, exist_ok=True)

    short_sha = commit[:7]
    release_id = f"r{run_number}.{run_attempt}-{short_sha}"
    release_tag = f"team-skills-v{release_id}"
    product_version = plugin_manifest["version"]
    runtime_version = f"{product_version}-r.{run_number}.{run_attempt}.{short_sha}"
    release_base = f"https://github.com/kir-kopylov/codex-team-skills/releases/download/{release_tag}"

    release_plugin_root = dist / "bundle-root" / "team-skills"
    plugin_permissions = copy_git_index_tree(
        entries=plugin_entries,
        source_root=plugin_root_relative,
        destination_root=release_plugin_root,
    )
    release_manifest_path = release_plugin_root / ".codex-plugin" / "plugin.json"
    release_plugin_manifest = json.loads(release_manifest_path.read_text(encoding="utf-8"))
    release_plugin_manifest["product_version"] = product_version
    release_plugin_manifest["version"] = runtime_version
    release_plugin_manifest["release_id"] = release_id
    release_plugin_manifest["commit"] = commit
    release_manifest_path.write_text(
        json.dumps(release_plugin_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    bundle_path = dist / "team-skills-bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as archive:
        release_files = sorted(
            (path for path in release_plugin_root.rglob("*") if path.is_file()),
            key=lambda path: path.relative_to(release_plugin_root).as_posix(),
        )
        for path in release_files:
            relative_path = PurePosixPath(*path.relative_to(release_plugin_root).parts)
            archive_name = PurePosixPath("team-skills", *relative_path.parts)
            write_deterministic_zip_file(
                archive,
                path,
                archive_name,
                plugin_permissions[relative_path],
            )
    shutil.rmtree(dist / "bundle-root", ignore_errors=True)

    for name, source_path in zip(SUPPORT_NAMES, support_paths, strict=True):
        source_relative = PurePosixPath(*source_path.relative_to(root).parts)
        source = index_by_path.get(source_relative)
        if source is None:
            raise RuntimeError(f"Support file отсутствует в Git index: {source_relative}")
        copy_support_file(source, dist / name)

    plugin_bundle = asset_metadata("team-skills-bundle.zip", bundle_path, release_base)
    support_files = [asset_metadata(name, dist / name, release_base) for name in SUPPORT_NAMES]
    created_at = datetime.now(timezone.utc).isoformat()
    manifest = {
        "name": "team-skills",
        "product_version": product_version,
        "runtime_version": runtime_version,
        "release_id": release_id,
        "release_tag": release_tag,
        "commit": commit,
        "channel": "stable",
        "minimum_bootstrap_version": "1.0.0",
        "minimum_updater_version": "1.0.0",
        "created_at": created_at,
        "plugin_bundle": plugin_bundle,
        "support_files": support_files,
    }
    (dist / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    latest = {
        "name": "team-skills",
        "channel": "stable",
        "release_id": release_id,
        "release_tag": release_tag,
        "runtime_version": runtime_version,
        "commit": commit,
        "manifest_url": f"{release_base}/manifest.json",
        "created_at": created_at,
    }
    (dist / "latest.json").write_text(
        json.dumps(latest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def env_or_default(name: str, default: str) -> str:
    return os.environ.get(name) or default


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dist", type=Path)
    parser.add_argument("--commit", default=env_or_default("GITHUB_SHA_VALUE", env_or_default("GITHUB_SHA", "HEAD")))
    parser.add_argument("--run-number", default=env_or_default("GITHUB_RUN_NUMBER_VALUE", env_or_default("GITHUB_RUN_NUMBER", "0")))
    parser.add_argument(
        "--run-attempt",
        default=env_or_default("GITHUB_RUN_ATTEMPT_VALUE", env_or_default("GITHUB_RUN_ATTEMPT", "0")),
    )
    args = parser.parse_args()

    root = args.root.resolve()
    dist = args.dist.resolve() if args.dist else root / "dist"
    build_release_bundle(
        root=root,
        dist=dist,
        commit=args.commit,
        run_number=args.run_number,
        run_attempt=args.run_attempt,
    )


if __name__ == "__main__":
    main()
