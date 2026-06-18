from __future__ import annotations

import copy
import importlib.util
import py_compile

import pytest

from conftest import ROOT, load_registry


SKILL_DIR = ROOT / "plugins" / "team-skills" / "skills" / "dopsoglasheniya-po-oplate"
SCRIPT = SKILL_DIR / "scripts" / "build_ds.py"


def test_dopsoglasheniya_asset_has_owner_and_team_ready_status() -> None:
    registry = load_registry(SKILL_DIR)
    assert registry["owner"] == "@kir-kopylov"
    assert "коллега по договорной работе" in registry.get("authors", [])
    assert registry["status"] == "team-ready"


def test_dopsoglasheniya_generator_has_no_nul_bytes_and_compiles(tmp_path) -> None:
    source = SCRIPT.read_bytes()
    assert b"\x00" not in source
    py_compile.compile(str(SCRIPT), cfile=str(tmp_path / "build_ds.pyc"), doraise=True)


# --- поведенческие тесты генератора DOCX -----------------------------------
# Запускают сам генератор (как тесты remont-smeta-builder), а не только
# проверяют, что он компилируется. Модуль импортирует python-docx на верхнем
# уровне, поэтому без пакета тесты корректно скипаются.

pytest.importorskip("docx")


def _load_module():
    spec = importlib.util.spec_from_file_location("build_ds", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MOD = _load_module()


# Минимально валидный конфиг постоплаты; отдельные тесты мутируют копию.
BASE_CFG = {
    "number": 3,
    "contract_date": "01.01.2020",
    "sign_date": "01.06.2024",
    "address": "г. Тест, ул. Тестовая, д. 1",
    "city": "г. Тест",
    "ds_type": "postoplata",
    "tenant": {"full_clause": "ООО «Арендатор», в лице директора", "short_name": "ООО «Арендатор»", "signer_short": "Иванов И.И."},
    "landlord": {"type": "individual", "fio": "Петров Петр Петрович", "fio_short": "Петров П.П.", "inn": "1234567890"},
    "sign_block": "vertical",
    "params": {"period_start": "июнь 2024", "period_end": "август 2024", "pay_day": "10"},
}


def _cfg(**overrides):
    cfg = copy.deepcopy(BASE_CFG)
    cfg.update(overrides)
    return cfg


def test_require_rejects_missing_and_empty() -> None:
    assert MOD.require({"k": "v"}, "k") == "v"
    for bad in ({}, {"k": None}, {"k": ""}):
        with pytest.raises(ValueError):
            MOD.require(bad, "k")


def test_suffix_follows_gender() -> None:
    assert MOD.suffix("m", "ый", "ая") == "ый"
    assert MOD.suffix("f", "ый", "ая") == "ая"


def test_landlord_clause_individual_self_employed_and_ip() -> None:
    base = {"number": "3", "address": "адрес", "contract_date": "01.01.2020", "object_kind": "помещения"}

    individual = MOD.landlord_clause(
        {"landlord": {"type": "individual", "fio": "Петров П.П.", "inn": "1234567890"}},
        base["number"], base["address"], base["contract_date"], base["object_kind"],
    )
    assert "Петров П.П." in individual and "ИНН 1234567890" in individual

    self_employed = MOD.landlord_clause(
        {"landlord": {"type": "self_employed", "fio": "Петров П.П.", "inn": "1", "npd_date": "01.01.2021"}},
        base["number"], base["address"], base["contract_date"], base["object_kind"],
    )
    assert "налога на профессиональный доход" in self_employed and "01.01.2021" in self_employed

    ip = MOD.landlord_clause(
        {"landlord": {"type": "ip", "fio": "Петров П.П.", "inn": "1", "ogrnip": "999", "ip_date": "02.02.2019"}},
        base["number"], base["address"], base["contract_date"], base["object_kind"],
    )
    assert "Индивидуальный предприниматель" in ip and "ОГРНИП 999" in ip


def test_landlord_clause_unknown_type_raises() -> None:
    with pytest.raises(ValueError):
        MOD.landlord_clause(
            {"landlord": {"type": "llc", "fio": "Х", "inn": "1"}},
            "3", "адрес", "01.01.2020", "помещения",
        )


def test_landlord_clause_female_gender_inflects() -> None:
    clause = MOD.landlord_clause(
        {"landlord": {"type": "individual", "fio": "Петрова П.П.", "inn": "1", "gender": "f"}},
        "3", "адрес", "01.01.2020", "помещения",
    )
    assert "именуемая" in clause


def test_body_postoplata_numbers_and_optional_blocks() -> None:
    # без опций: пункты 1..4 + хвост 5,6
    base = MOD.body_postoplata({"period_start": "a", "period_end": "b", "pay_day": "10"})
    assert base[0].startswith("1.") and base[-2].startswith("5.") and base[-1].startswith("6.")

    # доп. месяц сдвигает нумерацию вступления в силу и хвоста
    extra = MOD.body_postoplata({
        "period_start": "a", "period_end": "b", "pay_day": "10",
        "extra_month": "октябрь", "extra_amount_digits": "100 000", "extra_amount_words": "сто тысяч",
    })
    assert any(item.startswith("4.") and "октябрь" in item for item in extra)
    assert extra[-2].startswith("6.") and extra[-1].startswith("7.")


def test_body_postoplata_requires_words_when_amount_given() -> None:
    with pytest.raises(ValueError):
        MOD.body_postoplata({"period_start": "a", "period_end": "b", "pay_day": "10", "rent_amount_digits": "50000"})


def test_bodies_dispatch_covers_all_ds_types() -> None:
    assert set(MOD.BODIES) == {"postoplata", "vychet", "izmenenie"}
    for ds_type in ("vychet", "izmenenie"):
        items = MOD.BODIES[ds_type]({"month": "июль", "amount_digits": "1", "amount_words": "один"})
        assert items[0].startswith("1.") and items[-1].startswith("4.")


def test_build_writes_valid_docx_with_title_and_address(tmp_path) -> None:
    from docx import Document

    out = tmp_path / "ds.docx"
    MOD.build(_cfg(), out)
    assert out.exists() and out.stat().st_size > 0

    doc = Document(str(out))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ N 3" in text
    assert "г. Тест, ул. Тестовая, д. 1" in text
    assert "ООО «Арендатор», в лице директора" in text
    assert "Подписи сторон:" in text


def test_build_raises_on_missing_required_field(tmp_path) -> None:
    cfg = _cfg()
    del cfg["number"]
    with pytest.raises(ValueError):
        MOD.build(cfg, tmp_path / "no-number.docx")


def test_build_rejects_unknown_ds_type_and_sign_block(tmp_path) -> None:
    with pytest.raises(ValueError):
        MOD.build(_cfg(ds_type="unknown"), tmp_path / "bad-type.docx")
    with pytest.raises(ValueError):
        MOD.build(_cfg(sign_block="diagonal"), tmp_path / "bad-sign.docx")


def test_main_reports_usage_on_wrong_argc() -> None:
    assert MOD.main(["build_ds.py"]) == 2
    assert MOD.main(["build_ds.py", "only-one"]) == 2
