from __future__ import annotations

from pathlib import Path

from conftest import ROOT


CANONICAL_GATE = """Перед любым вопросом проведи контрфактическую проверку:
Представь наиболее вероятные ответы пользователя.
Назови, какое решение, действие или часть результата изменит каждый ответ.
Если следующий шаг при всех ответах одинаков — вопрос запрещён.
Если пользователь уже зафиксировал выбор — запиши его, не открывай заново.
Если неизвестное техническое и его можно проверить самостоятельно — проверь, не спрашивай.
Задавай только ближайший вопрос, ответ на который реально меняет результат."""

SKILLS_DIR = ROOT / "plugins" / "team-skills" / "skills"
QUESTION_DRIVEN_SKILLS = (
    "add-team-skill",
    "browser-preflight",
    "cheap-route-splitter",
    "codex-quick-launch",
    "dopsoglasheniya-po-oplate",
    "goal-contract-shaper",
    "goal-contract-shaper-v3",
    "krupnee-runtime",
    "marketplace-lot-verifier",
    "photo-photobomb-director",
    "raspiska-o-poluchenii-deneg",
    "razbor-bardaka",
    "remont-dogovor-i-raspiski",
    "remont-smeta-builder",
    "str-direct-semantika",
    "vtoroy-mozg",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_question_driven_skills_keep_canonical_gate() -> None:
    for name in QUESTION_DRIVEN_SKILLS:
        path = SKILLS_DIR / name / "SKILL.md"
        content = _read(path)

        assert content.count(CANONICAL_GATE) == 1, (
            f"{name}: канонический контрфактический гейт должен встречаться ровно один раз"
        )
        assert "Проверку проводи внутренне" in content[: content.index(CANONICAL_GATE)], (
            f"{name}: вероятные ответы и карта изменений должны оставаться скрытыми"
        )
        assert content.index(CANONICAL_GATE) < content.index("## Опрос После Использования"), (
            f"{name}: рабочий гейт должен находиться до post-use опроса"
        )


def test_author_contracts_keep_canonical_gate() -> None:
    for path in (ROOT / "CLAUDE.md", ROOT / "CONTRIBUTING.md"):
        assert CANONICAL_GATE in _read(path), f"{path.name}: потерян канонический текст гейта"


def test_question_gate_removes_precomputed_question_batches() -> None:
    razbor = _read(SKILLS_DIR / "razbor-bardaka" / "SKILL.md")
    razbor_example = _read(SKILLS_DIR / "razbor-bardaka" / "examples" / "good-01.md")
    add_skill = _read(SKILLS_DIR / "add-team-skill" / "SKILL.md")
    discovery = _read(
        SKILLS_DIR / "add-team-skill" / "references" / "discovery-gate.md"
    )

    for forbidden in ("раунды по 3–4", "показывать пачкой", "следующий раунд вопросов"):
        assert forbidden not in razbor
    assert "задаёт владельцу раунд вопросов" not in razbor_example

    for forbidden in (
        "1-3 blocker questions",
        "задайте максимум три вопроса",
        "не больше трех вопросов за раунд",
    ):
        assert forbidden not in add_skill + discovery


def test_goal_contract_shaper_keeps_domain_specific_question_gate() -> None:
    content = _read(SKILLS_DIR / "goal-contract-shaper" / "SKILL.md")

    for fragment in (
        "### Настоящий Вопрос",
        "не менее двух разных допустимых вариантов",
        "только пользователь может сообщить необходимый факт, предпочтение или полномочие",
        "единственный допустимый вывод",
    ):
        assert fragment in content
