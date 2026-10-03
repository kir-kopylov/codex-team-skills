#!/usr/bin/env python3
"""Проверить и упаковать локальную серию; изображения не изменяются."""

from __future__ import annotations

import argparse
import copy
import ctypes
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import zipfile


ID = re.compile(r"[a-z0-9][a-z0-9_-]*\Z")
REVIEW_FIELDS = {"requirements", "room", "identity", "placement"}
FORMATS = {"PNG": {".png"}, "JPEG": {".jpg", ".jpeg"}, "WEBP": {".webp"}}
EXTENSIONS = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
VARIATION_MODES = {"auto_concepts", "provided_concepts", "product_references"}
GENERATOR_POLICIES = {"auto", "preferred", "strict"}
SOURCE_ROLES = {"anchor", "supporting"}
REMOTE_HTTP_URL = re.compile(
    r"(?i)\bhttps?://(?:[^\s`\"'<>|)}\[\]/?#]*@)?"
    r"(?:\[[^\s`\"'<>|)}\[\]/?#]+\]|[^\s`\"'<>|)}\[\]/?#]+)"
    r"[^\s`\"'<>|)}\[\]]*"
)
REMOTE_DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z", re.I)
LOCAL_PATH_PATTERNS = (
    (
        "абсолютный или сетевой путь Unix",
        re.compile(r"(?<![\w/])/+[^/\s`\"'<>|]+(?:/[^/\s`\"'<>|]+)*"),
    ),
    (
        "локальный путь Unix",
        re.compile(
            r"(?<![A-Za-z0-9:/])/(?:Users|home|root|private|tmp|var|Volumes|mnt|opt|etc)"
            r"(?:/[^\s`\"'<>|]+)*"
        ),
    ),
    (
        "локальный путь Windows",
        re.compile(r"(?i)(?<![A-Za-z0-9])[A-Z]:[\\/][^\s`\"'<>|]+"),
    ),
    ("сетевой путь Windows", re.compile(r"\\\\[^\\\s]+\\[^\\\s]+")),
    (
        "корневой путь Windows",
        re.compile(r"(?<![\w\\])\\(?!\\)[^\\\s`\"'<>|]+(?:\\[^\\\s`\"'<>|]+)*"),
    ),
    ("домашний путь", re.compile(r"(?<![\w])~[\\/][^\s`\"'<>|]+")),
    ("локальный file URI", re.compile(r"(?i)\bfile://[^\s`\"'<>|]+")),
)
TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "gallery-template.html"
REVIEW_NOTICE = (
    "Статусы визуальной проверки переданы исполнителем. Сборщик проверяет "
    "наличие отметок pass, но не оценивает содержание изображения. "
    "Открываемость и разные хэши не доказывают сохранность комнаты, "
    "соответствие предмета или качество размещения."
)


class SeriesError(Exception):
    """Ожидаемая ошибка исходных данных или упаковки."""


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require_fields(
    value: object,
    *,
    name: str,
    required: set[str],
    optional: set[str] | None = None,
) -> dict:
    if not isinstance(value, dict):
        raise SeriesError(f"{name} должен содержать объект JSON.")
    optional = optional or set()
    missing = required - set(value)
    unknown = set(value) - required - optional
    if missing:
        raise SeriesError(f"{name}: отсутствуют поля: {', '.join(sorted(missing))}.")
    if unknown:
        raise SeriesError(f"{name}: неизвестные поля: {', '.join(sorted(unknown))}.")
    return value


def nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SeriesError(f"{name} должен быть непустой строкой.")
    return value


def string_list(value: object, name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise SeriesError(f"{name} должен быть массивом непустых строк.")
    return value


def safe_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise SeriesError(f"{name} содержит недопустимый id: {value!r}.")
    return value


def reject_local_paths(value: object, name: str) -> None:
    """Не дать приватным рабочим путям попасть в переносимый пакет."""
    if isinstance(value, dict):
        for key, child in value.items():
            reject_local_paths(child, f"{name}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_local_paths(child, f"{name}[{index}]")
    elif isinstance(value, str):
        def mask_valid_remote_url(match: re.Match[str]) -> str:
            candidate = match.group(0)
            if "\\" in candidate:
                return candidate
            try:
                parsed = urlsplit(candidate)
                hostname = parsed.hostname
                _ = parsed.port
                if not hostname:
                    return candidate
                if ":" in hostname:
                    from ipaddress import IPv6Address

                    IPv6Address(hostname)
                    authority = parsed.netloc.rsplit("@", 1)[-1]
                    if not re.fullmatch(r"\[[^\[\]]+\](?::[0-9]*)?", authority):
                        return candidate
                else:
                    dns_name = hostname.encode("idna").decode("ascii")
                    if dns_name.endswith("."):
                        dns_name = dns_name[:-1]
                    if len(dns_name) > 253 or any(
                        not REMOTE_DNS_LABEL.fullmatch(label)
                        for label in dns_name.split(".")
                    ):
                        return candidate
            except (ValueError, UnicodeError):
                return candidate
            if parsed.scheme.lower() in {"http", "https"} and parsed.netloc and hostname:
                for component, is_fragment in ((parsed.query, False), (parsed.fragment, True)):
                    # Проверяем и закодированные, и вложенно закодированные значения.
                    decoded = component
                    while True:
                        expanded = unquote(decoded)
                        if expanded == decoded:
                            break
                        decoded = expanded
                    if is_fragment and decoded.startswith("/") and not decoded.startswith("//"):
                        # Прямой маршрут веб-приложения #/catalog допустим;
                        # признаки локального расположения всё равно запрещены.
                        route = urlsplit(decoded)
                        reject_local_paths(route.query, f"{name}: параметры маршрута")
                        reject_local_paths(route.fragment, f"{name}: фрагмент маршрута")
                        for label, pattern in LOCAL_PATH_PATTERNS[1:]:
                            if pattern.search(route.path):
                                raise SeriesError(
                                    f"{name} содержит {label} в параметрах ссылки; "
                                    "удалите его до упаковки."
                                )
                    else:
                        reject_local_paths(decoded, f"{name}: параметры ссылки")
                return " " * len(candidate)
            return candidate

        scan_value = REMOTE_HTTP_URL.sub(mask_valid_remote_url, value)
        for label, pattern in LOCAL_PATH_PATTERNS:
            if pattern.search(scan_value):
                raise SeriesError(f"{name} содержит {label}; удалите его до упаковки.")


def read_brief(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SeriesError(f"Не удалось прочитать generation-brief: {exc}") from exc

    required = {
        "schema_version",
        "job_id",
        "title",
        "target",
        "variation_mode",
        "design_goal",
        "constraints",
        "preserve",
        "counts",
        "variants",
        "source_views",
        "shots",
        "generator",
        "limitations",
        "images",
    }
    data = require_fields(data, name="generation-brief", required=required)
    if data["schema_version"] != 1:
        raise SeriesError("Поддерживается только schema_version=1.")
    safe_id(data["job_id"], "job_id")
    nonempty_string(data["title"], "title")

    target = require_fields(
        data["target"],
        name="target",
        required={"item", "operation", "quantity", "location"},
    )
    nonempty_string(target["item"], "target.item")
    if target["operation"] not in {"add", "replace"}:
        raise SeriesError("target.operation должен быть add или replace.")
    if (
        not isinstance(target["quantity"], int)
        or isinstance(target["quantity"], bool)
        or target["quantity"] < 1
    ):
        raise SeriesError("target.quantity должен быть положительным целым числом.")
    if not isinstance(target["location"], str):
        raise SeriesError("target.location должен быть строкой.")

    if data["variation_mode"] not in VARIATION_MODES:
        raise SeriesError("variation_mode содержит неизвестный режим.")
    if data["design_goal"] is not None and not isinstance(data["design_goal"], str):
        raise SeriesError("design_goal должен быть строкой или null.")
    if data["variation_mode"] == "auto_concepts" and (
        not isinstance(data["design_goal"], str) or not data["design_goal"].strip()
    ):
        raise SeriesError("Для auto_concepts нужен непустой design_goal.")
    string_list(data["constraints"], "constraints")
    string_list(data["preserve"], "preserve")
    string_list(data["limitations"], "limitations")

    counts = require_fields(
        data["counts"],
        name="counts",
        required={"variations", "images_per_variation", "expected_images"},
    )
    for field in ("variations", "images_per_variation", "expected_images"):
        value = counts[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise SeriesError(f"counts.{field} должен быть положительным целым числом.")
    if counts["expected_images"] != counts["variations"] * counts["images_per_variation"]:
        raise SeriesError("counts.expected_images не равен variations × images_per_variation.")

    variants = data["variants"]
    if not isinstance(variants, list) or not variants:
        raise SeriesError("variants должен быть непустым массивом.")
    variant_ids: set[str] = set()
    for entry in variants:
        entry = require_fields(
            entry,
            name="variants entry",
            required={"id", "name", "description"},
        )
        key = safe_id(entry["id"], "variants")
        if key in variant_ids:
            raise SeriesError(f"Повторный id варианта: {key}.")
        variant_ids.add(key)
        nonempty_string(entry["name"], f"variants/{key}/name")
        if not isinstance(entry["description"], str):
            raise SeriesError(f"variants/{key}/description должен быть строкой.")
    if len(variants) != counts["variations"]:
        raise SeriesError("Число variants не совпадает с counts.variations.")

    source_views = data["source_views"]
    if not isinstance(source_views, list) or not source_views:
        raise SeriesError("source_views должен быть непустым массивом.")
    source_roles: dict[str, str] = {}
    for entry in source_views:
        entry = require_fields(
            entry,
            name="source_views entry",
            required={"id", "label", "role"},
        )
        key = safe_id(entry["id"], "source_views")
        if key in source_roles:
            raise SeriesError(f"Повторный id исходного вида: {key}.")
        nonempty_string(entry["label"], f"source_views/{key}/label")
        if entry["role"] not in SOURCE_ROLES:
            raise SeriesError(f"source_views/{key}/role должен быть anchor или supporting.")
        source_roles[key] = entry["role"]
    if "anchor" not in source_roles.values():
        raise SeriesError("Нужен хотя бы один source_view с role=anchor.")

    shots = data["shots"]
    if not isinstance(shots, list) or not shots:
        raise SeriesError("shots должен быть непустым массивом.")
    shot_ids: set[str] = set()
    shot_pairs: set[tuple[str, int]] = set()
    shot_sequence: list[tuple[str, int]] = []
    for entry in shots:
        entry = require_fields(
            entry,
            name="shots entry",
            required={"id", "source_view", "take", "label"},
        )
        key = safe_id(entry["id"], "shots")
        source_view = safe_id(entry["source_view"], f"shots/{key}/source_view")
        take = entry["take"]
        if source_view not in source_roles:
            raise SeriesError(f"shots/{key}: неизвестный source_view {source_view}.")
        if source_roles[source_view] != "anchor":
            raise SeriesError(f"shots/{key}: supporting-вид нельзя использовать как камеру.")
        if not isinstance(take, int) or isinstance(take, bool) or take < 1:
            raise SeriesError(f"shots/{key}/take должен быть положительным целым числом.")
        if key != f"{source_view}-t{take:02d}":
            raise SeriesError(
                f"shots/{key}: id должен иметь вид {source_view}-t{take:02d}."
            )
        if key in shot_ids or (source_view, take) in shot_pairs:
            raise SeriesError(f"Повторный кадр: {key}.")
        shot_ids.add(key)
        shot_pairs.add((source_view, take))
        shot_sequence.append((source_view, take))
        nonempty_string(entry["label"], f"shots/{key}/label")
    if len(shots) != counts["images_per_variation"]:
        raise SeriesError("Число shots не совпадает с counts.images_per_variation.")
    anchor_ids = [entry["id"] for entry in source_views if entry["role"] == "anchor"]
    expected_sequence = [
        (anchor_ids[index % len(anchor_ids)], index // len(anchor_ids) + 1)
        for index in range(counts["images_per_variation"])
    ]
    if shot_sequence != expected_sequence:
        raise SeriesError(
            "shots должны использовать все anchor-виды по порядку до нового дубля."
        )

    output_stems: dict[str, tuple[str, str]] = {}
    for variant in variants:
        for shot in shots:
            slot = (variant["id"], shot["id"])
            stem = f"{slot[0]}-{slot[1]}"
            if stem in output_stems:
                previous = output_stems[stem]
                raise SeriesError(
                    f"Ячейки {previous[0]}/{previous[1]} и {slot[0]}/{slot[1]} "
                    "дают одинаковое имя выходного файла; измените id."
                )
            output_stems[stem] = slot

    generator = require_fields(
        data["generator"],
        name="generator",
        required={
            "requested",
            "policy",
            "actual_name",
            "actual_version",
            "version_fulfilled",
        },
    )
    for field in ("requested", "actual_version"):
        if generator[field] is not None and (
            not isinstance(generator[field], str) or not generator[field].strip()
        ):
            raise SeriesError(f"generator.{field} должен быть непустой строкой или null.")
    nonempty_string(generator["actual_name"], "generator.actual_name")
    if generator["policy"] not in GENERATOR_POLICIES:
        raise SeriesError("generator.policy содержит неизвестное значение.")
    if generator["policy"] == "auto" and generator["requested"] is not None:
        raise SeriesError("При generator.policy=auto поле requested должно быть null.")
    if generator["policy"] in {"preferred", "strict"} and generator["requested"] is None:
        raise SeriesError("Для preferred или strict нужно поле generator.requested.")
    fulfilled = generator["version_fulfilled"]
    if fulfilled is not None and not isinstance(fulfilled, bool):
        raise SeriesError("generator.version_fulfilled должен быть true, false или null.")
    if fulfilled is True and generator["actual_name"] is None:
        raise SeriesError("Подтверждённый генератор требует generator.actual_name.")
    if generator["policy"] == "strict" and fulfilled is not True:
        raise SeriesError("Строгий запрос генератора не подтверждён; серия не упакована.")

    if not isinstance(data["images"], list):
        raise SeriesError("images должен быть массивом.")
    return data



def reject_image_metadata(picture: object, source: Path) -> None:
    """Проверить метаданные до копирования, не перекодируя растровые данные."""
    from io import BytesIO
    import struct
    import xml.etree.ElementTree as ET
    import zlib
    from PIL import Image, ImageCms, PngImagePlugin

    def scan(value: object) -> None:
        if isinstance(value, str):
            reject_local_paths(value, "Метаданные изображения")
        elif isinstance(value, dict):
            for key, child in value.items():
                scan(key)
                scan(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                scan(child)
        elif isinstance(value, bytes) and value:
            decode_text(value)

    def decode_text(payload: bytes) -> None:
        if payload.startswith(b"ASCII\x00\x00\x00"):
            scan(payload[8:].rstrip(b"\x00").decode("ascii"))
            return
        if payload.startswith(b"UNICODE\x00"):
            payload = payload[8:]
            encodings = ("utf-16",) if payload.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-16-be", "utf-16-le")
        elif payload.startswith(b"JIS\x00\x00\x00\x00\x00"):
            scan(payload[8:].rstrip(b"\x00").decode("shift_jis"))
            return
        elif payload.startswith((b"\xff\xfe", b"\xfe\xff")):
            encodings = ("utf-16",)
        else:
            # NUL не должен скрывать обычный ASCII/UTF-8 путь за догадкой UTF-16.
            scan(payload.decode("latin-1").replace("\x00", ""))
            payload = payload.rstrip(b"\x00")
            encodings = ("utf-16-be", "utf-16-le") if b"\x00" in payload else ("utf-8", "latin-1")
        decoded = []
        for encoding in encodings:
            try:
                text = payload.decode(encoding).rstrip("\x00")
            except UnicodeError:
                continue
            if all(character.isprintable() or character in "\n\r\t" for character in text):
                decoded.append(text)
        if not decoded:
            raise ValueError("неразбираемые текстовые метаданные; удалите их до упаковки")
        for text in decoded:
            scan(text)

    def decompress_png(payload: bytes) -> bytes:
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(payload, PngImagePlugin.MAX_TEXT_CHUNK + 1)
        if len(decoded) > PngImagePlugin.MAX_TEXT_CHUNK or decoder.unconsumed_tail or decoder.unused_data or not decoder.eof:
            raise ValueError("сжатые метаданные PNG не прошли ограниченную проверку")
        return decoded

    def check_xmp(payload: bytes) -> None:
        def check_name(name: object) -> None:
            if isinstance(name, str):
                parts = name[1:].split("}", 1) if name.startswith("{") else [name]
                scan(parts)

        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        root = ET.fromstring(payload, parser=parser)
        for _, (_, namespace) in ET.iterparse(BytesIO(payload), events=("start-ns",)):
            scan(namespace)
        for element in root.iter():
            check_name(element.tag)
            scan(element.text)
            scan(element.tail)
            for name, value in element.attrib.items():
                check_name(name)
                scan(value)

    def check_exif(payload: bytes) -> None:
        tiff = payload[6:] if payload.startswith(b"Exif\x00\x00") else payload
        if len(tiff) < 8 or tiff[:4] not in (b"II*\x00", b"MM\x00*"):
            raise ValueError("неразбираемые EXIF-метаданные; удалите их до упаковки")
        exif = Image.Exif()
        exif.load(payload)

        def check_ifd(values: dict) -> None:
            for tag, value in values.items():
                if tag in {513, 514}:
                    raise ValueError("встроенная EXIF-миниатюра не поддерживается; удалите её до упаковки")
                if tag in range(40091, 40096):
                    scan(bytes(value).decode("utf-16-le").rstrip("\x00"))
                elif tag == 37500 and value:
                    raise ValueError("неподдерживаемые непрозрачные MakerNote; удалите их до упаковки")
                else:
                    scan(value)

        check_ifd(dict(exif))
        # Exif/GPS/Interop и таблица миниатюры не входят целиком в dict(IFD0).
        nested = exif.get_ifd(34665) if 34665 in exif else {}
        check_ifd(nested)
        if 34853 in exif:
            check_ifd(exif.get_ifd(34853))
        if 40965 in nested:
            check_ifd(exif.get_ifd(40965))
        check_ifd(exif.get_ifd(-1))

    def scan_explicit_binary_paths(payload: bytes) -> None:
        # Случайный slash в бинарном профиле не является локальным путём.
        explicit = (LOCAL_PATH_PATTERNS[1], LOCAL_PATH_PATTERNS[2], LOCAL_PATH_PATTERNS[3], LOCAL_PATH_PATTERNS[5], LOCAL_PATH_PATTERNS[6])
        for encoding in ("latin-1", "utf-16-be", "utf-16-le"):
            text = payload.decode(encoding, errors="ignore").replace("\x00", "")
            for label, pattern in explicit:
                if pattern.search(text):
                    raise ValueError(f"метаданные содержат {label}; удалите их до упаковки")

    def check_icc(payload: bytes) -> None:
        try:
            profile = ImageCms.ImageCmsProfile(BytesIO(payload)).profile
        except Exception as exc:
            raise ValueError("неразбираемый ICC-профиль; удалите его до упаковки") from exc
        for attribute in dir(profile):
            if not attribute.startswith("_"):
                value = getattr(profile, attribute)
                if isinstance(value, (str, list, tuple)):
                    scan(value)
        scan_explicit_binary_paths(payload)

    try:
        if picture.format == "PNG":
            raw = source.read_bytes()
            position = 8
            structural = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"sBIT", b"pHYs", b"bKGD", b"hIST", b"tIME"}
            while position < len(raw):
                length = struct.unpack_from(">I", raw, position)[0]
                kind = raw[position + 4:position + 8]
                end = position + 12 + length
                if end > len(raw):
                    raise ValueError("неполная запись метаданных PNG")
                payload = raw[position + 8:position + 8 + length]
                position = end
                if kind in {b"tEXt", b"zTXt", b"iTXt"}:
                    key, rest = payload.split(b"\x00", 1)
                    scan(key.decode("latin-1"))
                    if kind == b"tEXt":
                        text = rest.decode("latin-1")
                    elif kind == b"zTXt":
                        if rest[0] != 0:
                            raise ValueError("неподдерживаемое сжатие PNG-текста")
                        text = decompress_png(rest[1:]).decode("latin-1")
                    else:
                        flag, method = rest[:2]
                        language, translated, rest = rest[2:].split(b"\x00", 2)
                        scan(language.decode("ascii"))
                        scan(translated.decode("utf-8"))
                        if flag not in (0, 1) or method != 0:
                            raise ValueError("неподдерживаемое сжатие PNG-текста")
                        text = (decompress_png(rest) if flag else rest).decode("utf-8")
                    if key == b"XML:com.adobe.xmp":
                        check_xmp(text.encode("utf-8"))
                    else:
                        scan(text)
                elif kind == b"eXIf":
                    check_exif(payload)
                elif kind == b"iCCP":
                    name, rest = payload.split(b"\x00", 1)
                    scan(name.decode("latin-1"))
                    if rest[0] != 0:
                        raise ValueError("неподдерживаемое сжатие ICC-профиля")
                    check_icc(decompress_png(rest[1:]))
                elif kind not in structural:
                    raise ValueError("неподдерживаемая запись метаданных PNG; удалите её до упаковки")
        elif picture.format == "JPEG":
            icc_parts = False
            for marker, payload in picture.applist:
                if marker == "COM":
                    decode_text(payload)
                elif marker == "APP1" and payload.startswith(b"Exif\x00\x00"):
                    check_exif(payload)
                elif marker == "APP1" and payload.startswith(b"http://ns.adobe.com/xap/1.0/\x00"):
                    check_xmp(payload.split(b"\x00", 1)[1])
                elif marker == "APP2" and payload.startswith(b"ICC_PROFILE\x00"):
                    icc_parts = True
                    scan_explicit_binary_paths(payload[14:])
                elif marker == "APP0" and payload.startswith(b"JFIF\x00"):
                    continue
                elif marker == "APP14" and payload.startswith(b"Adobe"):
                    continue
                else:
                    raise ValueError("неподдерживаемая запись метаданных JPEG; удалите её до упаковки")
            if icc_parts:
                check_icc(picture.info.get("icc_profile") or b"")
        elif picture.format == "WEBP":
            raw = source.read_bytes()
            position = 12
            while position < len(raw):
                kind = raw[position:position + 4]
                length = struct.unpack_from("<I", raw, position + 4)[0]
                payload = raw[position + 8:position + 8 + length]
                position += 8 + length + (length % 2)
                if position > len(raw):
                    raise ValueError("неполная запись метаданных WebP")
                if kind == b"EXIF":
                    check_exif(payload)
                elif kind == b"XMP ":
                    check_xmp(payload)
                elif kind == b"ICCP":
                    check_icc(payload)
                elif kind not in {b"VP8 ", b"VP8L", b"VP8X", b"ALPH"}:
                    raise ValueError("неподдерживаемая запись метаданных WebP; удалите её до упаковки")
        # Служебные числовые поля безопасны; неизвестные текстовые поля не пропускаем.
        for key, value in picture.info.items():
            if key not in {"exif", "xmp", "icc_profile", "transparency", "XML:com.adobe.xmp"}:
                scan(key)
                scan(value)
    except SeriesError as exc:
        raise ValueError(str(exc)) from exc
    except (UnicodeError, struct.error, zlib.error, ET.ParseError, IndexError, KeyError, TypeError) as exc:
        raise ValueError("неразбираемые метаданные; удалите их до упаковки") from exc


def validate_images(data: dict, base: Path) -> dict:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SeriesError(
            "Для проверки изображений нужен Pillow в среде проекта."
        ) from exc

    expected = {
        (variant["id"], shot["id"])
        for variant in data["variants"]
        for shot in data["shots"]
    }
    seen: set[tuple[str, str]] = set()
    accepted: dict[tuple[str, str], dict] = {}
    hashes: dict[str, str] = {}
    errors: list[str] = []
    required = {"variant", "shot", "path", "prompt", "origin", "review"}

    for position, item in enumerate(data["images"], 1):
        label = f"Изображение {position}"
        if not isinstance(item, dict):
            errors.append(f"{label}: требуется объект.")
            continue
        variant, shot = item.get("variant"), item.get("shot")
        if not isinstance(variant, str) or not isinstance(shot, str):
            errors.append(f"{label}: variant и shot должны быть строками.")
            continue
        slot = (variant, shot)
        label = f"{variant}/{shot}"
        if slot not in expected:
            errors.append(f"{label}: неизвестная ячейка варианта и кадра.")
            continue
        if slot in seen:
            errors.append(f"{label}: повторная запись ячейки.")
            continue
        seen.add(slot)
        if not required <= set(item) or set(item) - required - {"notes"}:
            errors.append(f"{label}: отсутствуют обязательные поля или есть неизвестные.")
            continue
        if any(not isinstance(item[field], str) for field in ("path", "prompt", "origin")):
            errors.append(f"{label}: path, prompt и origin должны быть строками.")
            continue
        if not item["path"].strip() or not item["prompt"].strip():
            errors.append(f"{label}: path и prompt не могут быть пустыми.")
            continue
        if "notes" in item and not isinstance(item["notes"], str):
            errors.append(f"{label}: notes должно быть строкой.")
            continue
        if item["origin"] != "generated":
            errors.append(f"{label}: принимается только origin=generated.")
            continue
        review = item["review"]
        if not isinstance(review, dict) or set(review) != REVIEW_FIELDS or any(
            review[field] != "pass" for field in REVIEW_FIELDS
        ):
            errors.append(f"{label}: нужны четыре отметки визуальной проверки pass.")
            continue

        source = Path(item["path"])
        if not source.is_absolute():
            if source == Path("..") or ".." in source.parts:
                errors.append(f"{label}: относительный path не может выходить из папки brief.")
                continue
            source = base / source
        try:
            if source.is_symlink():
                raise ValueError("символические ссылки не поддерживаются")
            if not source.is_file():
                raise ValueError("файл не найден или не является обычным файлом")
            checksum = digest(source)
            with Image.open(source) as picture:
                fmt = picture.format
                if fmt not in FORMATS or source.suffix.lower() not in FORMATS[fmt]:
                    raise ValueError("допустимы PNG/JPEG/WebP с соответствующим расширением")
                if getattr(picture, "n_frames", 1) != 1 or getattr(
                    picture, "is_animated", False
                ):
                    raise ValueError("анимация и несколько кадров не поддерживаются")
                width, height = picture.size
                picture.verify()
            with Image.open(source) as picture:
                picture.load()
                reject_image_metadata(picture, source)
            if digest(source) != checksum:
                raise ValueError("файл изменился во время проверки")
            if checksum in hashes:
                raise ValueError(f"точный дубликат файла для {hashes[checksum]}")
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
            errors.append(f"{label}: изображение не принято — {exc}.")
            continue
        hashes[checksum] = label
        accepted[slot] = {
            "item": item,
            "source": source,
            "sha256": checksum,
            "extension": EXTENSIONS[fmt],
            "format": fmt,
            "width": width,
            "height": height,
        }

    missing = expected - accepted.keys()
    if missing:
        errors.append(
            "Недостающие проверенные ячейки: "
            + ", ".join(f"{variant}/{shot}" for variant, shot in sorted(missing))
        )
    if len(accepted) != data["counts"]["expected_images"]:
        errors.append("Число принятых изображений не совпадает с expected_images.")
    if errors:
        raise SeriesError("Серия не упакована:\n- " + "\n- ".join(errors))
    return accepted


def gallery(data: dict, images: list[dict]) -> str:
    try:
        template = TEMPLATE.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SeriesError(f"Не удалось прочитать шаблон галереи: {exc}") from exc

    escape = lambda value: html.escape(str(value), quote=True)
    image_by_slot = {(item["variant"], item["shot"]): item for item in images}
    headings = "".join(
        f'<th scope="col">{escape(shot["label"])}</th>' for shot in data["shots"]
    )
    rows = []
    for variant in data["variants"]:
        cells = []
        for shot in data["shots"]:
            item = image_by_slot[(variant["id"], shot["id"])]
            path = escape(item["path"])
            prompt_path = escape(item["prompt_path"])
            caption = escape(f'{variant["name"]} — {shot["label"]}')
            note = f'<p>{escape(item["notes"])}</p>' if item.get("notes") else ""
            cells.append(
                f'<td><a href="{path}"><img src="{path}" alt="{caption}" '
                f'loading="lazy"></a><p><a href="{path}">Открыть изображение</a> · '
                f'<a href="{prompt_path}">Открыть промпт</a></p>{note}'
                f'<details><summary>Задание генератору</summary>'
                f'<pre>{escape(item["prompt"])}</pre></details></td>'
            )
        rows.append(
            f'<tr><th scope="row">{escape(variant["name"])}'
            f'<p>{escape(variant["description"])}</p></th>'
            + "".join(cells)
            + "</tr>"
        )

    limitations = "".join(f"<li>{escape(item)}</li>" for item in data["limitations"])
    footer = (
        f"<p>{escape(REVIEW_NOTICE)}</p>"
        f"<ul>{limitations}</ul>"
        "<p>Визуализации не подтверждают размеры, проходы, цену или наличие товара.</p>"
    )
    replacements = {
        "{{TITLE}}": escape(data["title"]),
        "{{SUMMARY}}": escape(
            f'{data["counts"]["variations"]} вариантов × '
            f'{data["counts"]["images_per_variation"]} изображений = '
            f'{data["counts"]["expected_images"]}.'
        ),
        "{{HEADINGS}}": headings,
        "{{ROWS}}": "".join(rows),
        "{{FOOTER}}": footer,
    }
    def replace_marker(match: re.Match[str]) -> str:
        marker = match.group(0)
        if marker not in replacements:
            raise SeriesError("В шаблоне галереи остались незаполненные маркеры.")
        return replacements[marker]

    # Сканируем только шаблон: маркеры внутри данных остаются обычным текстом.
    return re.sub(r"\{\{[A-Z_]+\}\}", replace_marker, template)


def rename_new(source: Path, destination: Path) -> None:
    """Атомарное перемещение без замены даже пустой чужой папки."""
    if os.name == "nt":
        os.rename(source, destination)
        return
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = library.renamex_np
        function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        result = function(os.fsencode(source), os.fsencode(destination), 4)
    elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
        function = library.renameat2
        function.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        result = function(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    else:
        raise SeriesError(
            "Система не поддерживает атомарное создание папки без перезаписи."
        )
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(destination))


def package(brief_path: Path, out: Path) -> int:
    if os.path.lexists(out):
        raise SeriesError(f"Папка результата уже существует; выберите новую: {out}")
    data = read_brief(brief_path)
    accepted = validate_images(data, brief_path.parent)
    portable_input = copy.deepcopy(data)
    for item in portable_input["images"]:
        item.pop("path", None)
    reject_local_paths(portable_input, "переносимые данные")
    if not out.parent.is_dir():
        raise SeriesError(f"Родительская папка результата не существует: {out.parent}")

    with tempfile.TemporaryDirectory(prefix=".interior-series-", dir=out.parent) as temp:
        staging = Path(temp) / "package"
        staging.mkdir()
        output_images: list[dict] = []
        files: list[dict] = []

        for variant in data["variants"]:
            for shot in data["shots"]:
                slot = (variant["id"], shot["id"])
                accepted_item = accepted[slot]
                item = accepted_item["item"]
                stem = f"{variant['id']}-{shot['id']}"
                image_relative = Path("images") / f"{stem}{accepted_item['extension']}"
                prompt_relative = Path("prompts") / f"{stem}.txt"
                image_target = staging / image_relative
                prompt_target = staging / prompt_relative
                image_target.parent.mkdir(parents=True, exist_ok=True)
                prompt_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(accepted_item["source"], image_target)
                if digest(image_target) != accepted_item["sha256"]:
                    raise SeriesError(
                        f"Исходный файл изменился во время упаковки: "
                        f"{accepted_item['source']}"
                    )
                prompt_target.write_text(item["prompt"].rstrip() + "\n", encoding="utf-8")
                portable_item = {
                    "variant": variant["id"],
                    "shot": shot["id"],
                    "path": image_relative.as_posix(),
                    "prompt_path": prompt_relative.as_posix(),
                    "prompt": item["prompt"],
                    "origin": item["origin"],
                    "review": copy.deepcopy(item["review"]),
                }
                if "notes" in item:
                    portable_item["notes"] = item["notes"]
                output_images.append(portable_item)
                files.append(
                    {
                        "variant": variant["id"],
                        "shot": shot["id"],
                        "path": image_relative.as_posix(),
                        "prompt_path": prompt_relative.as_posix(),
                        "sha256": accepted_item["sha256"],
                        "format": accepted_item["format"],
                        "width": accepted_item["width"],
                        "height": accepted_item["height"],
                        "review": copy.deepcopy(item["review"]),
                        **({"notes": item["notes"]} if "notes" in item else {}),
                    }
                )

        shot_by_id = {shot["id"]: shot for shot in data["shots"]}
        portable_brief = {
            key: copy.deepcopy(value)
            for key, value in data.items()
            if key != "images"
        }
        portable_brief["matrix"] = [
            {
                "variant": item["variant"],
                "shot": item["shot"],
                "source_view": shot_by_id[item["shot"]]["source_view"],
                "take": shot_by_id[item["shot"]]["take"],
                "image_path": item["path"],
                "prompt_path": item["prompt_path"],
            }
            for item in output_images
        ]
        manifest = {
            "schema_version": data["schema_version"],
            "job_id": data["job_id"],
            "title": data["title"],
            "target": copy.deepcopy(data["target"]),
            "variation_mode": data["variation_mode"],
            "counts": copy.deepcopy(data["counts"]),
            "variants": copy.deepcopy(data["variants"]),
            "source_views": copy.deepcopy(data["source_views"]),
            "shots": copy.deepcopy(data["shots"]),
            "generator": copy.deepcopy(data["generator"]),
            "limitations": copy.deepcopy(data["limitations"]),
            "images": files,
        }
        validation = {
            "expected_images": data["counts"]["expected_images"],
            "actual_images": len(files),
            "unique_sha256": len({item["sha256"] for item in files}),
            "all_review_fields_pass": True,
            "gallery_images": len(files),
            "prompt_files": len(files),
            "review_source": REVIEW_NOTICE,
        }

        for name, content in (
            ("generation-brief.json", portable_brief),
            ("manifest.json", manifest),
            ("validation.json", validation),
        ):
            (staging / name).write_text(
                json.dumps(content, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        (staging / "index.html").write_text(
            gallery(data, output_images), encoding="utf-8"
        )

        archive_name = f"{data['job_id']}.zip"
        members = sorted(path for path in staging.rglob("*") if path.is_file())
        with zipfile.ZipFile(
            staging / archive_name, "w", zipfile.ZIP_DEFLATED
        ) as archive:
            for member in members:
                archive.write(member, member.relative_to(staging).as_posix())
        expected_members = [member.relative_to(staging).as_posix() for member in members]
        try:
            with zipfile.ZipFile(staging / archive_name) as archive:
                archived_members = archive.namelist()
                if archive.testzip() is not None:
                    raise SeriesError("ZIP не прошёл проверку целостности.")
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise SeriesError(f"Не удалось проверить ZIP: {exc}") from exc
        if len(archived_members) != len(set(archived_members)):
            raise SeriesError("ZIP содержит повторные пути.")
        if archived_members != expected_members:
            raise SeriesError("Состав ZIP не совпадает с составом пакета.")
        rename_new(staging, out)
    return len(files)


class RussianParser(argparse.ArgumentParser):
    def format_usage(self) -> str:
        return super().format_usage().replace("usage: ", "Использование: ", 1)

    def format_help(self) -> str:
        return super().format_help().replace("usage: ", "Использование: ", 1)

    def error(self, message: str) -> None:
        for original, translated in (
            ("the following arguments are required:", "отсутствуют обязательные параметры:"),
            ("unrecognized arguments:", "неизвестные параметры:"),
            ("expected one argument", "требуется одно значение"),
            ("argument ", "параметр "),
            ("ignored explicit argument", "неожиданное значение"),
        ):
            message = message.replace(original, translated)
        self.print_usage(sys.stderr)
        self.exit(2, f"Ошибка параметров: {message}\n")


def main(argv: list[str] | None = None) -> int:
    parser = RussianParser(
        description=__doc__,
        add_help=False,
        usage="%(prog)s --brief ПУТЬ --out НОВАЯ_ПАПКА",
    )
    parser._positionals.title = "Позиционные параметры"
    parser._optionals.title = "Параметры"
    parser.add_argument("-h", "--help", action="help", help="показать справку и завершить")
    parser.add_argument(
        "--brief",
        type=Path,
        required=True,
        help="путь к generation-brief.json",
        metavar="ПУТЬ",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="новая папка в существующем каталоге",
        metavar="НОВАЯ_ПАПКА",
    )
    args = parser.parse_args(argv)
    try:
        count = package(args.brief.absolute(), args.out.absolute())
    except (SeriesError, OSError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    print(
        f"Упаковано изображений: {count}. "
        f"Галерея: {args.out.absolute() / 'index.html'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
