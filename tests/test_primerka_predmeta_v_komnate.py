from __future__ import annotations

import copy
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import zipfile

from PIL import Image
import pytest

from conftest import ROOT


SKILL_DIR = (
    ROOT
    / "plugins"
    / "team-skills"
    / "skills"
    / "primerka-predmeta-v-komnate"
)
SCRIPT = SKILL_DIR / "scripts" / "package_series.py"
REVIEW_FIELDS = ("requirements", "room", "identity", "placement")


class GalleryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def make_brief(
    parent: Path,
    *,
    variants: int = 3,
    source_views: int = 2,
    images_per_variation: int = 2,
) -> tuple[Path, dict]:
    """Создать только синтетические растровые образцы для файловых тестов."""
    source = parent / "исходные данные"
    source.mkdir(parents=True)
    views = [
        {"id": f"v{i + 1:02d}", "label": f"Ракурс {i + 1}", "role": "anchor"}
        for i in range(source_views)
    ]
    shots = []
    for index in range(images_per_variation):
        source_view = views[index % source_views]["id"]
        take = index // source_views + 1
        shots.append(
            {
                "id": f"{source_view}-t{take:02d}",
                "source_view": source_view,
                "take": take,
                "label": f"Ракурс {index % source_views + 1}, дубль {take}",
            }
        )
    data = {
        "schema_version": 1,
        "job_id": "testovaya-seriya",
        "title": "Сравнение вариантов предмета",
        "target": {
            "item": "диван",
            "operation": "replace",
            "quantity": 1,
            "location": "у стены",
        },
        "variation_mode": "auto_concepts",
        "design_goal": "Сопоставимое визуальное сравнение.",
        "constraints": ["Менять только диван."],
        "preserve": ["Сохранить комнату."],
        "counts": {
            "variations": variants,
            "images_per_variation": images_per_variation,
            "expected_images": variants * images_per_variation,
        },
        "variants": [
            {
                "id": f"{i + 1:02d}",
                "name": f"Вариант {i + 1}",
                "description": f"Описание {i + 1}",
            }
            for i in range(variants)
        ],
        "source_views": views,
        "shots": shots,
        "generator": {
            "requested": None,
            "policy": "auto",
            "actual_name": "built-in imagegen",
            "actual_version": None,
            "version_fulfilled": None,
        },
        "limitations": ["Размеры и проходы не подтверждены."],
        "images": [],
    }
    for i, variant in enumerate(data["variants"]):
        for j, shot in enumerate(data["shots"]):
            path = source / f"образец-{i + 1}-{j + 1}.png"
            Image.new(
                "RGB",
                (32 + i, 24 + j),
                (30 + 45 * i, 40 + 50 * j, 110 + i + j),
            ).save(path)
            data["images"].append(
                {
                    "variant": variant["id"],
                    "shot": shot["id"],
                    "path": path.name,
                    "prompt": (
                        f"Синтетический образец {i + 1}, кадр {j + 1} "
                        "для проверки упаковки."
                    ),
                    "origin": "generated",
                    "review": {field: "pass" for field in REVIEW_FIELDS},
                    "notes": "Размещение концептуальное.",
                }
            )
    brief = source / "generation-brief.json"
    write_brief(brief, data)
    return brief, data


def write_brief(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def run_package(brief: Path, out: Path, *, cwd: Path | None = None):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--brief",
            str(brief),
            "--out",
            str(out),
        ],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


def assert_rejected(brief: Path, out: Path) -> None:
    before = snapshot(brief.parent)
    result = run_package(brief, out)
    assert result.returncode != 0, result.stdout
    assert result.stderr.strip(), "Отказ должен объяснять причину."
    assert not out.exists(), "Непригодная серия не должна оставлять выдачу."
    assert snapshot(brief.parent) == before


def test_complete_package_is_portable_and_preserves_original_bytes(
    tmp_path: Path,
) -> None:
    brief, data = make_brief(
        tmp_path, variants=4, source_views=1, images_per_variation=2
    )
    data["images"].reverse()
    write_brief(brief, data)
    before = snapshot(brief.parent)
    out = tmp_path / "готовая серия"
    unrelated_cwd = tmp_path / "другая рабочая папка"
    unrelated_cwd.mkdir()

    result = run_package(brief, out, cwd=unrelated_cwd)

    assert result.returncode == 0, result.stderr
    assert snapshot(brief.parent) == before
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    portable_brief = json.loads(
        (out / "generation-brief.json").read_text(encoding="utf-8")
    )
    validation = json.loads((out / "validation.json").read_text(encoding="utf-8"))
    assert manifest["counts"]["expected_images"] == 8
    assert len(manifest["images"]) == 8
    assert len(portable_brief["matrix"]) == 8
    assert "images" not in portable_brief
    assert str(tmp_path) not in (out / "generation-brief.json").read_text(encoding="utf-8")
    assert validation["expected_images"] == validation["actual_images"] == 8
    assert validation["unique_sha256"] == 8
    assert validation["prompt_files"] == 8

    expected = {
        (item["variant"], item["shot"]): item for item in data["images"]
    }
    for item in manifest["images"]:
        relative = Path(item["path"])
        prompt_relative = Path(item["prompt_path"])
        assert relative.as_posix() == f"images/{item['variant']}-{item['shot']}.png"
        assert prompt_relative.as_posix() == (
            f"prompts/{item['variant']}-{item['shot']}.txt"
        )
        assert not relative.is_absolute() and ".." not in relative.parts
        original = expected[(item["variant"], item["shot"])]
        assert (out / relative).read_bytes() == (
            brief.parent / original["path"]
        ).read_bytes()
        assert (out / prompt_relative).read_text(encoding="utf-8").strip() == (
            original["prompt"]
        )
        with Image.open(out / relative) as image:
            image.load()
            assert [image.width, image.height] == [item["width"], item["height"]]

    gallery = GalleryParser()
    gallery.feed((out / "index.html").read_text(encoding="utf-8"))
    image_sources = [
        attrs["src"] for tag, attrs in gallery.tags if tag == "img"
    ]
    assert len(image_sources) == 8
    for _, attrs in gallery.tags:
        if href := attrs.get("href"):
            url = urlsplit(href)
            if not url.scheme and not url.netloc and url.path:
                assert (out / unquote(url.path)).exists()

    archive_path = out / "testovaya-seriya.zip"
    assert archive_path.is_file()
    expected_members = set(snapshot(out)) - {archive_path.name}
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        assert set(archive.namelist()) == expected_members

    moved = tmp_path / "перенесённая серия"
    shutil.move(str(out), moved)
    assert (moved / "index.html").is_file()
    assert (moved / "testovaya-seriya.zip").is_file()


def test_two_real_source_views_build_six_cell_matrix(tmp_path: Path) -> None:
    brief, _ = make_brief(
        tmp_path, variants=3, source_views=2, images_per_variation=2
    )
    out = tmp_path / "готовая серия"

    result = run_package(brief, out)

    assert result.returncode == 0, result.stderr
    portable_brief = json.loads(
        (out / "generation-brief.json").read_text(encoding="utf-8")
    )
    matrix = portable_brief["matrix"]
    assert len(matrix) == 6
    assert {item["source_view"] for item in matrix} == {"v01", "v02"}
    assert {item["take"] for item in matrix} == {1}
    assert all(item["shot"] == f'{item["source_view"]}-t01' for item in matrix)


def test_metadata_is_escaped_in_gallery(tmp_path: Path) -> None:
    brief, data = make_brief(tmp_path, variants=1, source_views=1)
    payload = '<script>alert("пример")</script><img src=x onerror="alert(1)">'
    data["title"] = payload
    data["variants"][0]["name"] = payload
    data["variants"][0]["description"] = payload
    data["shots"][0]["label"] = payload
    data["images"][0]["prompt"] = payload
    data["images"][0]["notes"] = payload
    write_brief(brief, data)
    out = tmp_path / "выдача"

    result = run_package(brief, out)

    assert result.returncode == 0, result.stderr
    gallery = GalleryParser()
    gallery.feed((out / "index.html").read_text(encoding="utf-8"))
    assert payload in " ".join(gallery.text)
    assert not [tag for tag, _ in gallery.tags if tag == "script"]
    assert not [
        name for _, attrs in gallery.tags for name in attrs if name.startswith("on")
    ]


@pytest.mark.parametrize(
    "failure", ["missing", "duplicate-slot", "unknown-variant", "unknown-shot"]
)
def test_incomplete_or_ambiguous_matrix_is_rejected(
    tmp_path: Path, failure: str
) -> None:
    brief, data = make_brief(tmp_path)
    if failure == "missing":
        data["images"].pop()
    elif failure == "duplicate-slot":
        data["images"][-1]["variant"] = data["images"][0]["variant"]
        data["images"][-1]["shot"] = data["images"][0]["shot"]
    elif failure == "unknown-variant":
        data["images"][-1]["variant"] = "missing-variant"
    else:
        data["images"][-1]["shot"] = "v99-t01"
    write_brief(brief, data)
    assert_rejected(brief, tmp_path / "выдача")


def test_identical_bytes_are_rejected(tmp_path: Path) -> None:
    brief, data = make_brief(tmp_path)
    first = brief.parent / data["images"][0]["path"]
    last = brief.parent / data["images"][-1]["path"]
    last.write_bytes(first.read_bytes())
    assert_rejected(brief, tmp_path / "выдача")


def test_colliding_variant_and_shot_stems_are_rejected(tmp_path: Path) -> None:
    brief, data = make_brief(
        tmp_path, variants=2, source_views=2, images_per_variation=2
    )
    variant_ids = {"01": "a-b", "02": "a"}
    shot_ids = {
        "v01-t01": {"id": "c-t01", "source_view": "c", "take": 1},
        "v02-t01": {"id": "b-c-t01", "source_view": "b-c", "take": 1},
    }
    data["source_views"][0]["id"] = "c"
    data["source_views"][1]["id"] = "b-c"
    for variant in data["variants"]:
        variant["id"] = variant_ids[variant["id"]]
    for shot in data["shots"]:
        replacement = shot_ids[shot["id"]]
        shot.update(replacement)
    for item in data["images"]:
        item["variant"] = variant_ids[item["variant"]]
        item["shot"] = shot_ids[item["shot"]]["id"]
    write_brief(brief, data)

    assert_rejected(brief, tmp_path / "выдача")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("prompt", "Используй /Users/test-user/work/room.png как исходник."),
        ("notes", r"Рабочий файл C:\Users\test-user\room.png"),
        ("title", "Материал из file:///home/test-user/room.png"),
        ("description", "Эталон лежит в ~/projects/room.png"),
    ],
)
def test_local_paths_cannot_enter_portable_output(
    tmp_path: Path, field: str, value: str
) -> None:
    brief, data = make_brief(tmp_path)
    if field in {"prompt", "notes"}:
        data["images"][0][field] = value
    elif field == "description":
        data["variants"][0][field] = value
    else:
        data[field] = value
    write_brief(brief, data)

    assert_rejected(brief, tmp_path / "выдача")


@pytest.mark.parametrize("field", REVIEW_FIELDS)
@pytest.mark.parametrize("value", ["fail", "pending", True, None])
def test_each_review_field_requires_explicit_pass(
    tmp_path: Path, field: str, value
) -> None:
    brief, data = make_brief(tmp_path)
    if value is None:
        data["images"][-1]["review"].pop(field)
    else:
        data["images"][-1]["review"][field] = value
    write_brief(brief, data)
    assert_rejected(brief, tmp_path / "выдача")


@pytest.mark.parametrize("failure", ["corrupt", "truncated", "missing", "extension"])
def test_unreadable_images_are_rejected(tmp_path: Path, failure: str) -> None:
    brief, data = make_brief(tmp_path)
    path = brief.parent / data["images"][-1]["path"]
    if failure == "corrupt":
        path.write_bytes(b"not a raster image")
    elif failure == "truncated":
        original = path.read_bytes()
        path.write_bytes(original[: len(original) // 2])
    elif failure == "missing":
        path.unlink()
    else:
        renamed = path.with_suffix(".txt")
        path.rename(renamed)
        data["images"][-1]["path"] = renamed.name
        write_brief(brief, data)
    assert_rejected(brief, tmp_path / "выдача")


@pytest.mark.parametrize(
    "failure",
    [
        "count-product",
        "variant-count",
        "shot-count",
        "bad-shot-id",
        "repeat-before-cycle",
        "supporting-camera",
        "auto-requested",
        "strict-unconfirmed",
        "missing-actual-name",
        "auto-without-goal",
    ],
)
def test_invalid_order_contract_is_rejected(tmp_path: Path, failure: str) -> None:
    brief, data = make_brief(tmp_path)
    if failure == "count-product":
        data["counts"]["expected_images"] += 1
    elif failure == "variant-count":
        data["counts"]["variations"] += 1
        data["counts"]["expected_images"] = (
            data["counts"]["variations"]
            * data["counts"]["images_per_variation"]
        )
    elif failure == "shot-count":
        data["shots"].pop()
    elif failure == "bad-shot-id":
        data["shots"][0]["id"] = "invented-view"
        data["images"][0]["shot"] = "invented-view"
    elif failure == "repeat-before-cycle":
        old_shot = data["shots"][1]["id"]
        data["shots"][1].update(
            {"id": "v01-t02", "source_view": "v01", "take": 2}
        )
        for item in data["images"]:
            if item["shot"] == old_shot:
                item["shot"] = "v01-t02"
    elif failure == "supporting-camera":
        data["source_views"][0]["role"] = "supporting"
    elif failure == "auto-requested":
        data["generator"]["requested"] = "Images X"
    elif failure == "strict-unconfirmed":
        data["generator"] = {
            "requested": "Images X",
            "policy": "strict",
            "actual_name": "built-in imagegen",
            "actual_version": None,
            "version_fulfilled": False,
        }
    elif failure == "missing-actual-name":
        data["generator"]["actual_name"] = None
    else:
        data["design_goal"] = None
    write_brief(brief, data)
    assert_rejected(brief, tmp_path / "выдача")


def test_preferred_generator_mismatch_is_recorded_and_allowed(tmp_path: Path) -> None:
    brief, data = make_brief(tmp_path)
    data["generator"] = {
        "requested": "Images X",
        "policy": "preferred",
        "actual_name": "built-in imagegen",
        "actual_version": None,
        "version_fulfilled": False,
    }
    write_brief(brief, data)
    out = tmp_path / "выдача"

    result = run_package(brief, out)

    assert result.returncode == 0, result.stderr
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["generator"] == data["generator"]


@pytest.mark.parametrize("kind", ["directory", "empty-directory", "file"])
def test_existing_output_is_never_overwritten(tmp_path: Path, kind: str) -> None:
    brief, _ = make_brief(tmp_path)
    out = tmp_path / "существующая выдача"
    if kind != "file":
        out.mkdir()
        if kind == "directory":
            (out / "не трогать.txt").write_bytes(b"keep")
        before = snapshot(out)
    else:
        out.write_bytes(b"keep")
        before = out.read_bytes()

    result = run_package(brief, out)

    assert result.returncode != 0
    assert (snapshot(out) if kind != "file" else out.read_bytes()) == before


def test_documented_generation_brief_runs_without_schema_changes(
    tmp_path: Path,
) -> None:
    example = json.loads(
        (SKILL_DIR / "assets" / "generation-brief.example.json").read_text(
            encoding="utf-8"
        )
    )
    source = tmp_path / "пример"
    source.mkdir()
    for number, item in enumerate(example["images"]):
        path = source / item["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (33 + number, 29), (10, 20, 30 + number)).save(path)
    brief = source / "generation-brief.json"
    write_brief(brief, copy.deepcopy(example))
    out = tmp_path / "result"

    result = run_package(brief, out)

    assert result.returncode == 0, result.stderr
    assert len(list((out / "images").glob("*.png"))) == 4
    assert len(list((out / "prompts").glob("*.txt"))) == 4


def test_help_and_argument_errors_are_localized() -> None:
    help_result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    error_result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert help_result.returncode == 0
    assert "Использование:" in help_result.stdout
    assert "--brief" in help_result.stdout
    assert error_result.returncode == 2
    assert "Ошибка параметров:" in error_result.stderr
