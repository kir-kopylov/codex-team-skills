from __future__ import annotations

from conftest import ROOT, load_registry


SPLIT_BRAIN = ROOT / "plugins" / "team-skills" / "skills" / "windows-app-connectivity-split-brain"
GOAL_SHAPER = ROOT / "plugins" / "team-skills" / "skills" / "goal-contract-shaper"
GOAL_SHAPER_V3 = ROOT / "plugins" / "team-skills" / "skills" / "goal-contract-shaper-v3"
SKILL_METHODOLOGIST = ROOT / "plugins" / "team-skills" / "skills" / "skill-methodologist"
GIT_REALITY_CHECK = ROOT / "plugins" / "team-skills" / "skills" / "git-worktree-reality-check"


def test_windows_app_connectivity_split_brain_declares_layer_matrix_and_evidence_refs() -> None:
    body = (SPLIT_BRAIN / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(SPLIT_BRAIN)

    assert registry["status"] == "experimental"
    assert "PowerShell/Codex sandbox как по прямому факту" in body
    for fragment in (
        "user-visible app UI",
        "процесс/сокеты",
        "app proxy config",
        "Windows proxy",
        "DNS/fakeDNS",
        "routes/interfaces",
        "VPN core",
        "references/repair-state-bundle.md",
        "references/gui-evidence-ladder.md",
        "references/known-failure-patterns.md",
    ):
        assert fragment in body


def test_goal_contract_shaper_requires_completion_gate_for_false_completion_risk() -> None:
    body = (GOAL_SHAPER / "SKILL.md").read_text(encoding="utf-8")

    for fragment in (
        "## Completion Gate",
        "user-visible success",
        "direct evidence",
        "forbidden false positives",
        "close allowed: yes/no",
        "процесс, форма входа, spinner, старый скрин или CLI-тест",
    ):
        assert fragment in body


def test_goal_contract_shaper_v3_is_explicit_experimental_completion_gate_variant() -> None:
    body = (GOAL_SHAPER_V3 / "SKILL.md").read_text(encoding="utf-8")
    registry = load_registry(GOAL_SHAPER_V3)

    assert registry["status"] == "experimental"
    for fragment in (
        "только при явном вызове `goal-contract-shaper-v3`",
        "Смысловой запрос без прямого вызова маршрутизируйте в базовый "
        "`goal-contract-shaper`",
        "не запускайте v3 и не спрашивайте о его применении",
        "Применяю экспериментальный навык **«Усиленная проверка контракта цели»** "
        "(обратная связь — @kir-kopylov):",
        "продолжайте работу в том же ответе, не ожидая реакции",
        "## Completion Gate",
        "user-visible success",
        "direct evidence",
        "forbidden false positives",
        "close allowed: yes/no",
        "CLI/PowerShell/Codex sandbox",
        "Эпистемический гейт",
        "Грант = след, а не жест",
    ):
        assert fragment in body


def test_skill_methodologist_routes_incidents_without_skill_inflation() -> None:
    body = (SKILL_METHODOLOGIST / "SKILL.md").read_text(encoding="utf-8")
    methodology = (SKILL_METHODOLOGIST / "references" / "skill-methodology.md").read_text(encoding="utf-8")

    for fragment in (
        "incident-to-library decision",
        "new skill / patch existing skill / shared reference / script / no library change",
        "Не превращайте каждый инцидент в новый skill",
    ):
        assert fragment in body
    assert "Incident-To-Library Decision" in methodology


def test_git_reality_launch_notice_cannot_replace_read_only_snapshot() -> None:
    body = (GIT_REALITY_CHECK / "SKILL.md").read_text(encoding="utf-8")

    assert "Не завершайте ответ одной строкой уведомления" in body
    assert "до отправки первого ответа обязательно выполните через терминал read-only снимок Git" in body
    assert "верните наблюдаемые факты в этом ответе" in body
