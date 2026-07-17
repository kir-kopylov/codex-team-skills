from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath
from types import ModuleType

import pytest
import yaml

from conftest import ROOT


CONTRACT_PATH = ROOT / "runtime-contract.yaml"
CONTRACT = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
RUNTIMES = {runtime["id"]: runtime for runtime in CONTRACT["runtimes"]}
CODEX_RUNTIME = RUNTIMES["codex"]
CLAUDE_RUNTIME = RUNTIMES["claude_code"]
CLAUDE_SYNC = CLAUDE_RUNTIME["delivery"]["legacy_sync"]

BUILD_SCRIPT = ROOT / CODEX_RUNTIME["delivery"]["builder"]
SYNC_SCRIPT = ROOT / CLAUDE_SYNC["script"]
SKILLS_DIR = ROOT / CONTRACT["shared"]["skills"]
ROOT_SYNC_METADATA = {".last-sync", ".sync.log"}


def load_build_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_release_bundle", BUILD_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_dist(destination: Path) -> Path:
    commit = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
            "--root",
            str(ROOT),
            "--dist",
            str(destination),
            "--commit",
            commit,
            "--run-number",
            "123",
            "--run-attempt",
            "2",
        ],
        cwd=ROOT,
        check=True,
    )
    return destination


def git_index_records(pathspec: Path) -> list[tuple[PurePosixPath, str, int]]:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "ls-files",
            "--stage",
            "-z",
            "--",
            pathspec.relative_to(ROOT).as_posix(),
        ],
        check=True,
        capture_output=True,
    )
    records: list[tuple[PurePosixPath, str, int]] = []
    for raw_record in result.stdout.split(b"\0"):
        if not raw_record:
            continue
        raw_metadata, raw_path = raw_record.split(b"\t", 1)
        raw_mode, raw_object_id, raw_stage = raw_metadata.split()
        assert raw_stage == b"0", f"unresolved Git index entry: {raw_record!r}"
        records.append(
            (
                PurePosixPath(os.fsdecode(raw_path)),
                raw_object_id.decode("ascii"),
                int(raw_mode, 8),
            )
        )
    return sorted(records)


def add_parent_directories(
    fingerprint: dict[str, tuple[str, str]],
    relative_path: PurePosixPath,
) -> None:
    for parent in relative_path.parents:
        if parent == PurePosixPath("."):
            break
        fingerprint.setdefault(parent.as_posix(), ("dir", ""))


def source_snapshot() -> tuple[dict[str, tuple[str, str]], dict[str, int]]:
    fingerprint: dict[str, tuple[str, str]] = {}
    permissions: dict[str, int] = {}
    blob_cache: dict[str, bytes] = {}
    skills_relative = PurePosixPath(*SKILLS_DIR.relative_to(ROOT).parts)

    for repo_path, object_id, git_mode in git_index_records(SKILLS_DIR):
        relative_path = repo_path.relative_to(skills_relative)
        add_parent_directories(fingerprint, relative_path)
        if object_id not in blob_cache:
            blob_cache[object_id] = subprocess.run(
                ["git", "-C", str(ROOT), "cat-file", "blob", object_id],
                check=True,
                capture_output=True,
            ).stdout
        fingerprint[relative_path.as_posix()] = (
            "file",
            hashlib.sha256(blob_cache[object_id]).hexdigest(),
        )
        permissions[relative_path.as_posix()] = git_mode & 0o777

    return fingerprint, permissions


def is_runtime_metadata(relative_path: PurePosixPath) -> bool:
    if len(relative_path.parts) == 1 and relative_path.name in ROOT_SYNC_METADATA:
        return True
    return len(relative_path.parts) == 2 and relative_path.name == ".team-skill"


def filesystem_fingerprint(
    root: Path,
    *,
    exclude_runtime_metadata: bool = False,
) -> dict[str, tuple[str, str]]:
    fingerprint: dict[str, tuple[str, str]] = {}
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative_path = PurePosixPath(*path.relative_to(root).parts)
        if exclude_runtime_metadata and is_runtime_metadata(relative_path):
            continue

        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            value = ("dir", "")
        elif stat.S_ISREG(mode):
            value = ("file", hashlib.sha256(path.read_bytes()).hexdigest())
        elif stat.S_ISLNK(mode):
            value = ("symlink", os.readlink(path))
        else:
            value = ("special", oct(mode))
        fingerprint[relative_path.as_posix()] = value
    return fingerprint


def zip_skill_snapshot(
    bundle: Path,
) -> tuple[dict[str, tuple[str, str]], dict[str, int]]:
    fingerprint: dict[str, tuple[str, str]] = {}
    permissions: dict[str, int] = {}
    prefix = PurePosixPath("team-skills", "skills")

    with zipfile.ZipFile(bundle) as archive:
        for entry in archive.infolist():
            archive_path = PurePosixPath(entry.filename)
            try:
                relative_path = archive_path.relative_to(prefix)
            except ValueError:
                continue
            if entry.is_dir():
                continue
            add_parent_directories(fingerprint, relative_path)
            unix_mode = entry.external_attr >> 16
            assert stat.S_IFMT(unix_mode) == stat.S_IFREG
            fingerprint[relative_path.as_posix()] = (
                "file",
                hashlib.sha256(archive.read(entry)).hexdigest(),
            )
            permissions[relative_path.as_posix()] = stat.S_IMODE(unix_mode)

    return fingerprint, permissions


def git_index_blob(path: Path) -> bytes:
    relative = path.relative_to(ROOT).as_posix()
    return subprocess.run(
        ["git", "-C", str(ROOT), "show", f":{relative}"],
        check=True,
        capture_output=True,
    ).stdout


@pytest.mark.skipif(shutil.which("bash") is None, reason="нужен bash для проверки Claude folder-sync")
def test_codex_bundle_and_released_claude_sync_deliver_identical_skill_trees(
    tmp_path: Path,
) -> None:
    assert BUILD_SCRIPT.is_file()
    assert SYNC_SCRIPT.is_file()
    dist = build_dist(tmp_path / "dist")
    bundle = dist / "team-skills-bundle.zip"

    expected, expected_permissions = source_snapshot()
    archived, archived_permissions = zip_skill_snapshot(bundle)
    assert archived == expected
    assert archived_permissions == expected_permissions
    assert any(mode & 0o111 for mode in expected_permissions.values()), (
        "mode parity assertion must exercise at least one executable skill file"
    )

    codex_root = tmp_path / "codex"
    with zipfile.ZipFile(bundle) as archive:
        archive.extractall(codex_root)
    codex_skills = codex_root / "team-skills" / "skills"

    released_sync = dist / SYNC_SCRIPT.name
    assert released_sync.read_bytes() == git_index_blob(SYNC_SCRIPT)
    claude_skills = tmp_path / "claude-skills"
    claude_skills.mkdir()
    sync_log = claude_skills / ".sync.log"
    env = os.environ.copy()
    env["TEAM_SKILLS_PULL"] = "0"
    env[CLAUDE_SYNC["source_env"]] = str(codex_skills)
    env[CLAUDE_SYNC["destination_env"]] = str(claude_skills)
    with sync_log.open("w", encoding="utf-8") as log_stream:
        subprocess.run(
            ["bash", str(released_sync)],
            cwd=dist,
            env=env,
            check=True,
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            text=True,
        )

    assert filesystem_fingerprint(codex_skills) == expected
    assert filesystem_fingerprint(claude_skills, exclude_runtime_metadata=True) == expected

    skill_names = {
        PurePosixPath(path).parts[0]
        for path, value in expected.items()
        if value[0] == "file"
    }
    markers = sorted(claude_skills.glob("*/.team-skill"))
    assert {marker.parent.name for marker in markers} == skill_names
    assert all(marker.read_bytes() == b"" for marker in markers)
    assert (claude_skills / ".last-sync").is_file()
    assert (claude_skills / ".last-sync").read_text(encoding="utf-8").strip()
    assert sync_log.read_text(encoding="utf-8").strip()


@pytest.mark.skipif(shutil.which("bash") is None, reason="нужен bash для проверки Claude folder-sync")
def test_declared_claude_sync_default_destination_is_scoped_to_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["TEAM_SKILLS_PULL"] = "0"
    env[CLAUDE_SYNC["source_env"]] = str(SKILLS_DIR)
    env.pop(CLAUDE_SYNC["destination_env"], None)

    subprocess.run(
        ["bash", str(SYNC_SCRIPT)],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    default_destination = CLAUDE_SYNC["default_destination"]
    assert default_destination.startswith("~/")
    destination = home / default_destination.removeprefix("~/").rstrip("/")
    assert destination.is_dir()
    assert (destination / ".last-sync").is_file()
    assert (destination / "add-team-skill" / "SKILL.md").is_file()
    assert set(tmp_path.iterdir()) == {home}
    assert set(home.iterdir()) == {home / ".claude"}
    assert set((home / ".claude").iterdir()) == {destination}


@pytest.mark.skipif(
    os.name != "posix" or shutil.which("bash") is None,
    reason="нужны POSIX mode bits и bash для проверки Claude folder-sync",
)
def test_declared_claude_sync_preserves_executable_skill_files(tmp_path: Path) -> None:
    source = tmp_path / "source"
    skill = source / "demo"
    executable = skill / "scripts" / "run.sh"
    executable.parent.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: demo\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    executable.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)

    destination = tmp_path / "destination"
    env = os.environ.copy()
    env["TEAM_SKILLS_PULL"] = "0"
    env[CLAUDE_SYNC["source_env"]] = str(source)
    env[CLAUDE_SYNC["destination_env"]] = str(destination)
    subprocess.run(
        ["bash", str(SYNC_SCRIPT)],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    installed = destination / "demo" / "scripts" / "run.sh"
    assert installed.read_bytes() == executable.read_bytes()
    assert stat.S_IMODE(installed.stat().st_mode) == 0o755
    assert (destination / "demo" / ".team-skill").is_file()


def test_release_plugin_bundle_is_byte_deterministic(tmp_path: Path) -> None:
    first = build_dist(tmp_path / "first") / "team-skills-bundle.zip"
    second = build_dist(tmp_path / "second") / "team-skills-bundle.zip"

    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert {entry.date_time for entry in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}


def init_repo(path: Path) -> None:
    subprocess.run(["git", "-C", str(path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "core.filemode", "true"], check=True)


def test_release_source_uses_only_git_index_bytes_and_mode(tmp_path: Path) -> None:
    module = load_build_module()
    repo = tmp_path / "repo"
    plugin = repo / "plugins" / "team-skills"
    tracked = plugin / "skills" / "demo" / "SKILL.md"
    untracked = plugin / "skills" / "demo" / "notes.md"
    ignored = plugin / "skills" / "demo" / "__pycache__" / "helper.pyc"
    tracked.parent.mkdir(parents=True)
    ignored.parent.mkdir(parents=True)
    tracked.write_text("tracked index bytes\n", encoding="utf-8")
    untracked.write_text("untracked author file\n", encoding="utf-8")
    ignored.write_bytes(b"generated")
    (repo / ".gitignore").write_text("__pycache__/\n*.pyc\n", encoding="utf-8")
    init_repo(repo)
    tracked_relative = tracked.relative_to(repo).as_posix()
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore", tracked_relative], check=True)
    subprocess.run(["git", "-C", str(repo), "update-index", "--chmod=+x", tracked_relative], check=True)
    tracked.write_text("unstaged worktree bytes\n", encoding="utf-8")

    entries = module.git_index_source_files(repo, [plugin])
    selected = {entry.repo_path.as_posix(): entry for entry in entries}

    assert set(selected) == {tracked_relative}
    assert selected[tracked_relative].content == b"tracked index bytes\n"
    assert selected[tracked_relative].permissions == 0o755


@pytest.mark.parametrize(
    "artifact_relative",
    (
        PurePosixPath("skills/demo/__pycache__/helper.py"),
        PurePosixPath("skills/demo/__pycache__/helper.pyc"),
        PurePosixPath("skills/demo/helper.pyc"),
        PurePosixPath("skills/demo/helper.pyo"),
        PurePosixPath("skills/demo/.DS_Store"),
    ),
)
def test_release_source_rejects_force_added_generated_artifacts(
    tmp_path: Path,
    artifact_relative: PurePosixPath,
) -> None:
    module = load_build_module()
    repo = tmp_path / "repo"
    plugin = repo / "plugins" / "team-skills"
    artifact = plugin.joinpath(*artifact_relative.parts)
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"generated")
    (repo / ".gitignore").write_text(
        "__pycache__/\n*.pyc\n*.pyo\n.DS_Store\n",
        encoding="utf-8",
    )
    init_repo(repo)
    subprocess.run(["git", "-C", str(repo), "add", ".gitignore"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", "-f", artifact.relative_to(repo).as_posix()],
        check=True,
    )

    with pytest.raises(ValueError, match="запрещённый служебный файл"):
        module.git_index_source_files(repo, [plugin])


def test_release_source_fails_when_tracked_file_is_missing(tmp_path: Path) -> None:
    module = load_build_module()
    repo = tmp_path / "repo"
    plugin = repo / "plugins" / "team-skills"
    tracked = plugin / "skills" / "demo" / "SKILL.md"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("tracked\n", encoding="utf-8")
    init_repo(repo)
    subprocess.run(["git", "-C", str(repo), "add", tracked.relative_to(repo).as_posix()], check=True)
    tracked.unlink()

    with pytest.raises(RuntimeError, match="отсутствует в worktree"):
        module.git_index_source_files(repo, [plugin])


def test_release_source_rejects_index_divergence_from_real_commit(tmp_path: Path) -> None:
    module = load_build_module()
    repo = tmp_path / "repo"
    plugin = repo / "plugins" / "team-skills"
    tracked = plugin / "skills" / "demo" / "SKILL.md"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("committed\n", encoding="utf-8")
    init_repo(repo)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", tracked.relative_to(repo).as_posix()], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)

    tracked.write_text("staged divergence\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", tracked.relative_to(repo).as_posix()], check=True)
    with pytest.raises(RuntimeError, match="index расходится"):
        module.release_source_files(repo, [plugin], "HEAD")


def test_release_source_rejects_unknown_commit(tmp_path: Path) -> None:
    module = load_build_module()
    repo = tmp_path / "repo"
    plugin = repo / "plugins" / "team-skills"
    tracked = plugin / "skills" / "demo" / "SKILL.md"
    tracked.parent.mkdir(parents=True)
    tracked.write_text("tracked\n", encoding="utf-8")
    init_repo(repo)
    subprocess.run(["git", "-C", str(repo), "add", tracked.relative_to(repo).as_posix()], check=True)

    with pytest.raises(RuntimeError, match="Release commit не существует"):
        module.release_source_files(repo, [plugin], "definitely-not-a-commit")


def test_executed_builder_bytes_must_match_declared_commit(tmp_path: Path) -> None:
    module = load_build_module()
    repo = tmp_path / "repo"
    builder = repo / "scripts" / "build_release_bundle.py"
    builder.parent.mkdir(parents=True)
    builder.write_text("print('committed builder')\n", encoding="utf-8")
    init_repo(repo)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "add", builder.relative_to(repo).as_posix()], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "initial"], check=True)

    module.ensure_executed_builder_matches_commit(repo, "HEAD", builder)
    builder.write_text("print('unstaged builder')\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="worktree-байты builder расходятся"):
        module.ensure_executed_builder_matches_commit(repo, "HEAD", builder)


def test_release_source_rejects_symlinks_and_case_collisions(tmp_path: Path) -> None:
    module = load_build_module()
    repo = tmp_path / "repo"
    plugin = repo / "plugins" / "team-skills"
    regular = plugin / "skills" / "demo" / "regular.txt"
    symlink = plugin / "skills" / "demo" / "link.txt"
    regular.parent.mkdir(parents=True)
    regular.write_text("ok\n", encoding="utf-8")
    try:
        symlink.symlink_to(regular)
    except OSError as exc:  # pragma: no cover - depends on local Windows policy
        pytest.skip(f"symbolic links are unavailable: {exc}")
    init_repo(repo)
    subprocess.run(["git", "-C", str(repo), "add", regular.relative_to(repo), symlink.relative_to(repo)], check=True)

    with pytest.raises(ValueError, match="symbolic link"):
        module.git_index_source_files(repo, [plugin])

    with pytest.raises(ValueError, match="конфликтуют"):
        module.validate_portable_paths(
            [
                PurePosixPath("skills/Demo/SKILL.md"),
                PurePosixPath("skills/demo/examples/good.md"),
            ]
        )


@pytest.mark.parametrize(
    "invalid_path",
    (
        PurePosixPath("skills/demo/CON.txt"),
        PurePosixPath("skills/demo/CON .txt"),
        PurePosixPath("skills/demo/Lpt9.log"),
        PurePosixPath("skills/demo/trailing."),
        PurePosixPath("skills/demo/trailing "),
        PurePosixPath("skills/demo/bad:name"),
        PurePosixPath("skills/demo/bad\\name"),
    ),
)
def test_release_source_rejects_windows_invalid_components(invalid_path: PurePosixPath) -> None:
    module = load_build_module()
    with pytest.raises(ValueError, match="Windows"):
        module.validate_portable_paths([invalid_path])
