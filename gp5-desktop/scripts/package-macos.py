#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
# ─── How to run ───
# python scripts/package-macos.py sourceElectronZip appAsar outputZip
# Or: uv run --no-project scripts/package-macos.py sourceElectronZip appAsar outputZip
# Python is a build-time dependency only; the distributed application embeds Electron.
# ──────────────────
"""Repack macOS Electron ZIP entries without extracting Unix links onto Windows."""

from __future__ import annotations

import copy
import os
import plistlib
import shutil
import stat
import sys
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Final, TypeAlias, assert_never
from zipfile import BadZipFile, ZipFile, ZipInfo

if TYPE_CHECKING:
    from collections.abc import Callable

SOURCE_ROOT: Final = "Electron.app/"
TARGET_ROOT: Final = "GP5 PDF.app/"
PLIST_PATH: Final = SOURCE_ROOT + "Contents/Info.plist"
DEFAULT_APP: Final = SOURCE_ROOT + "Contents/Resources/default_app.asar"
APP_ID: Final = "local.gp5pdf.desktop"
APP_VERSION: Final = "1.1.0"
CLI_ARG_COUNT: Final = 4
ZIP_UNIX_SYSTEM: Final = 3
PlistValue: TypeAlias = (
    str
    | int
    | float
    | bool
    | bytes
    | datetime
    | list["PlistValue"]
    | dict[str, "PlistValue"]
)


class _EntryKind(Enum):
    PLIST = "plist"
    APP = "app"
    RUNTIME = "runtime"


@dataclass(frozen=True, slots=True)
class PackageError(Exception):
    """An input archive or preservation invariant prevented packaging."""

    detail: str


@dataclass(frozen=True, slots=True)
class ArchiveAudit:
    """Counts of entries whose persisted ZIP metadata passed comparison."""

    entries: int
    symlinks: int
    executable_files: int
    unix_mode_entries: int


def updated_plist(
    data: bytes, decode: Callable[[bytes], PlistValue] = plistlib.loads
) -> bytes:
    """Preserve Electron runtime settings while naming the new app bundle."""
    metadata = decode(data)
    if not isinstance(metadata, dict):
        message = "Electron Info.plist must contain a dictionary"
        raise PackageError(message)
    if metadata.get("CFBundleExecutable") != "Electron":
        message = "Expected the original Electron executable in Info.plist"
        raise PackageError(message)
    metadata.update(
        CFBundleName="GP5 PDF",
        CFBundleDisplayName="GP5 PDF",
        CFBundleIdentifier=APP_ID,
        CFBundleShortVersionString=APP_VERSION,
        CFBundleVersion=APP_VERSION,
    )
    _ = metadata.pop("ElectronAsarIntegrity", None)
    return plistlib.dumps(metadata, fmt=plistlib.FMT_XML, sort_keys=False)


def target_entry(original: ZipInfo) -> ZipInfo:
    """Copy every ZIP metadata field, changing only the application entry path."""
    entry = copy.copy(original)
    if original.filename.startswith(SOURCE_ROOT):
        entry.filename = TARGET_ROOT + original.filename[len(SOURCE_ROOT) :]
    if original.filename == DEFAULT_APP:
        entry.filename = TARGET_ROOT + "Contents/Resources/app.asar"
    return entry


def audit_archive(source: ZipFile, output: ZipFile) -> ArchiveAudit:
    """Compare stored metadata and unchanged CRCs after ZIP serialization."""
    symlinks = executable_files = unix_modes = 0
    fields = (
        "external_attr",
        "internal_attr",
        "create_system",
        "extra",
        "comment",
        "date_time",
        "compress_type",
    )
    if (
        len(source.infolist()) != len(output.infolist())
        or source.comment != output.comment
    ):
        message = "Archive entry count or comment changed unexpectedly"
        raise PackageError(message)
    for original in source.infolist():
        saved = output.getinfo(target_entry(original).filename)
        if any(getattr(original, field) != getattr(saved, field) for field in fields):
            message = f"ZIP metadata changed: {original.filename}"
            raise PackageError(message)
        if original.filename not in (PLIST_PATH, DEFAULT_APP) and (
            original.CRC,
            original.file_size,
        ) != (saved.CRC, saved.file_size):
            message = f"Entry bytes changed: {original.filename}"
            raise PackageError(message)
        mode = saved.external_attr >> 16
        symlinks += stat.S_ISLNK(mode)
        executable_files += stat.S_ISREG(mode) and bool(mode & 0o111)
        unix_modes += saved.create_system == ZIP_UNIX_SYSTEM
    return ArchiveAudit(len(output.infolist()), symlinks, executable_files, unix_modes)


def _validate_source(source: ZipFile) -> None:
    names = source.namelist()
    required = (PLIST_PATH, DEFAULT_APP, SOURCE_ROOT + "Contents/MacOS/Electron")
    if len(names) != len(set(names)) or any(name not in names for name in required):
        message = "Expected one original Electron macOS distribution"
        raise PackageError(message)
    if SOURCE_ROOT + "Contents/Resources/app.asar" in names:
        message = "The input already contains an application ASAR"
        raise PackageError(message)
    for name in names:
        if (
            name.startswith("/")
            or "\\" in name
            or any(part in (".", "..") for part in name.split("/"))
        ):
            message = f"Unsafe ZIP entry path: {name}"
            raise PackageError(message)


def package_macos(source_zip: Path, app_asar: Path, output_zip: Path) -> ArchiveAudit:
    """Create an unverified staging ZIP; never overwrite an existing artifact."""
    if output_zip.exists():
        message = f"Output already exists: {output_zip}"
        raise PackageError(message)
    if app_asar.stat().st_size == 0:
        message = "The application ASAR is empty"
        raise PackageError(message)
    with ZipFile(source_zip) as source:
        _validate_source(source)
        metadata = updated_plist(source.read(PLIST_PATH))
        with TemporaryDirectory(
            prefix=".gp5-macos-", dir=output_zip.parent
        ) as temporary:
            staged = Path(temporary) / "app.zip"
            with ZipFile(staged, "w") as output:
                output.comment = source.comment
                for original in source.infolist():
                    entry = target_entry(original)
                    kind = {
                        PLIST_PATH: _EntryKind.PLIST,
                        DEFAULT_APP: _EntryKind.APP,
                    }.get(original.filename, _EntryKind.RUNTIME)
                    match kind:
                        case _EntryKind.PLIST:
                            output.writestr(entry, metadata)
                        case _EntryKind.APP:
                            entry.file_size = app_asar.stat().st_size
                            with (
                                app_asar.open("rb") as payload,
                                output.open(entry, "w") as destination,
                            ):
                                shutil.copyfileobj(payload, destination)
                        case _EntryKind.RUNTIME:
                            with (
                                source.open(original) as payload,
                                output.open(entry, "w") as destination,
                            ):
                                shutil.copyfileobj(payload, destination)
                        case _:
                            assert_never(kind)
            with ZipFile(staged) as output:
                audit = audit_archive(source, output)
            # Hard links publish the finished ZIP without overwriting a racing output.
            os.link(staged, output_zip)
    return audit


def main() -> int:
    """Expose the three-path build interface and a metadata preservation report."""
    if len(sys.argv) != CLI_ARG_COUNT:
        _ = sys.stderr.write(
            "Usage: package-macos.py sourceElectronZip appAsar outputZip\n"
        )
        return 2
    source_zip, app_asar, output_zip = (Path(value).resolve() for value in sys.argv[1:])
    try:
        audit = package_macos(source_zip, app_asar, output_zip)
    except (OSError, BadZipFile, PackageError, plistlib.InvalidFileException) as error:
        _ = sys.stderr.write(f"Packaging failed: {error}\n")
        return 1
    _ = sys.stdout.write(
        "\n".join(
            (
                f"Created: {output_zip}",
                f"Metadata audit: {audit.entries} entries; {audit.symlinks} symlinks;",
                f"Executable files preserved: {audit.executable_files}",
                f"Unix entries preserved: {audit.unix_mode_entries}",
                "GP5 PDF signing not performed; Electron signatures may be invalid.",
                "macOS runtime UNVERIFIED. Native Mac validation/signing required.",
                "",
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
