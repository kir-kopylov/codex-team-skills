#!/usr/bin/env python3
"""Выбрать локальные проверки по изменениям; полный pytest выполняется в CI."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SKILL_PREFIX = "plugins/team-skills/skills/"
MANIFEST = "plugins/team-skills/.codex-plugin/plugin.json"

# Только проверенные связи. Все остальные test_*.py запускаются как общие.
# Несколько владельцев означают, что тест читает или проверяет несколько навыков.
TEST_OWNERS = {
    "test_dobavlenie_navyka_v_biblioteku.py": {"dobavlenie-navyka-v-biblioteku"},
    "test_dobavlenie_navyka_v_biblioteku_review_loop.py": {"dobavlenie-navyka-v-biblioteku", "snos-podsistemy-iz-koda"},
    "test_dopsoglasheniya_po_oplate.py": {"dopsoglasheniya-po-oplate", "smeta-remonta-do-dogovora"},
    "test_dopusk_saytov_do_tsikla.py": {"dopusk-saytov-do-tsikla"},
    "test_evidence_digest_skills.py": {"daydzhest-proverennyh-izmeneniy", "podtverzhdenie-planovoy-rassylki"},
    "test_goal_contract_feedback_log.py": {"kontrakt-tseli-do-starta"},
    "test_kak_drugie_reshili.py": {"kak-drugie-reshili", "peresmotr-predposylok-posle-povtora"},
    "test_karta_sistemy_do_pravok.py": {"karta-sistemy-do-pravok"},
    "test_kontrakt_navyka_do_sborki.py": {"kontrakt-navyka-do-sborki"},
    "test_kontrakt_tseli_do_starta.py": {"kontrakt-tseli-do-starta"},
    "test_lechenie_terminala_pri_vpn.py": {"lechenie-terminala-pri-vpn"},
    "test_narabotki_sessii_v_vetku.py": {"narabotki-sessii-v-vetku", "provedenie-vetki-do-uborki", "sverka-git-pered-deystviem"},
    "test_navyk_iz_chastogo_zaprosa.py": {"navyk-iz-chastogo-zaprosa"},
    "test_obnovlenie_biblioteki_navykov.py": {"obnovlenie-biblioteki-navykov", "sverka-aktivnoy-versii-navykov", "razgrom-plana-na-naivnost"},
    "test_otbor_navykov_iz_chata.py": {"otbor-navykov-iz-chata", "razbor-chata-na-artefakty", "kontrakt-navyka-do-sborki"},
    "test_peredelka_dogovorov_arendy.py": {"peredelka-dogovorov-arendy"},
    "test_peresmotr_predposylok_posle_povtora.py": {"peresmotr-predposylok-posle-povtora", "kak-drugie-reshili"},
    "test_perevod_smennyh_svodok.py": {"perevod-smennyh-svodok"},
    "test_podgotovka_windows_k_zapisi.py": {"podgotovka-windows-k-zapisi"},
    "test_podklyuchenie_sip_u_operatora.py": {"podklyuchenie-sip-u-operatora"},
    "test_poisk_sekretov_bez_raskrytiya.py": {"poisk-sekretov-bez-raskrytiya"},
    "test_pr_semantic_verifier.py": {"pr-semantic-verifier", "provedenie-vetki-do-uborki", "dobavlenie-navyka-v-biblioteku", "peresmotr-predposylok-posle-povtora", "razgrom-plana-na-naivnost"},
    "test_pravilo_iz_zhurnala_sboev.py": {"pravilo-iz-zhurnala-sboev"},
    "test_primerka_image_metadata.py": {"primerka-predmeta-v-komnate"},
    "test_primerka_predmeta_v_komnate.py": {"primerka-predmeta-v-komnate"},
    "test_privyazka_git_k_gitlab.py": {"privyazka-git-k-gitlab"},
    "test_provedenie_vetki_do_uborki.py": {"provedenie-vetki-do-uborki"},
    "test_proverka_aktualnosti_v_momente.py": {"proverka-aktualnosti-v-momente"},
    "test_proverka_broney_i_izmeneniy.py": {"proverka-broney-i-izmeneniy"},
    "test_proverka_prichin_sboya.py": {"proverka-prichin-sboya", "peresmotr-predposylok-posle-povtora"},
    "test_razbor_chata_na_artefakty.py": {"razbor-chata-na-artefakty"},
    "test_razgrom_plana_na_naivnost.py": {"razgrom-plana-na-naivnost"},
    "test_remont_docs_pack.py": {"remont-dogovor-i-raspiski", "raspiska-o-poluchenii-deneg"},
    "test_repair_state_safety_skills.py": {"kontrakt-tseli-do-starta", "goal-contract-shaper-v3", "sloy-obryva-seti-windows", "kontrakt-navyka-do-sborki", "sverka-git-pered-deystviem"},
    "test_semantika_direkta_po_adresam.py": {"semantika-direkta-po-adresam"},
    "test_shag_posle_prervannoy_tseli.py": {"shag-posle-prervannoy-tseli", "kontrakt-tseli-do-starta", "narabotki-sessii-v-vetku", "sverka-git-pered-deystviem"},
    "test_slepok_oformleniya_google_tablitsy.py": {"slepok-oformleniya-google-tablitsy"},
    "test_smeta_remonta_do_dogovora.py": {"smeta-remonta-do-dogovora"},
    "test_sverka_aktivnoy_versii_navykov.py": {"sverka-aktivnoy-versii-navykov"},
    "test_sverka_rashodov_po_istochnikam.py": {"sverka-rashodov-po-istochnikam"},
    "test_sverka_vyruchki_ehous.py": {"sverka-rashodov-po-istochnikam"},
    "test_sverka_zapuskov_pri_rashozhdenii.py": {"sverka-zapuskov-pri-rashozhdenii", "proverka-prichin-sboya", "dobavlenie-navyka-v-biblioteku"},
    "test_udalenie_prilozheniya_s_mac.py": {"udalenie-prilozheniya-s-mac"},
    "test_upakovka_navyka_odnim_faylom.py": {"upakovka-navyka-odnim-faylom"},
    "test_veer_resheniy_do_chertezha.py": {"veer-resheniy-do-chertezha"},
    "test_verdikt_po_otstavshey_vetke.py": {"verdikt-po-otstavshey-vetke"},
    "test_verstka_docx_po_standartu.py": {"verstka-docx-po-standartu", "smeta-remonta-do-dogovora"},
}
CATALOG_TESTS = {
    "test_dobavlenie_navyka_v_biblioteku_review_loop.py",
    "test_navyk_iz_chastogo_zaprosa.py",
    "test_obnovlenie_biblioteki_navykov.py",
    "test_proverka_aktualnosti_v_momente.py",
}


@dataclass
class Selection:
    full: bool
    tests: list[str]
    reasons: list[str]


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True,
    )
    return result.stdout


def changed_paths(root: Path, base_ref: str) -> tuple[str, set[str]]:
    base = git(root, "rev-parse", "--verify", "--end-of-options", f"{base_ref}^{{commit}}").strip()
    base = git(root, "merge-base", base, "HEAD").strip()
    if git(root, "ls-files", "--unmerged", "-z"):
        raise ValueError("Есть неразрешённые конфликты Git.")
    commands = (
        ("diff", "--name-only", "-z", "--no-renames", base, "HEAD", "--"),
        ("diff", "--name-only", "-z", "--no-renames", "--cached", "--"),
        ("diff", "--name-only", "-z", "--no-renames", "--"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    )
    paths = set()
    for command in commands:
        paths.update(filter(None, git(root, *command).split("\0")))
    return base, paths


def only_version_changed(root: Path, base: str) -> bool:
    try:
        contents = [git(root, "show", f"{ref}:{MANIFEST}") for ref in (base, "HEAD", "")]
        contents.append((root / MANIFEST).read_text(encoding="utf-8"))
        payloads = [json.loads(content) for content in contents]
        for payload in payloads:
            del payload["version"]
        return all(payload == payloads[0] for payload in payloads[1:])
    except (subprocess.CalledProcessError, OSError, ValueError, KeyError, TypeError):
        return False


def select_tests(root: Path, paths: set[str], *, version_only: bool = False) -> Selection:
    available = {path.name for path in (root / "tests").glob("test_*.py")}
    known_skills = set().union(*TEST_OWNERS.values())
    selected = available - TEST_OWNERS.keys()
    affected = set()
    reasons = []
    test_files = set((root / "tests").rglob("test_*.py")) | set((root / "tests").rglob("*_test.py"))
    unsupported_tests = any(
        path.parent != root / "tests" or not path.name.startswith("test_")
        for path in test_files
    )
    if not available or TEST_OWNERS.keys() - available or unsupported_tests:
        return Selection(True, [], ["Состав тестов изменился; нужны все проверки."])
    for path in sorted(paths):
        parts = Path(path).parts
        if path.startswith(SKILL_PREFIX) and len(parts) >= 5 and parts[3] in known_skills:
            affected.add(parts[3])
            reasons.append(f"{path} → проверки навыка {parts[3]} и общие проверки")
        elif path == "catalog.md":
            selected.update(CATALOG_TESTS)
            reasons.append(f"{path} → общие проверки и все известные читатели каталога")
        elif path == MANIFEST and version_only:
            reasons.append(f"{path} → общие проверки манифеста; изменена только версия")
        elif len(parts) == 2 and parts[0] == "tests" and parts[1] in TEST_OWNERS:
            affected.update(TEST_OWNERS[parts[1]])
            reasons.append(f"{path} → тест и проверки связанных навыков")
        else:
            return Selection(True, [], [f"{path} → общая или неизвестная зависимость; нужен полный прогон."])
    for test, owners in TEST_OWNERS.items():
        if owners & affected:
            selected.add(test)
    if not paths:
        reasons.append("Изменений относительно базы нет; выполняются общие проверки.")
    return Selection(False, [f"tests/{name}" for name in sorted(selected)], reasons)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="база сравнения, по умолчанию origin/main")
    parser.add_argument("--full", action="store_true", help="выполнить полный pytest")
    parser.add_argument("--explain", action="store_true", help="показать выбор без запуска тестов")
    args = parser.parse_args(argv)
    if args.full:
        selection = Selection(True, [], ["Полный прогон запрошен явно."])
    else:
        try:
            base, paths = changed_paths(ROOT, args.base)
            print(f"База сравнения: {base}", flush=True)
            selection = select_tests(ROOT, paths, version_only=MANIFEST in paths and only_version_changed(ROOT, base))
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 2
        except (subprocess.CalledProcessError, OSError) as error:
            selection = Selection(True, [], [f"Не удалось определить изменения ({error}); нужен полный прогон."])
    for reason in selection.reasons:
        print(reason, flush=True)
    command = [sys.executable, "-m", "pytest"]
    if selection.full:
        print("Полный прогон всех тестов.", flush=True)
    else:
        print(f"Выбрано файлов тестов: {len(selection.tests)}", flush=True)
        command.extend(["--no-cov", *selection.tests])
        for test in selection.tests:
            print(f"  {test}", flush=True)
    if args.explain:
        return 0
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, check=False)
    print(f"Время проверок: {time.monotonic() - started:.2f} с. Код возврата: {result.returncode}.", flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
