from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

from conftest import ROOT


SKILL = ROOT / "plugins" / "team-skills" / "skills" / "codex-session-to-repo-rescue"
SCRIPT = SKILL / "scripts" / "rescue_evidence.py"
SPEC = importlib.util.spec_from_file_location("codex_session_to_repo_rescue", SCRIPT)
assert SPEC and SPEC.loader
rescue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rescue)


def git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def create_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "--quiet")
    git(path, "config", "user.name", "Synthetic User")
    git(path, "config", "user.email", "synthetic@example.test")
    (path / ".gitattributes").write_text("evidence.txt text eol=lf\n", encoding="utf-8")
    (path / "evidence.txt").write_bytes(b"approved\nbytes\n")
    git(path, "add", ".gitattributes", "evidence.txt")
    git(path, "commit", "--quiet", "-m", "Add approved evidence")
    return path


def write_manifest(path: Path, relative_path: str, data: bytes) -> Path:
    payload = {
        "version": 1,
        "files": [
            {
                "path": relative_path,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_skill_preserves_unique_session_forensics_boundary() -> None:
    content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for phrase in (
        "Codex task -> session file -> cwd -> repo/worktree -> commit/files -> remote -> PR/MR -> target branch",
        "Не считайте `origin/main` настоящим target автоматически",
        "Raw session",
        "TARGET_PROVEN",
        "git-worktree-reality-check",
        "git-pr-lifecycle-safeguard",
        "auto-merge",
        "настоящий target не подтверждён",
    ):
        assert phrase in content


def test_inventory_finds_archived_session_and_git_worktree(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    repo = create_repo(workspace / "repo-worktree")
    internal_repo = create_repo(tmp_path / ".codex" / "memories")
    codex_home = tmp_path / "codex-home"
    archive = codex_home / "archived_sessions"
    archive.mkdir(parents=True)
    thread_id = "019f0000-0000-7000-8000-000000000001"
    session = archive / f"rollout-2026-07-15-{thread_id}.jsonl"
    tool_input = (
        "await tools.shell_command({command: 'git status', workdir: "
        + json.dumps(str(repo))
        + "})"
    )
    internal_tool_input = (
        "await tools.shell_command({command: 'git status', workdir: "
        + json.dumps(str(internal_repo))
        + "})"
    )
    session.write_text(
        json.dumps(
            {
                "timestamp": "2026-07-15T10:00:00Z",
                "type": "session_meta",
                "payload": {
                    "id": thread_id,
                    "timestamp": "2026-07-15T10:00:00Z",
                    "cwd": str(workspace),
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "input": tool_input,
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "response_item",
                "payload": {"type": "function_call", "input": internal_tool_input},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    matches = rescue.find_session_files(codex_home, thread_id)

    assert len(matches) == 1
    match = matches[0]
    assert match["archived"] is True
    assert match["schema_status"] == "confirmed"
    assert match["cwd"] == str(workspace)
    assert match["git"]["cwd_status"] == "not_git"
    assert match["path_hints_observed"] == 3
    assert len(match["git_candidates"]) == 1
    candidate = match["git_candidates"][0]
    assert Path(candidate["repo_root"]).resolve() == repo.resolve()
    assert candidate["head"] == git(repo, "rev-parse", "HEAD")
    assert candidate["worktrees"]


def test_inventory_does_not_scan_content_without_explicit_flag(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    thread_id = "019f0000-0000-7000-8000-000000000002"
    (sessions / "generic-name.jsonl").write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}}) + "\n",
        encoding="utf-8",
    )

    assert rescue.find_session_files(codex_home, thread_id) == []
    matches = rescue.find_session_files(codex_home, thread_id, scan_content=True)
    assert len(matches) == 1
    assert matches[0]["id_source"] == "session_meta"


def test_inventory_marks_record_limit_as_partial(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    thread_id = "019f0000-0000-7000-8000-000000000003"
    session = sessions / f"rollout-{thread_id}.jsonl"
    session.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}})
        + "\n"
        + json.dumps({"type": "event_msg", "payload": {"message": "later evidence"}})
        + "\n",
        encoding="utf-8",
    )

    matches = rescue.find_session_files(codex_home, thread_id, max_records=1)

    assert len(matches) == 1
    assert matches[0]["records_scanned"] == 1
    assert matches[0]["records_truncated"] is True
    assert matches[0]["discovery_status"] == "partial"


def test_inventory_reports_invalid_utf8_as_structured_cli_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    thread_id = "019f0000-0000-7000-8000-000000000004"
    session = sessions / f"rollout-{thread_id}.jsonl"
    session.write_bytes(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}}).encode()
        + b"\n\xff\n"
    )

    exit_code = rescue.main(
        [
            "inventory-session",
            "--codex-home",
            str(codex_home),
            "--thread-id",
            thread_id,
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["status"] == "error"
    assert str(session) in output["detail"]


def test_remote_url_sanitization_removes_credentials_and_tokens() -> None:
    assert (
        rescue.sanitize_remote_url(
            "https://account:secret@git.example.test/team/repo.git?access_token=hidden#fragment"
        )
        == "https://git.example.test/team/repo.git"
    )
    assert (
        rescue.sanitize_remote_url("git@git.example.test:team/repo.git?token=hidden")
        == "ssh://git.example.test/team/repo.git"
    )
    assert rescue.sanitize_remote_url(r"C:\repo\worktree") == r"C:\repo\worktree"
    assert rescue.sanitize_remote_url("C:/repo/worktree") == "C:/repo/worktree"


def test_manifest_matches_working_index_commit_and_fresh_checkout(tmp_path: Path) -> None:
    repo = create_repo(tmp_path / "repo")
    approved = (repo / "evidence.txt").read_bytes()
    manifest = write_manifest(tmp_path / "manifest.json", "evidence.txt", approved)

    entries = rescue.load_manifest(manifest)
    report = rescue.verify_manifest(
        repo,
        entries,
        ["working", "index", "commit", "checkout"],
        commit="HEAD",
    )

    assert report["status"] == "hashes_ok_scope_unchecked"
    assert report["hash_status"] == "ok"
    assert report["scope"]["status"] == "unchecked"
    assert report["package_ready"] is False
    assert {row["source"] for row in report["files"]} == {
        "working",
        "index",
        "commit",
        "checkout",
    }
    assert all(row["status"] == "ok" for row in report["files"])


def test_manifest_reports_working_copy_drift_without_rewriting_expected_hash(tmp_path: Path) -> None:
    repo = create_repo(tmp_path / "repo")
    approved = (repo / "evidence.txt").read_bytes()
    manifest = write_manifest(tmp_path / "manifest.json", "evidence.txt", approved)
    entries = rescue.load_manifest(manifest)
    (repo / "evidence.txt").write_bytes(b"changed\n")

    report = rescue.verify_manifest(repo, entries, ["working", "commit"], commit="HEAD")

    assert report["status"] == "mismatch"
    by_source = {row["source"]: row for row in report["files"]}
    assert by_source["working"]["status"] == "mismatch"
    assert by_source["commit"]["status"] == "ok"
    assert by_source["working"]["expected_sha256"] == hashlib.sha256(approved).hexdigest()


def test_manifest_exact_index_scope_rejects_unexpected_changed_paths(tmp_path: Path) -> None:
    repo = create_repo(tmp_path / "repo")
    approved = b"new approved bytes\n"
    (repo / "evidence.txt").write_bytes(approved)
    git(repo, "add", "evidence.txt")
    manifest = write_manifest(tmp_path / "manifest.json", "evidence.txt", approved)
    entries = rescue.load_manifest(manifest)

    exact_report = rescue.verify_manifest(
        repo,
        entries,
        ["working", "index"],
        exact_scope="index",
        base="HEAD",
    )

    assert exact_report["status"] == "ok"
    assert exact_report["scope"]["status"] == "ok"
    assert exact_report["package_ready"] is True

    (repo / "unexpected.txt").write_text("not in manifest\n", encoding="utf-8")
    git(repo, "add", "unexpected.txt")
    mismatch_report = rescue.verify_manifest(
        repo,
        entries,
        ["working", "index"],
        exact_scope="index",
        base="HEAD",
    )

    assert mismatch_report["hash_status"] == "ok"
    assert mismatch_report["status"] == "mismatch"
    assert mismatch_report["scope"]["status"] == "mismatch"
    assert mismatch_report["scope"]["unexpected_changed_paths"] == ["unexpected.txt"]
    assert mismatch_report["package_ready"] is False


@pytest.mark.parametrize(
    ("exact_scope", "sources"),
    [
        ("index", ["working"]),
        ("commit", ["checkout"]),
    ],
)
def test_exact_scope_requires_matching_git_byte_source(
    tmp_path: Path, exact_scope: str, sources: list[str]
) -> None:
    repo = create_repo(tmp_path / "repo")
    approved = (repo / "evidence.txt").read_bytes()
    manifest = write_manifest(tmp_path / "manifest.json", "evidence.txt", approved)

    with pytest.raises(rescue.RescueError, match="byte source"):
        rescue.verify_manifest(
            repo,
            rescue.load_manifest(manifest),
            sources,
            exact_scope=exact_scope,
            base="HEAD",
        )


def test_manifest_exact_commit_scope_uses_resolved_commits(tmp_path: Path) -> None:
    repo = create_repo(tmp_path / "repo")
    base = git(repo, "rev-parse", "HEAD")
    approved = b"approved in commit\n"
    (repo / "evidence.txt").write_bytes(approved)
    git(repo, "add", "evidence.txt")
    git(repo, "commit", "--quiet", "-m", "Update approved evidence")
    manifest = write_manifest(tmp_path / "manifest.json", "evidence.txt", approved)

    report = rescue.verify_manifest(
        repo,
        rescue.load_manifest(manifest),
        ["commit"],
        commit="HEAD",
        exact_scope="commit",
        base=base,
    )

    assert report["status"] == "ok"
    assert report["package_ready"] is True
    assert report["commit"] == git(repo, "rev-parse", "HEAD")
    assert report["scope"]["base"] == base


def test_manifest_exact_scope_handles_cyrillic_path_without_git_quoting(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    relative_path = "доказательство.txt"
    approved = "проверено\n".encode()
    (repo / relative_path).write_bytes(approved)
    git(repo, "add", relative_path)
    manifest = write_manifest(tmp_path / "manifest.json", relative_path, approved)

    report = rescue.verify_manifest(
        repo,
        rescue.load_manifest(manifest),
        ["index"],
        exact_scope="index",
        base="HEAD",
    )

    assert report["status"] == "ok"
    assert report["scope"]["unexpected_changed_paths"] == []


def test_manifest_exact_scope_rejects_file_type_change_even_when_bytes_match(
    tmp_path: Path,
) -> None:
    repo = create_repo(tmp_path / "repo")
    approved = (repo / "evidence.txt").read_bytes()
    blob = git(repo, "hash-object", "evidence.txt")
    git(repo, "update-index", "--cacheinfo", "120000", blob, "evidence.txt")
    manifest = write_manifest(tmp_path / "manifest.json", "evidence.txt", approved)

    report = rescue.verify_manifest(
        repo,
        rescue.load_manifest(manifest),
        ["index"],
        exact_scope="index",
        base="HEAD",
    )

    assert report["hash_status"] == "ok"
    assert report["status"] == "mismatch"
    assert report["scope"]["unsupported_changes"] == [
        {"status": "T", "path": "evidence.txt"}
    ]
    assert report["package_ready"] is False


def test_manifest_exact_scope_rejects_unmerged_index(tmp_path: Path) -> None:
    repo = create_repo(tmp_path / "repo")
    primary_branch = git(repo, "branch", "--show-current")
    git(repo, "branch", "other")
    (repo / "evidence.txt").write_bytes(b"main side\n")
    git(repo, "add", "evidence.txt")
    git(repo, "commit", "--quiet", "-m", "Change evidence on main")
    git(repo, "checkout", "--quiet", "other")
    (repo / "evidence.txt").write_bytes(b"other side\n")
    git(repo, "add", "evidence.txt")
    git(repo, "commit", "--quiet", "-m", "Change evidence on other")
    git(repo, "checkout", "--quiet", primary_branch)
    merge = subprocess.run(
        ["git", "-C", str(repo), "merge", "--no-edit", "other"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert merge.returncode != 0
    manifest = write_manifest(tmp_path / "manifest.json", "evidence.txt", b"main side\n")

    report = rescue.verify_manifest(
        repo,
        rescue.load_manifest(manifest),
        ["index"],
        exact_scope="index",
        base="HEAD",
    )

    assert report["status"] == "mismatch"
    assert {item["status"] for item in report["scope"]["unsupported_changes"]} == {"U"}
    assert report["package_ready"] is False


def test_untrusted_revision_cannot_become_git_option(tmp_path: Path) -> None:
    repo = create_repo(tmp_path / "repo")
    approved = (repo / "evidence.txt").read_bytes()
    manifest = write_manifest(tmp_path / "manifest.json", "evidence.txt", approved)
    output_path = tmp_path / "must-not-be-written.txt"

    with pytest.raises(rescue.RescueError, match="base не разрешается"):
        rescue.verify_manifest(
            repo,
            rescue.load_manifest(manifest),
            ["index"],
            exact_scope="index",
            base=f"--output={output_path}",
        )

    assert not output_path.exists()


def test_working_source_hashes_symlink_itself_without_following_target(tmp_path: Path) -> None:
    (tmp_path / "target.txt").write_text("outside manifest bytes\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to("target.txt")
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    assert rescue.read_filesystem_bytes(tmp_path, "link.txt") == os.fsencode("target.txt")


@pytest.mark.parametrize(
    "unsafe_path",
    [
        ".codex/hooks.json",
        "docs/.codex/hooks.json",
        ".goal-runtime/active.json",
        "docs/.goal-runtime/active.json",
        ".git/config",
        "rollout-2026-07-15-session.jsonl",
        "../outside.txt",
        ".env.local",
        ".envrc",
        ".env-backup",
        ".envbackup",
        ".env_local",
        ".environment",
        ".environment.local",
    ],
)
def test_manifest_rejects_local_raw_or_escaping_paths(tmp_path: Path, unsafe_path: str) -> None:
    manifest = write_manifest(tmp_path / "manifest.json", unsafe_path, b"unsafe")

    with pytest.raises(rescue.RescueError):
        rescue.load_manifest(manifest)
