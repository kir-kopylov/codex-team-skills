"""Отбор не должен терять изменённые файлы, зависимости и коды ошибок."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_changed", ROOT / "scripts/check_changed.py")
checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = checker
spec.loader.exec_module(checker)


def write(root, path, content="исходник\n"):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path):
    checker.git(tmp_path, "init", "-b", "main")
    checker.git(tmp_path, "config", "user.name", "Test")
    checker.git(tmp_path, "config", "user.email", "test@example.invalid")
    for path in ("committed", "staged", "unstaged", "old name", "deleted", "cancelled"):
        write(tmp_path, path)
    write(tmp_path, checker.MANIFEST, json.dumps({"name": "team-skills", "version": "1.0.0"}))
    checker.git(tmp_path, "add", ".")
    checker.git(tmp_path, "commit", "-qm", "base")
    checker.git(tmp_path, "branch", "base")
    return tmp_path


def test_changes_include_all_layers_rename_delete_and_untracked(repo):
    write(repo, "committed", "после commit")
    write(repo, "cancelled", "изменён commit")
    checker.git(repo, "add", ".")
    checker.git(repo, "commit", "-qm", "change")
    write(repo, "staged", "индекс")
    write(repo, "cancelled")  # Возврат к базе не скрывает изменение в HEAD.
    checker.git(repo, "add", ".")
    write(repo, "staged")  # Рабочий файл снова равен HEAD, но индекс отличается.
    write(repo, "unstaged", "рабочий файл")
    checker.git(repo, "mv", "old name", "new name")
    (repo / "deleted").unlink()
    write(repo, "new file")
    base, paths = checker.changed_paths(repo, "base")
    assert base == checker.git(repo, "rev-parse", "base").strip()
    assert paths == {"committed", "staged", "unstaged", "cancelled", "old name", "new name", "deleted", "new file"}


def test_conflict_is_not_a_successful_selection(repo):
    checker.git(repo, "checkout", "-qb", "other")
    write(repo, "committed", "другая ветка")
    checker.git(repo, "commit", "-qam", "other")
    checker.git(repo, "checkout", "main")
    write(repo, "committed", "основная ветка")
    checker.git(repo, "commit", "-qam", "main")
    with pytest.raises(subprocess.CalledProcessError):
        checker.git(repo, "merge", "other")
    with pytest.raises(ValueError, match="конфликты"):
        checker.changed_paths(repo, "base")


def test_version_only_checks_index_even_when_worktree_hides_other_changes(repo):
    write(repo, checker.MANIFEST, json.dumps({"name": "team-skills", "version": "1.0.1"}))
    assert checker.only_version_changed(repo, "base")
    write(repo, checker.MANIFEST, json.dumps({"name": "other", "version": "1.0.1"}))
    checker.git(repo, "add", checker.MANIFEST)
    write(repo, checker.MANIFEST, json.dumps({"name": "team-skills", "version": "1.0.1"}))
    assert not checker.only_version_changed(repo, "base")


def test_skill_selection_keeps_common_checks_and_omits_unrelated_skill():
    selected = checker.select_tests(ROOT, {checker.SKILL_PREFIX + "primerka-predmeta-v-komnate/SKILL.md"})
    assert not selected.full
    assert "tests/test_primerka_predmeta_v_komnate.py" in selected.tests
    assert "tests/test_primerka_image_metadata.py" in selected.tests
    assert "tests/test_check_changed.py" in selected.tests
    assert "tests/test_privacy.py" in selected.tests
    assert "tests/test_language_policy.py" in selected.tests
    assert "tests/test_dopsoglasheniya_po_oplate.py" not in selected.tests


def test_cross_skill_dependencies_and_changed_test_are_included():
    selected = checker.select_tests(ROOT, {
        checker.SKILL_PREFIX + "provedenie-vetki-do-uborki/SKILL.md",
        "tests/test_primerka_image_metadata.py",
    })
    assert not selected.full
    for name in ("test_provedenie_vetki_do_uborki", "test_narabotki_sessii_v_vetku", "test_pr_semantic_verifier", "test_primerka_image_metadata", "test_primerka_predmeta_v_komnate"):
        assert f"tests/{name}.py" in selected.tests


def test_catalog_and_version_keep_all_known_consumers():
    selected = checker.select_tests(ROOT, {"catalog.md", checker.MANIFEST}, version_only=True)
    assert not selected.full
    assert {f"tests/{name}" for name in checker.CATALOG_TESTS} <= set(selected.tests)
    assert "tests/test_plugin_manifest.py" in selected.tests


@pytest.mark.parametrize("path", [
    "tests/conftest.py", "scripts/new_skill.py", "pyproject.toml", ".github/workflows/tests.yml",
    checker.SKILL_PREFIX + "unknown-skill/SKILL.md", "tests/test_new_dependency.py", checker.MANIFEST,
])
def test_unknown_or_shared_change_falls_back_to_full(path):
    assert checker.select_tests(ROOT, {path}).full


def test_missing_test_inventory_falls_back_to_full(tmp_path):
    write(tmp_path, "tests/test_privacy.py", "")
    assert checker.select_tests(tmp_path, {checker.SKILL_PREFIX + "primerka-predmeta-v-komnate/SKILL.md"}).full


def test_map_covers_skill_names_referenced_by_mapped_tests():
    skills = {path.name for path in (ROOT / checker.SKILL_PREFIX).iterdir() if path.is_dir()}
    for name, owners in checker.TEST_OWNERS.items():
        source = (ROOT / "tests" / name).read_text(encoding="utf-8")
        referenced = {skill for skill in skills if skill in source}
        assert referenced <= owners, (name, referenced - owners)


@pytest.mark.parametrize("path", ["tests/new/test_dependency.py", "tests/dependency_test.py"])
def test_unmapped_test_layout_cannot_be_silently_omitted(tmp_path, path):
    for name in checker.TEST_OWNERS:
        write(tmp_path, f"tests/{name}", "")
    write(tmp_path, path, "")
    assert checker.select_tests(tmp_path, {checker.SKILL_PREFIX + "primerka-predmeta-v-komnate/SKILL.md"}).full


def test_missing_base_falls_back_to_full_and_explain_does_not_run_tests(repo, monkeypatch, capsys):
    monkeypatch.setattr(checker, "ROOT", repo)
    assert checker.main(["--base", "missing-ref", "--explain"]) == 0
    assert "Полный прогон" in capsys.readouterr().out
    assert not (repo / ".pytest_cache").exists()


@pytest.mark.parametrize("code", [1, 5])
def test_failure_and_no_tests_collected_are_propagated(monkeypatch, code):
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, code)
    monkeypatch.setattr(checker.subprocess, "run", run)
    assert checker.main(["--full"]) == code
    assert calls == [[sys.executable, "-m", "pytest"]]


def test_focused_run_uses_only_selected_files_without_partial_coverage(monkeypatch):
    monkeypatch.setattr(checker, "changed_paths", lambda *args: ("base", {checker.SKILL_PREFIX + "primerka-predmeta-v-komnate/SKILL.md"}))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(checker.subprocess, "run", run)
    assert checker.main([]) == 0
    assert calls[0][:4] == [sys.executable, "-m", "pytest", "--no-cov"]
    assert "tests/test_primerka_image_metadata.py" in calls[0]
    assert "tests/test_dopsoglasheniya_po_oplate.py" not in calls[0]
