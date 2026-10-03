"""Проверять приватные пути внутри реальных метаданных без изменения изображений."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import zipfile

from PIL import Image, ImageCms, PngImagePlugin
import pytest

from test_primerka_predmeta_v_komnate import (
    assert_rejected,
    make_brief,
    run_package,
    snapshot,
    write_brief,
)


PRIVATE_PATH = "/home/test-user/private/source-room.png"
XMP_PREFIX = b"http://ns.adobe.com/xap/1.0/\x00"
FORMATS = (("JPEG", ".jpg"), ("WEBP", ".webp"))


def xmp_packet(value: str) -> bytes:
    return (
        '<x:xmpmeta xmlns:x="adobe:ns:meta/" '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:RDF><rdf:Description xmlns:preview="https://example.com/preview/" '
        f'preview:source="{value}" /></rdf:RDF></x:xmpmeta>'
    ).encode("utf-8")


def add_jpeg_xmp(path: Path, value: bytes) -> None:
    """Добавить стандартный APP1 XMP; совместимо с Pillow >=10.0."""
    payload = XMP_PREFIX + value
    segment = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
    raw = path.read_bytes()
    assert raw.startswith(b"\xff\xd8")
    path.write_bytes(raw[:2] + segment + raw[2:])


def image_fixture(tmp_path: Path, suffix: str):
    brief, data = make_brief(
        tmp_path, variants=1, source_views=1, images_per_variation=1
    )
    source = (brief.parent / data["images"][0]["path"]).with_suffix(suffix)
    data["images"][0]["path"] = source.name
    write_brief(brief, data)
    picture = Image.new("RGB", (32, 24), (30, 80, 120))
    return brief, data, source, picture


@pytest.mark.parametrize(
    "carrier",
    (
        "text-value",
        "text-key",
        "itxt-value",
        "itxt-key",
        "itxt-translated-key",
        "duplicate-compressed-text",
    ),
)
def test_png_private_metadata_is_rejected(tmp_path: Path, carrier: str) -> None:
    brief, _, source, picture = image_fixture(tmp_path, ".png")
    info = PngImagePlugin.PngInfo()
    if carrier == "text-value":
        info.add_text("SourceFile", PRIVATE_PATH)
    elif carrier == "text-key":
        info.add_text(PRIVATE_PATH, "Public preview")
    elif carrier == "itxt-value":
        info.add_itxt("SourceFile", PRIVATE_PATH)
    elif carrier == "itxt-key":
        info.add_itxt(PRIVATE_PATH, "Public preview")
    elif carrier == "itxt-translated-key":
        info.add_itxt("SourceFile", "Public preview", tkey=PRIVATE_PATH)
    else:
        # Pillow итоговым dict скрывает первый chunk; в файле остаются оба.
        info.add_text("SourceFile", PRIVATE_PATH, zip=True)
        info.add_text("SourceFile", "Public preview", zip=True)
    picture.save(source, format="PNG", pnginfo=info)

    assert_rejected(brief, tmp_path / "выдача")


@pytest.mark.parametrize(("fmt", "suffix"), FORMATS)
@pytest.mark.parametrize("carrier", ("exif-description", "exif-xpcomment", "exif-usercomment", "xmp"))
def test_jpeg_and_webp_private_metadata_is_rejected(
    tmp_path: Path, fmt: str, suffix: str, carrier: str
) -> None:
    brief, _, source, picture = image_fixture(tmp_path, suffix)
    options = {}
    if carrier == "xmp":
        if fmt == "WEBP":
            options["xmp"] = xmp_packet(PRIVATE_PATH)
    else:
        exif = Image.Exif()
        if carrier == "exif-description":
            exif[270] = PRIVATE_PATH
        elif carrier == "exif-xpcomment":
            exif[40092] = tuple((PRIVATE_PATH + "\x00").encode("utf-16-le"))
        else:
            # EXIF UserComment лежит в Exif IFD и имеет собственную кодировку.
            exif[34665] = {
                37510: b"UNICODE\x00" + (PRIVATE_PATH + "\x00").encode("utf-16-be")
            }
        options["exif"] = exif
    picture.save(source, format=fmt, **options)
    if fmt == "JPEG" and carrier == "xmp":
        add_jpeg_xmp(source, xmp_packet(PRIVATE_PATH))

    assert_rejected(brief, tmp_path / "выдача")


@pytest.mark.parametrize(("fmt", "suffix"), (("PNG", ".png"), *FORMATS))
def test_benign_metadata_is_accepted_without_reencoding(
    tmp_path: Path, fmt: str, suffix: str
) -> None:
    brief, data, source, picture = image_fixture(tmp_path, suffix)
    exif = Image.Exif()
    exif[270] = "Synthetic public preview"
    exif[274] = 1
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    xmp = xmp_packet("https://example.com/room.png")
    options = {"exif": exif, "icc_profile": icc}
    if fmt == "PNG":
        info = PngImagePlugin.PngInfo()
        info.add_text("Description", "Synthetic public preview")
        info.add_itxt("Title", "Синтетический образец", lang="ru", tkey="Заголовок")
        info.add_itxt("XML:com.adobe.xmp", xmp.decode("utf-8"))
        options["pnginfo"] = info
    elif fmt == "WEBP":
        options["xmp"] = xmp
    picture.save(source, format=fmt, **options)
    if fmt == "JPEG":
        add_jpeg_xmp(source, xmp)
    before = snapshot(brief.parent)
    expected = source.read_bytes()
    out = tmp_path / "выдача"

    result = run_package(brief, out)

    assert result.returncode == 0, result.stderr
    assert snapshot(brief.parent) == before
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    relative = manifest["images"][0]["path"]
    assert (out / relative).read_bytes() == expected
    with zipfile.ZipFile(out / (data["job_id"] + ".zip")) as archive:
        assert archive.read(relative) == expected


@pytest.mark.parametrize(
    "value",
    (b"/home/user/private/room\x00", b"C:\\Users\\test-user\\private\\room.png\x00"),
)
def test_jpeg_comment_nul_cannot_hide_private_paths(tmp_path: Path, value: bytes) -> None:
    brief, _, source, picture = image_fixture(tmp_path, ".jpg")
    picture.save(source, format="JPEG")
    raw = source.read_bytes()
    source.write_bytes(raw[:2] + b"\xff\xfe" + struct.pack(">H", len(value) + 2) + value + raw[2:])

    assert_rejected(brief, tmp_path / "выдача")
    result = run_package(brief, tmp_path / "выдача")
    assert "метадан" in result.stderr.lower()
    assert "Traceback" not in result.stderr


def test_benign_jpeg_comment_nul_is_preserved(tmp_path: Path) -> None:
    brief, data, source, picture = image_fixture(tmp_path, ".jpg")
    picture.save(source, format="JPEG")
    value = b"Synthetic public preview\x00"
    raw = source.read_bytes()
    source.write_bytes(raw[:2] + b"\xff\xfe" + struct.pack(">H", len(value) + 2) + value + raw[2:])
    before = snapshot(brief.parent)
    expected = source.read_bytes()
    out = tmp_path / "выдача"

    result = run_package(brief, out)

    assert result.returncode == 0, result.stderr
    assert snapshot(brief.parent) == before
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    relative = manifest["images"][0]["path"]
    assert (out / relative).read_bytes() == expected
    with zipfile.ZipFile(out / (data["job_id"] + ".zip")) as archive:
        assert archive.read(relative) == expected
