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


def write_target_lock(path: Path, session: Path, thread_id: str, *, archived: bool) -> Path:
    payload = {
        "version": 1,
        "kind": "codex-session-target-lock",
        "query": {"thread_id": thread_id},
        "target": {
            "thread_id": thread_id,
            "session_file": str(session.resolve()),
            "archived": archived,
            "size_bytes": session.stat().st_size,
            "size_mib": rescue.size_mib_rounded(session.stat().st_size),
            "title": None,
            "title_source": None,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_sized_session(
    path: Path,
    thread_id: str,
    title: str,
    size_mib: str,
    *,
    message: str | None = None,
) -> Path:
    prefix = (
        json.dumps(
            {"type": "session_meta", "payload": {"id": thread_id}},
            separators=(",", ":"),
        )
        + "\n"
        + json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": message or title}],
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    target_size = int(float(size_mib) * 1024 * 1024)
    padding_template = b'{"type":"padding","payload":{"text":""}}\n'
    padding_size = target_size - len(prefix) - len(padding_template)
    assert padding_size >= 0
    path.write_bytes(prefix + b'{"type":"padding","payload":{"text":"' + b"x" * padding_size + b'"}}\n')
    assert rescue.size_mib_rounded(path.stat().st_size) == size_mib
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
        "target_locked",
    ):
        assert phrase in content


def test_resolver_uses_size_gate_before_locking_same_title_candidates(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    archive = codex_home / "archived_sessions"
    archive.mkdir(parents=True)
    title = "Status Export Pass"
    decoy_id = "019f0000-0000-7000-8000-000000000216"
    target_id = "019f0000-0000-7000-8000-000000000253"
    write_sized_session(archive / f"rollout-{decoy_id}.jsonl", decoy_id, title, "2.16")
    target = write_sized_session(
        archive / f"rollout-{target_id}.jsonl", target_id, title, "2.53"
    )

    incomplete = rescue.resolve_session_target(codex_home, title=title)
    assert incomplete["status"] == "identity_incomplete"
    assert incomplete["candidates"] == []

    resolved = rescue.resolve_session_target(
        codex_home,
        title=title,
        expected_size_mib="2,53",
    )
    assert resolved["status"] == "resolved"
    assert resolved["target"]["thread_id"] == target_id
    assert Path(resolved["target"]["session_file"]) == target.resolve()


def test_resolver_rejects_message_fallback_when_indexed_title_mismatches(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    archive = codex_home / "archived_sessions"
    archive.mkdir(parents=True)
    requested_title = "Status Export Pass"
    thread_id = "019f0000-0000-7000-8000-000000000254"
    session = write_sized_session(
        archive / f"rollout-{thread_id}.jsonl",
        thread_id,
        requested_title,
        "2.53",
    )
    (codex_home / "session_index.jsonl").write_text(
        json.dumps({"id": thread_id, "thread_name": "Different Session"}) + "\n",
        encoding="utf-8",
    )

    result = rescue.resolve_session_target(
        codex_home,
        title=requested_title,
        expected_bytes=session.stat().st_size,
    )

    assert result["status"] == "target_not_found"


def test_resolver_requires_exact_message_fallback_title(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    archive = codex_home / "archived_sessions"
    archive.mkdir(parents=True)
    requested_title = "Status Export Pass"
    thread_id = "019f0000-0000-7000-8000-000000000255"
    session = write_sized_session(
        archive / f"rollout-{thread_id}.jsonl",
        thread_id,
        requested_title,
        "2.53",
        message=f"Запусти {requested_title}.",
    )

    result = rescue.resolve_session_target(
        codex_home,
        title=requested_title,
        expected_bytes=session.stat().st_size,
    )

    assert result["status"] == "target_not_found"


@pytest.mark.parametrize("raw_size", ["NaN", "Infinity", "-Infinity", "1e999999"])
def test_resolver_rejects_nonfinite_or_unquantizable_sizes_as_structured_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    raw_size: str,
) -> None:
    exit_code = rescue.main(
        [
            "resolve-session",
            "--codex-home",
            str(tmp_path / "codex-home"),
            "--title",
            "Status Export Pass",
            f"--expected-size-mib={raw_size}",
            "--lock-file",
            str(tmp_path / "target-lock.json"),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output == {
        "status": "error",
        "detail": "expected_size_mib должен быть конечным числом",
    }


def test_thread_id_resolution_skips_unrelated_corrupt_sessions(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "000-unrelated.jsonl").write_bytes(b"\xff\n")
    thread_id = "019f0000-0000-7000-8000-000000000256"
    target = sessions / f"rollout-{thread_id}.jsonl"
    target.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}}) + "\n",
        encoding="utf-8",
    )

    result = rescue.resolve_session_target(codex_home, thread_id=thread_id)

    assert result["status"] == "resolved"
    assert result["target"]["thread_id"] == thread_id
    assert Path(result["target"]["session_file"]) == target.resolve()


def test_title_resolution_skips_and_reports_unrelated_corrupt_sessions(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    archive = codex_home / "archived_sessions"
    archive.mkdir(parents=True)
    corrupt = archive / "000-unrelated.jsonl"
    corrupt.write_bytes(b"\xff\n")
    title = "Status Export Pass"
    thread_id = "019f0000-0000-7000-8000-000000000257"
    target = write_sized_session(
        archive / f"rollout-{thread_id}.jsonl",
        thread_id,
        title,
        "2.53",
    )

    result = rescue.resolve_session_target(
        codex_home,
        title=title,
        expected_bytes=target.stat().st_size,
    )

    assert result["status"] == "resolved"
    assert result["target"]["thread_id"] == thread_id
    assert result["inspection_errors"][0]["session_file"] == str(corrupt.resolve())
    assert "Не удалось прочитать session identity" in result["inspection_errors"][0]["detail"]


def test_title_resolution_rejects_candidate_without_valid_thread_id(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    title = "Status Export Pass"
    session = sessions / "generic.jsonl"
    session.write_text(
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": title}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    lock = tmp_path / "target-lock.json"

    exit_code = rescue.main(
        [
            "resolve-session",
            "--codex-home",
            str(codex_home),
            "--title",
            title,
            "--expected-bytes",
            str(session.stat().st_size),
            "--lock-file",
            str(lock),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 3
    assert output["status"] == "target_not_found"
    assert output["inspection_errors"][0]["session_file"] == str(session.resolve())
    assert "корректный thread_id" in output["inspection_errors"][0]["detail"]
    assert not lock.exists()


def test_title_resolution_preserves_early_message_before_session_meta(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    title = "Status Export Pass"
    thread_id = "019f0000-0000-7000-8000-000000000272"
    session = sessions / f"rollout-{thread_id}.jsonl"
    session.write_text(
        json.dumps(
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": title}],
                },
            }
        )
        + "\n"
        + json.dumps({"type": "session_meta", "payload": {"id": thread_id}})
        + "\n",
        encoding="utf-8",
    )

    result = rescue.resolve_session_target(
        codex_home,
        title=title,
        expected_bytes=session.stat().st_size,
    )

    assert result["status"] == "resolved"
    assert result["target"]["title_source"] == "early_user_message"


def test_thread_id_resolution_requires_matching_session_meta_after_filename_hint(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    requested_id = "019f0000-0000-7000-8000-000000000262"
    actual_id = "019f0000-0000-7000-8000-000000000263"
    session = sessions / f"rollout-{requested_id}.jsonl"
    session.write_text(
        json.dumps({"type": "event_msg", "payload": {"message": "before metadata"}})
        + "\n"
        + json.dumps({"type": "session_meta", "payload": {"id": actual_id}})
        + "\n",
        encoding="utf-8",
    )

    result = rescue.resolve_session_target(codex_home, thread_id=requested_id)

    assert result["status"] == "target_not_found"


def test_thread_id_resolution_does_not_depend_on_session_index(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    (codex_home / "session_index.jsonl").write_bytes(b"\xff\n")
    thread_id = "019f0000-0000-7000-8000-000000000270"
    session = sessions / f"rollout-{thread_id}.jsonl"
    session.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}}) + "\n",
        encoding="utf-8",
    )

    result = rescue.resolve_session_target(codex_home, thread_id=thread_id)

    assert result["status"] == "resolved"
    assert result["target"]["session_file"] == str(session.resolve())


def test_identity_reports_session_disappearing_before_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread_id = "019f0000-0000-7000-8000-000000000271"
    session = tmp_path / f"rollout-{thread_id}.jsonl"
    session.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}}) + "\n",
        encoding="utf-8",
    )
    original_stat = Path.stat

    def disappearing_stat(path: Path, *args: object, **kwargs: object) -> os.stat_result:
        if path == session:
            raise FileNotFoundError(session)
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", disappearing_stat)

    with pytest.raises(rescue.RescueError, match="Не удалось прочитать session identity"):
        rescue.inspect_session_identity(session, {}, title_query=None)


def test_thread_id_resolution_falls_back_after_false_filename_hint(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    requested_id = "019f0000-0000-7000-8000-000000000264"
    stale_id = "019f0000-0000-7000-8000-000000000265"
    stale = sessions / f"rollout-{requested_id}.jsonl"
    stale.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": stale_id}}) + "\n",
        encoding="utf-8",
    )
    valid = sessions / "renamed-session.jsonl"
    valid.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": requested_id}})
        + "\n",
        encoding="utf-8",
    )

    result = rescue.resolve_session_target(codex_home, thread_id=requested_id)

    assert result["status"] == "resolved"
    assert result["target"]["session_file"] == str(valid.resolve())


def test_thread_id_resolution_reports_renamed_duplicate_as_ambiguous(
    tmp_path: Path,
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    archive = codex_home / "archived_sessions"
    sessions.mkdir(parents=True)
    archive.mkdir(parents=True)
    thread_id = "019f0000-0000-7000-8000-000000000268"
    active = sessions / f"rollout-{thread_id}.jsonl"
    archived = archive / "renamed-copy.jsonl"
    record = json.dumps({"type": "session_meta", "payload": {"id": thread_id}}) + "\n"
    active.write_text(record, encoding="utf-8")
    archived.write_text(record, encoding="utf-8")

    result = rescue.resolve_session_target(codex_home, thread_id=thread_id)

    assert result["status"] == "ambiguous_target"
    assert {item["session_file"] for item in result["candidates"]} == {
        str(active.resolve()),
        str(archived.resolve()),
    }


def test_confirmed_filename_match_uses_lightweight_scan_for_unrelated_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    thread_id = "019f0000-0000-7000-8000-000000000269"
    target = sessions / f"rollout-{thread_id}.jsonl"
    unrelated = sessions / "unrelated.jsonl"
    target.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}}) + "\n",
        encoding="utf-8",
    )
    unrelated.write_text(
        json.dumps({"type": "event_msg", "payload": {"message": "not metadata"}})
        + "\n",
        encoding="utf-8",
    )
    inspected: list[Path] = []
    original_inspect = rescue.inspect_session_identity

    def recording_inspect(path: Path, *args: object, **kwargs: object) -> dict[str, object]:
        inspected.append(path)
        return original_inspect(path, *args, **kwargs)

    monkeypatch.setattr(rescue, "inspect_session_identity", recording_inspect)

    result = rescue.resolve_session_target(codex_home, thread_id=thread_id)

    assert result["status"] == "resolved"
    assert inspected == [target]


def test_existing_lock_refuses_silent_target_switch(tmp_path: Path) -> None:
    first = {
        "version": 1,
        "kind": "codex-session-target-lock",
        "query": {},
        "target": {
            "thread_id": "019f0000-0000-7000-8000-000000000001",
            "session_file": str((tmp_path / "first.jsonl").resolve()),
            "archived": True,
        },
    }
    second = {
        **first,
        "target": {
            "thread_id": "019f0000-0000-7000-8000-000000000002",
            "session_file": str((tmp_path / "second.jsonl").resolve()),
            "archived": True,
        },
    }
    lock = tmp_path / "target-lock.json"

    created = rescue.write_target_lock(lock, first)
    before = lock.read_bytes()
    conflict = rescue.write_target_lock(lock, second)

    assert created == {"status": "target_locked", "lock_state": "created"}
    assert conflict["status"] == "target_lock_conflict"
    assert conflict["invalidation_required"] is True
    assert lock.read_bytes() == before


def test_target_lock_cannot_be_created_inside_git_worktree(tmp_path: Path) -> None:
    repo = create_repo(tmp_path / "repo")
    lock = repo / "private" / "target-lock.json"
    lock.parent.mkdir()
    payload = {
        "version": 1,
        "kind": "codex-session-target-lock",
        "query": {"title": "Private Task"},
        "target": {
            "thread_id": "019f0000-0000-7000-8000-000000000261",
            "session_file": str((tmp_path / "private-session.jsonl").resolve()),
            "archived": True,
        },
    }

    with pytest.raises(rescue.RescueError, match="внутри Git worktree"):
        rescue.write_target_lock(lock, payload)

    assert not lock.exists()


def test_target_lock_requires_fixed_private_filename(tmp_path: Path) -> None:
    payload = {
        "version": 1,
        "kind": "codex-session-target-lock",
        "query": {"title": "Private Task"},
        "target": {
            "thread_id": "019f0000-0000-7000-8000-000000000266",
            "session_file": str((tmp_path / "private-session.jsonl").resolve()),
            "archived": True,
        },
    }

    with pytest.raises(rescue.RescueError, match="target-lock.json"):
        rescue.write_target_lock(tmp_path / "session-lock.json", payload)


def test_target_lock_is_created_with_private_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "version": 1,
        "kind": "codex-session-target-lock",
        "query": {"title": "Private Task"},
        "target": {
            "thread_id": "019f0000-0000-7000-8000-000000000267",
            "session_file": str((tmp_path / "private-session.jsonl").resolve()),
            "archived": True,
        },
    }
    requested_modes: list[int] = []
    original_open = os.open

    def recording_open(path: os.PathLike[str] | str, flags: int, mode: int = 0o777) -> int:
        requested_modes.append(mode)
        return original_open(path, flags, mode)

    monkeypatch.setattr(rescue.os, "open", recording_open)
    lock = tmp_path / "target-lock.json"

    result = rescue.write_target_lock(lock, payload)

    assert result == {"status": "target_locked", "lock_state": "created"}
    assert requested_modes == [0o600]
    if os.name != "nt":
        assert lock.stat().st_mode & 0o777 == 0o600


def test_symlinked_archive_keeps_consistent_lock_state(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex-home"
    codex_home.mkdir()
    external_archive = tmp_path / "external-store"
    external_archive.mkdir()
    archive_link = codex_home / "archived_sessions"
    try:
        archive_link.symlink_to(external_archive, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    thread_id = "019f0000-0000-7000-8000-000000000273"
    logical_session = archive_link / f"rollout-{thread_id}.jsonl"
    (external_archive / logical_session.name).write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}}) + "\n",
        encoding="utf-8",
    )

    resolution = rescue.resolve_session_target(codex_home, thread_id=thread_id)

    assert resolution["status"] == "resolved"
    assert resolution["target"]["archived"] is True
    assert resolution["target"]["session_file"] == str(logical_session.absolute())
    lock = tmp_path / "target-lock.json"
    rescue.write_target_lock(lock, rescue.target_lock_payload(resolution))

    _, inventory = rescue.inventory_from_target_lock(codex_home, lock, max_records=200)

    assert inventory[0]["archived"] is True


def test_resolve_cli_reports_persisted_target_when_lock_is_reused(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    thread_id = "019f0000-0000-7000-8000-000000000258"
    session = sessions / f"rollout-{thread_id}.jsonl"
    session.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}}) + "\n",
        encoding="utf-8",
    )
    persisted_target = {
        "thread_id": thread_id,
        "session_file": str(session.resolve()),
        "archived": False,
        "size_bytes": 999,
        "size_mib": "0.00",
        "title": "Persisted Title",
        "title_source": "session_index",
    }
    lock = tmp_path / "target-lock.json"
    lock.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "codex-session-target-lock",
                "query": {"thread_id": thread_id},
                "target": persisted_target,
            }
        ),
        encoding="utf-8",
    )

    exit_code = rescue.main(
        [
            "resolve-session",
            "--codex-home",
            str(codex_home),
            "--thread-id",
            thread_id,
            "--lock-file",
            str(lock),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["lock_state"] == "reused"
    assert output["target"] == persisted_target


def test_resolve_cli_omits_target_when_existing_lock_conflicts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    requested_id = "019f0000-0000-7000-8000-000000000259"
    requested_session = sessions / f"rollout-{requested_id}.jsonl"
    requested_session.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": requested_id}}) + "\n",
        encoding="utf-8",
    )
    active_target = {
        "thread_id": "019f0000-0000-7000-8000-000000000260",
        "session_file": str((sessions / "active.jsonl").resolve()),
        "archived": False,
    }
    lock = tmp_path / "target-lock.json"
    lock.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "codex-session-target-lock",
                "query": {},
                "target": active_target,
            }
        ),
        encoding="utf-8",
    )

    exit_code = rescue.main(
        [
            "resolve-session",
            "--codex-home",
            str(codex_home),
            "--thread-id",
            requested_id,
            "--lock-file",
            str(lock),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 4
    assert output["status"] == "target_lock_conflict"
    assert output["active_target"] == active_target
    assert output["rejected_target"]["thread_id"] == requested_id
    assert "target" not in output


def test_inventory_reports_invalid_target_lock_utf8_as_structured_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lock = tmp_path / "target-lock.json"
    lock.write_bytes(b'{"title":"\xff"}')

    exit_code = rescue.main(
        [
            "inventory-session",
            "--codex-home",
            str(tmp_path / "codex-home"),
            "--target-lock",
            str(lock),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["status"] == "error"
    assert f"Не удалось прочитать target lock {lock}" in output["detail"]


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
    lock = write_target_lock(tmp_path / "target-lock.json", session, thread_id, archived=False)

    exit_code = rescue.main(
        [
            "inventory-session",
            "--codex-home",
            str(codex_home),
            "--target-lock",
            str(lock),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["status"] == "error"
    assert str(session) in output["detail"]


@pytest.mark.parametrize("max_records", [0, -1])
def test_inventory_rejects_nonpositive_record_limits(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    max_records: int,
) -> None:
    codex_home = tmp_path / "codex-home"
    sessions = codex_home / "sessions"
    sessions.mkdir(parents=True)
    thread_id = "019f0000-0000-7000-8000-000000000005"
    session = sessions / f"rollout-{thread_id}.jsonl"
    session.write_text(
        json.dumps({"type": "session_meta", "payload": {"id": thread_id}}) + "\n",
        encoding="utf-8",
    )
    lock = write_target_lock(
        tmp_path / "target-lock.json",
        session,
        thread_id,
        archived=False,
    )

    exit_code = rescue.main(
        [
            "inventory-session",
            "--codex-home",
            str(codex_home),
            "--target-lock",
            str(lock),
            "--max-records",
            str(max_records),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output == {
        "status": "error",
        "detail": "max_records должен быть положительным",
    }


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
        "target-lock.json",
        "docs/target-lock.json",
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
