"""Bounded ZIP reader: no filesystem extraction, path interpretation or object loading."""

import hashlib
import io
import json
import math
import re
import stat
import zipfile
from typing import Any

from app.domain.archives import MAX_ARCHIVE, MAX_EXPANDED, MAX_FILES, ArchiveManifest, FileEntry


def json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError("Nonfinite JSON number")

    def finite(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Nonfinite JSON number")
        return number

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite)


def descriptor(raw: bytes) -> FileEntry:
    return FileEntry(sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw))


def safe_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.\-/]{0,239}", name)) and all(
        p not in ("", ".", "..") for p in name.split("/")
    )


def read_archive(raw: bytes) -> tuple[ArchiveManifest, dict[str, bytes]]:
    if len(raw) > MAX_ARCHIVE or not raw.startswith(b"PK\x03\x04"):
        raise ValueError("Archive exceeds 64 MiB")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if not 2 <= len(entries) <= MAX_FILES or sum(e.file_size for e in entries) > MAX_EXPANDED:
            raise ValueError("Archive exceeds expansion/file-count limits")
        names = [e.filename for e in entries]
        if len(set(names)) != len(names) or "manifest.json" not in names:
            raise ValueError("Duplicate entry or missing manifest")
        for entry in entries:
            mode = stat.S_IFMT(entry.external_attr >> 16)
            if (
                not safe_name(entry.filename)
                or entry.is_dir()
                or mode not in (0, stat.S_IFREG)
                or entry.flag_bits & 1
                or entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                or entry.file_size > 32 * 1024**2
                or entry.file_size > max(1, entry.compress_size) * 200
            ):
                raise ValueError("Unsafe archive entry or compression ratio")
        manifest_entry = archive.getinfo("manifest.json")
        if manifest_entry.file_size > 1024**2:
            raise ValueError("Manifest exceeds 1 MiB")
        manifest = ArchiveManifest.model_validate(strict_json(archive.read(manifest_entry)))
        if set(manifest.files) != set(names) - {"manifest.json"}:
            raise ValueError("Undeclared or missing archive files")
        files = {}
        for name, expected in manifest.files.items():
            # Embedded DOCX is allowed only as an opaque generated report artifact.
            if not re.fullmatch(
                r"project\.json|tools\.json|diagnostic\.json|objects/[0-9a-f]{64}", name
            ):
                raise ValueError("Unsupported/recursive archive file")
            entry = archive.getinfo(name)
            if entry.file_size != expected.size_bytes:
                raise ValueError("Archive size mismatch")
            data = archive.read(entry)
            if descriptor(data) != expected:
                raise ValueError("Archive checksum mismatch")
            files[name] = data
        return manifest, files


def write_archive(manifest: ArchiveManifest, files: dict[str, bytes]) -> bytes:
    if len(files) + 1 > MAX_FILES or sum(len(v) for v in files.values()) > MAX_EXPANDED:
        raise ValueError("Project exceeds archive limits; omit outputs or reduce project size")
    manifest.files.clear()
    manifest.files.update({name: descriptor(data) for name, data in files.items()})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", json_bytes(manifest.model_dump(mode="json")))
        for name, data in files.items():
            archive.writestr(name, data)
    raw = output.getvalue()
    if len(raw) > MAX_ARCHIVE:
        raise ValueError("Project exceeds 64 MiB archive limit; omit outputs")
    return raw


def nested_archive(data: bytes) -> bool:
    return (
        data.startswith(
            (
                b"PK\x03\x04",
                b"PK\x05\x06",
                b"PK\x07\x08",
                b"7z\xbc\xaf",
                b"\x1f\x8b",
                b"Rar!",
                b"\xfd7zXZ",
                b"BZh",
                b"\x28\xb5\x2f\xfd",
            )
        )
        or data[257:262] == b"ustar"
    )
