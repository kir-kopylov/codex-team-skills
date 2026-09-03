import hashlib
import json
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).parents[1]
SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "add-team-skill"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _changed_source_producer(reference: str) -> str:
    start_marker = "# CHANGED_SOURCE_PRODUCER_BEGIN"
    end_marker = "# CHANGED_SOURCE_PRODUCER_END"
    start = reference.index(start_marker)
    end = reference.index(end_marker, start) + len(end_marker)
    return reference[start:end]


def _layer_state_vector(repo: Path, relative_path: str) -> dict[str, str]:
    path = repo / relative_path
    assert not _git(repo, "ls-files", "-u")
    head_parts = _git(repo, "ls-tree", "HEAD", "--", relative_path).split()
    index_parts = _git(repo, "ls-files", "--stage", "--", relative_path).split()
    return {
        "head_oid": _git(repo, "rev-parse", "HEAD"),
        "index_tree_oid": _git(repo, "write-tree"),
        "head_entry": (
            f"{head_parts[0]} {head_parts[2]}" if head_parts else "ABSENT"
        ),
        "index_entry": (
            f"{index_parts[0]} {index_parts[1]}" if index_parts else "ABSENT"
        ),
        "worktree_mode": f"{path.stat().st_mode & 0o777:o}",
        "worktree_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _postcommit_receipt_matches(
    repo: Path,
    relative_path: str,
    precommit: dict[str, str],
    expected_parent_oids: list[str],
) -> bool:
    postcommit = _layer_state_vector(repo, relative_path)
    commit_row = _git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()
    parents = commit_row[1:]
    commit_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    return all(
        (
            parents == expected_parent_oids,
            commit_tree == precommit["index_tree_oid"],
            postcommit["index_tree_oid"] == precommit["index_tree_oid"],
            postcommit["head_entry"] == precommit["index_entry"],
            postcommit["index_entry"] == precommit["index_entry"],
            postcommit["worktree_mode"] == precommit["worktree_mode"],
            postcommit["worktree_sha256"] == precommit["worktree_sha256"],
            not _git(repo, "status", "--porcelain=v1", "--untracked-files=all"),
            not _git(repo, "ls-files", "-u"),
        )
    )


def test_add_team_skill_requires_isolated_test_preflight():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "pyproject.toml",
        "pytest-cov",
        "временную venv",
        "codex --version",
        "LOCAL_NATIVE_SMOKE_BLOCKED",
        "git clone --no-hardlinks",
        "не доустанавливайте пакеты в глобальный Python",
    ):
        assert required in text


def test_add_team_skill_gates_pr_mutation_on_separate_validation():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    for required in (
        "check_pr_governance.py metadata --event-path",
        "наблюдаемого кода возврата `0`",
        "отдельным вызовом выполните `gh pr create --body-file",
        "gh pr view",
        "git ls-remote --heads origin",
        "полный `gh pr checks",
        "старый зелёный job не подтверждает новые метаданные",
        "простой rerun старого job может использовать прежний event payload",
    ):
        assert required in text


def test_add_team_skill_registry_covers_observed_failure_classes():
    metadata = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))
    registry = yaml.safe_load(
        (SKILL_DIR / "known-exceptions.yaml").read_text(encoding="utf-8")
    )

    ids = {item["id"] for item in registry["exceptions"]}
    assert {
        "missing-test-extras-in-system-python",
        "broken-codex-wrapper-treated-as-skill-failure",
        "local-clone-hardlink-failure",
        "pr-mutation-runs-after-failed-validation",
        "stale-pr-governance-after-metadata-edit",
        "blocking-consent-stalls-work",
        "static-green-wrong-first-response",
        "incomplete-or-stale-behavior-probe-batch",
        "behavior-probe-mutated-shared-target",
        "add-team-skill-self-probe-recursion",
    } <= ids
    for relative_path in metadata["example_files"]:
        assert (SKILL_DIR / relative_path).is_file()


def test_add_team_skill_gates_commit_on_observed_first_response():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    example = (SKILL_DIR / "examples" / "good-02-team-ready.md").read_text(
        encoding="utf-8"
    )

    required = (
        "дословную естественную фразу запуска",
        "До запуска зафиксируйте",
        "от одного до трёх наблюдаемых признаков",
        "свежий контекст",
        "только первый ответ",
        "`BEHAVIOR_PROBE_PASS`",
        "`BEHAVIOR_PROBE_FAIL`",
        "`BEHAVIOR_PROBE_BLOCKED`",
        "не делайте commit",
        "Структурный pytest не исполняет модель",
    )
    for fragment in required:
        assert fragment in text

    assert text.index("До запуска зафиксируйте") < text.index("Откройте свежий контекст")
    assert "не предлагает оплату" in example
    assert "открывает commit" in example


def test_add_team_skill_keeps_one_schema_for_structured_outputs_only():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    examples_section = text.split("## Examples", maxsplit=1)[1].split(
        "## Known Exceptions", maxsplit=1
    )[0]
    for required in (
        "структурированный результат",
        "одну каноническую схему",
        "во всех examples и tests",
        "каждый структурированный example",
        "отдельной испорченной копии",
        "изменённым полем, типом или формой",
        "проверка падает",
        "обычным текстовым ответом искусственную схему не вводите",
    ):
        assert required in examples_section


def test_changed_source_producer_covers_all_git_layers(tmp_path):
    reference = (
        SKILL_DIR / "references" / "behavior-probe-batch.md"
    ).read_text(encoding="utf-8")
    producer = _changed_source_producer(reference)
    repo = tmp_path / "repo"
    repo.mkdir()

    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Codex Test")
    _git(repo, "config", "user.email", "codex-test@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")

    tracked_paths = (
        "committed.md",
        "staged.md",
        "unstaged.md",
    )
    for relative_path in tracked_paths:
        (repo / relative_path).write_text("base\n", encoding="utf-8")
    _git(repo, "add", "--", *tracked_paths)
    _git(repo, "commit", "-q", "-m", "base")
    checked_base = _git(repo, "rev-parse", "HEAD")

    (repo / "committed.md").write_text("committed branch diff\n", encoding="utf-8")
    _git(repo, "add", "--", "committed.md")
    _git(repo, "commit", "-q", "-m", "branch change")
    (repo / "committed.md").write_text("base\n", encoding="utf-8")
    (repo / "staged.md").write_text("staged diff\n", encoding="utf-8")
    _git(repo, "add", "--", "staged.md")
    (repo / "staged.md").write_text("base\n", encoding="utf-8")
    (repo / "unstaged.md").write_text("unstaged diff\n", encoding="utf-8")
    untracked_path = Path("plugins/team-skills/skills/demo/agents/openai.yaml")
    (repo / untracked_path).parent.mkdir(parents=True)
    (repo / untracked_path).write_text("interface:\n", encoding="utf-8")

    shell = "set -u\nrepo=$1\nchecked_base=$2\n" + producer
    completed = subprocess.run(
        ["bash", "-c", shell, "changed-source-test", str(repo), checked_base],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == sorted(
        [*tracked_paths, untracked_path.as_posix()]
    )

    for unsafe_base in ("missing-base", "--cached", "--quiet"):
        invalid_base = subprocess.run(
            ["bash", "-c", shell, "changed-source-test", str(repo), unsafe_base],
            check=False,
            capture_output=True,
            text=True,
        )
        assert invalid_base.returncode != 0


def test_layer_state_vector_detects_masked_index_and_head_changes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Codex Test")
    _git(repo, "config", "user.email", "codex-test@example.invalid")
    _git(repo, "config", "commit.gpgsign", "false")

    tracked = repo / "tracked.md"
    tracked.write_text("base\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.md")
    _git(repo, "commit", "-q", "-m", "base")

    tracked.write_text("staged one\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.md")
    tracked.write_text("base\n", encoding="utf-8")
    before = _layer_state_vector(repo, "tracked.md")

    tracked.write_text("staged two\n", encoding="utf-8")
    _git(repo, "add", "--", "tracked.md")
    tracked.write_text("base\n", encoding="utf-8")
    after_index_change = _layer_state_vector(repo, "tracked.md")

    assert before["worktree_sha256"] == after_index_change["worktree_sha256"]
    assert before["head_oid"] == after_index_change["head_oid"]
    assert before["index_tree_oid"] != after_index_change["index_tree_oid"]
    assert before != after_index_change

    _git(repo, "commit", "-q", "-m", "commit staged bytes")
    after_commit = _layer_state_vector(repo, "tracked.md")

    assert after_index_change["worktree_sha256"] == after_commit["worktree_sha256"]
    assert after_index_change["index_tree_oid"] == after_commit["index_tree_oid"]
    assert after_index_change["head_oid"] != after_commit["head_oid"]
    assert after_index_change != after_commit


def test_postcommit_receipt_accepts_create_and_amend_only_with_exact_proof(tmp_path):
    create_repo = tmp_path / "create"
    create_repo.mkdir()
    _git(create_repo, "init", "-q")
    _git(create_repo, "config", "user.name", "Codex Test")
    _git(create_repo, "config", "user.email", "codex-test@example.invalid")
    _git(create_repo, "config", "commit.gpgsign", "false")
    create_file = create_repo / "tracked.md"
    create_file.write_text("base\n", encoding="utf-8")
    _git(create_repo, "add", "--", "tracked.md")
    _git(create_repo, "commit", "-q", "-m", "base")
    create_file.write_text("create candidate\n", encoding="utf-8")
    _git(create_repo, "add", "--", "tracked.md")
    create_precommit = _layer_state_vector(create_repo, "tracked.md")
    create_parents = [create_precommit["head_oid"]]
    _git(create_repo, "commit", "-q", "-m", "create candidate")

    assert _postcommit_receipt_matches(
        create_repo, "tracked.md", create_precommit, create_parents
    )
    assert not _postcommit_receipt_matches(
        create_repo, "tracked.md", create_precommit, ["0" * 40]
    )
    wrong_tree = dict(create_precommit)
    wrong_tree["index_tree_oid"] = "0" * 40
    assert not _postcommit_receipt_matches(
        create_repo, "tracked.md", wrong_tree, create_parents
    )

    amend_repo = tmp_path / "amend"
    amend_repo.mkdir()
    _git(amend_repo, "init", "-q")
    _git(amend_repo, "config", "user.name", "Codex Test")
    _git(amend_repo, "config", "user.email", "codex-test@example.invalid")
    _git(amend_repo, "config", "commit.gpgsign", "false")
    amend_file = amend_repo / "tracked.md"
    amend_file.write_text("base\n", encoding="utf-8")
    _git(amend_repo, "add", "--", "tracked.md")
    _git(amend_repo, "commit", "-q", "-m", "base")
    amend_file.write_text("published candidate\n", encoding="utf-8")
    _git(amend_repo, "add", "--", "tracked.md")
    _git(amend_repo, "commit", "-q", "-m", "published candidate")
    amend_file.write_text("amended candidate\n", encoding="utf-8")
    _git(amend_repo, "add", "--", "tracked.md")
    amend_precommit = _layer_state_vector(amend_repo, "tracked.md")
    amend_parents = _git(
        amend_repo, "rev-list", "--parents", "-n", "1", "HEAD"
    ).split()[1:]
    _git(amend_repo, "commit", "--amend", "-q", "-m", "amended candidate")

    assert amend_parents != [amend_precommit["head_oid"]]
    assert _postcommit_receipt_matches(
        amend_repo, "tracked.md", amend_precommit, amend_parents
    )
    assert not _postcommit_receipt_matches(
        amend_repo,
        "tracked.md",
        amend_precommit,
        [*amend_parents, "0" * 40],
    )


def test_add_team_skill_batches_changed_first_response_probes_privately():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    reference = (
        SKILL_DIR / "references" / "behavior-probe-batch.md"
    ).read_text(encoding="utf-8")
    example = (
        SKILL_DIR / "examples" / "good-07-batch-first-responses.md"
    ).read_text(encoding="utf-8")
    metadata = yaml.safe_load((SKILL_DIR / "skill.yaml").read_text(encoding="utf-8"))

    batch_section = text.split("### Пакетная Проба Изменённых Skills", 1)[1].split(
        "\n## ", 1
    )[0]
    normalized_batch = " ".join(batch_section.split())
    normalized_reference = " ".join(reference.split())
    normalized_example = " ".join(example.split())
    publication_section = reference.split("## Что Можно Публиковать", 1)[1]

    assert "в том же ходе вычислите охват и запустите его строки" in text
    assert "не завершайте ход строкой запуска" in text

    for required in (
        "все новые или существенно изменённые skills",
        "полную библиотеку",
        "Каждый skill запускайте в отдельном свежем контексте",
        "После `FAIL` или `BLOCKED` продолжайте остальные строки",
        "пока каждая строка охвата не получила",
        "`required_source`",
        "фактически вошёл в `loaded_source`",
        "fail-closed объединения committed, staged и unstaged tracked-файлов с untracked-файлами",
        "полный exact commit OID",
        "`batch_excluded_source`",
        "`batch_scope_fingerprint`",
        "`index_tree_oid = tested_tree`",
        "заранее выбранным `CREATE`/`AMEND`",
        "фактические parents равны заранее сохранённым",
        "entries `HEAD`/index/worktree каждого пути",
        "commit tree равен `tested_tree`",
        "`source_scope_fingerprint`",
        "Изменение index bytes, executable mode, excluded-файла или основания его исключения после пробы",
        "Symlink нельзя загружать или передавать target-агенту",
        "Сырые фразы, критерии и ответы храните только приватно",
        "одноразовой изолированной копии",
        "двухуровневом fixture",
        "references/behavior-probe-batch.md",
    ):
        assert required in normalized_batch

    for failure_class in (
        "NOTICE_ONLY",
        "PROMISE_ONLY",
        "BLOCKING_CONSENT",
        "REDUNDANT_CONFIRMATION",
        "USER_AS_OBSERVER",
        "TASK_SPECIFIC",
    ):
        assert f"`{failure_class}`" not in batch_section
        assert f"`{failure_class}`" in reference

    for freshness_fragment in (
        "`checked_base`",
        "`batch_changed_source`",
        "`batch_attribution`",
        "`batch_excluded_source`",
        "`batch_scope_fingerprint`",
        "`layer_state_vector`",
        "`head_oid`",
        "`commit_transition`",
        "`expected_parent_oids`",
        "`index_tree_oid`",
        "`changed_source`",
        "`excluded_changed_source`",
        "`source_scope_fingerprint`",
        "`required_source`",
        "`loaded_source`",
        "`target_fingerprint`",
        "`probe_contract_fingerprint`",
        "keyed digest",
        "`phrase_source`, точная `trigger_phrase`, `criteria` в исходном порядке и `forbidden_behavior`",
        "приватный ключ конкретного пакета",
        "Обычный неконтролируемый hash короткой фразы не считается privacy-safe",
        "repo-relative",
        "`required_source ⊆ loaded_source`",
        "точные пути из `changed_source`",
        "всегда `known-exceptions.yaml`",
        "`known-exceptions.yaml` входит в `required_source` для каждой строки",
        "независимо от причины включения skill",
        "разложите его без пропусков и пересечений",
        "`skill.yaml`, `agents/openai.yaml`",
        "Неизвестный или неучтённый путь даёт",
        "непересекающееся разложение на `scope_reason` и `excluded_changed_source`",
        "Неполный или недоказуемый source scope даёт",
        "content hash",
        "текущее содержимое и mode рабочего дерева",
        "content hash текущих Git-эквивалентных bytes либо явным маркером `DELETED`",
        "каждый путь `excluded_changed_source` вместе с текстом его проверяемого доказательства",
        "изменение самого доказательства исключения аннулирует строку",
        "Git mode и content hash",
        "проекция `head_entry`, `index_entry` и `worktree_entry`",
        "одинаковые path set и worktree hash не скрывают изменение bytes или mode в `HEAD` либо index",
        "precommit `index_tree_oid` и `tested_tree` должны быть одним OID",
        "не подменяйте `AMEND` правилом `first parent = precommit head_oid`",
        "postcommit `head_entry` и `index_entry` должны в точности равняться precommit `index_entry`",
        '`git -C "$repo" hash-object --path="$path" -- "$path"`',
        "commit считается новым кандидатом и требует новой пробы",
        "смена mode при неизменных bytes меняет fingerprint",
        "Symlink нельзя включать в `required_source` или `loaded_source`",
        "если различия её канонических входов ограничены доказанными новыми",
        "равенства старого и нового digest не требуйте",
        "только если одновременно совпадают",
        "аннулируйте только строки",
        "после переноса на новый `checked_base`",
        "аннулируйте весь пакет",
        "без push-доступа к настоящему remote",
        "Общий worktree пользователя",
        "Нерекурсивная Строка Оркестратора",
        "строго в два уровня",
        "не меньше двух других тестовых skills",
        "`add-team-skill` отсутствует",
        "Третьего уровня нет",
        "внешняя строка `add-team-skill` получает обычный",
        "внешний пакет продолжает остальные строки",
        "заново вычисленный `probe_contract_fingerprint` не совпал — аннулируйте эту строку",
        "полный `loaded_source`, `target_fingerprint` и `probe_contract_fingerprint`",
        "Любое иное расхождение",
        "`BEHAVIOR_PROBE_BLOCKED`",
        "# CHANGED_SOURCE_PRODUCER_BEGIN",
        '"rev-parse", "--verify", "--end-of-options"',
        'paths = nul_paths(["diff", *diff_flags, base_oid, "HEAD", "--"])',
        'paths.extend(nul_paths(["diff", "--cached", *diff_flags, "HEAD", "--"]))',
        'paths.extend(nul_paths(["diff", *diff_flags, "--"]))',
        '"ls-files", "--others", "--exclude-standard", "-z"',
        "committed branch diff, staged, unstaged tracked и untracked-файлы",
    ):
        assert freshness_fragment in normalized_reference

    for source_scope_fragment in (
        "полный repo-relative список обязательных источников",
        "`known-exceptions.yaml` входит в обязательный список каждой",
        "если любой агент загрузил один `SKILL.md`",
        "обязательную загрузку `known-exceptions.yaml`",
        "Изменённые `agents/openai.yaml` и `skill.yaml` всегда входят",
        "Общая причина «skill изменён»",
        "полный учёт каждого изменённого пути",
        "покрытие остальных обязательных источников",
        "новый ещё не staged `agents/openai.yaml`",
        "изменение содержимого исключённого example",
        "терять новый untracked-файл до staging",
        "путь из branch commit или index не исчезает",
        "Каждый путь глобального снимка назначен одной или нескольким строкам",
        "`batch_scope_fingerprint`",
        "выбранный `CREATE` или `AMEND`",
        "у `AMEND` parents заменяемого commit",
        "замена только staged bytes при прежних path set и worktree hash аннулирует пакет",
        "Commit tree равен precommit `index_tree_oid` и `tested_tree`",
        "commit без совпадения parents и точного `tested_tree`",
        "смена `100644` на `100755`",
        "Symlink может быть учтён в batch, но не загружается",
        "Равенство старого и нового digest при разных SHA не требуется",
    ):
        assert source_scope_fragment in normalized_example

    for private_fragment in (
        "Сырые пользовательские запросы",
        "точные приватные фразы",
        "критерии и ответы модели",
        "`layer_state_vector`",
        "`batch_scope_fingerprint`",
        "`source_scope_fingerprint`",
        "`probe_contract_fingerprint`",
        "не коммитите и не вставляйте в PR",
    ):
        assert private_fragment in normalized_reference

    assert (
        "`layer_state_vector`, а также `batch_scope_fingerprint`, "
        "`source_scope_fingerprint`, "
        "`target_fingerprint` и "
        "`probe_contract_fingerprint` не коммитите и не вставляйте в PR"
        in " ".join(publication_section.split())
    )

    assert "проверь первые ответы всех изменённых skills перед PR" in metadata[
        "natural_triggers"
    ]
    assert "examples/good-07-batch-first-responses.md" in metadata[
        "example_files"
    ]
    assert metadata["last_reviewed"] == "2026-08-24"
    assert "три существенно изменённых skill" in normalized_example
    assert "сырые фразы, критерии и ответы остаются приватными" in normalized_example
    assert "фактически загруженные источники" in normalized_example
    assert "одноразовую копию точного target" in normalized_example
    assert "общий worktree не меняется" in normalized_example
    assert "Внешний реальный пакет включает `add-team-skill`" in normalized_example
    assert "внутреннем diff есть два других существенно изменённых skill" in normalized_example
    assert "нет `add-team-skill`" in normalized_example
    assert "второй и последний уровень" in normalized_example
    assert "не создают третьего пакета" in normalized_example
    assert "внешняя строка получает `BEHAVIOR_PROBE_PASS`" in normalized_example
    assert "внешний пакет в любом случае продолжает остальные строки" in normalized_example
    assert "приватные digests пакета, охвата и контракта каждой строки" in (
        normalized_example
    )
    assert "изменение фразы, порядка или содержания критериев" in normalized_example
    assert "В PR не попадает ни один из приватных fingerprints" in normalized_example
    assert "повторяет только затронутые строки" in normalized_example
    assert "аннулирует весь пакет" in normalized_example


def test_known_exceptions_change_is_in_behavior_probe_batch_scope():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    reference = (
        SKILL_DIR / "references" / "behavior-probe-batch.md"
    ).read_text(encoding="utf-8")
    example = (
        SKILL_DIR / "examples" / "good-07-batch-first-responses.md"
    ).read_text(encoding="utf-8")
    normalized_reference = " ".join(reference.split())
    normalized_example = " ".join(example.split())

    assert "Изменение `known-exceptions.yaml` считается поведенческим" in text
    assert (
        "Изменение только `known-exceptions.yaml` тоже включает skill"
        in normalized_reference
    )
    assert (
        "подходящий `do_next_time` способен изменить первый ответ"
        in normalized_reference
    )
    assert (
        "у одного из них изменён только `known-exceptions.yaml`"
        in normalized_example
    )
