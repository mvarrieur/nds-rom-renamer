#!/usr/bin/env python3
"""Command-line NDS ROM renamer using a local ADVANsCEne NDS CRC ZIP.

This script does not download anything and does not delete files.
It renames matching .nds files and matching .sav/.nds.sav
save files in place, while logging each action to the terminal.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET


REGION_BY_CODE = {
    "E": "U",
    "P": "E",
    "J": "J",
    "K": "K",
    "F": "F",
    "D": "G",
    "S": "S",
    "I": "I",
    "H": "NL",
    "X": "E",
    "Y": "E",
}


@dataclass(frozen=True)
class RenamePlan:
    rom: Path
    destination: Path
    crc: str
    game_code: str
    match_method: str
    release: str
    title: str
    region: str
    matching_saves: tuple[Path, ...]


def crc32_file(path: Path) -> str:
    crc = 0
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            crc = zlib.crc32(chunk, crc)
    return f"{crc & 0xffffffff:08X}"


def files_are_identical(a: Path, b: Path) -> bool:
    return a.stat().st_size == b.stat().st_size and crc32_file(a) == crc32_file(b)


def read_nds_header(path: Path) -> str:
    with path.open("rb") as f:
        h = f.read(0x200)
    return h[0x0C:0x10].decode("ascii", errors="ignore").strip("\x00 ")


def region_from_game_code(game_code: str) -> str:
    return REGION_BY_CODE.get(game_code[3].upper(), "") if len(game_code) >= 4 else ""


def clean_tag(tag: str) -> str:
    return tag.split("}")[-1].lower()


def all_text_and_attrs(elem: ET.Element) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}

    for e in elem.iter():
        tag = clean_tag(e.tag)

        if e.text and e.text.strip():
            values.setdefault(tag, []).append(e.text.strip())

        for k, v in e.attrib.items():
            if v and v.strip():
                values.setdefault(k.lower(), []).append(v.strip())

    return values


def first(values: dict[str, list[str]], keys: list[str]) -> str:
    for key in keys:
        key = key.lower()
        if key in values and values[key]:
            return values[key][0]
    return ""


def build_advanscene_indexes(root: ET.Element) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    by_crc: dict[str, dict[str, str]] = {}
    by_game_code: dict[str, dict[str, str]] = {}

    for elem in root.iter():
        values = all_text_and_attrs(elem)

        title = first(values, ["name", "title", "romname", "gamename"])
        release_no = first(
            values,
            ["number", "release", "release_number", "releasenumber", "id", "n", "imagenumber"],
        )
        serial = first(values, ["serial", "gamecode", "game_code", "code"])
        crc = first(values, ["crc", "crc32", "romcrc"])

        if not title:
            continue

        info = {
            "release": release_no or "",
            "title": title,
        }

        if crc:
            by_crc[crc.upper()] = info

        if serial:
            serial = serial.upper()
            serial = serial.replace("NTR-", "").replace("TWL-", "")
            serial = serial.split("-")[0]

            if len(serial) >= 4:
                by_game_code[serial[:4]] = info

    return by_crc, by_game_code


def load_advanscene_xml(zip_path: Path) -> ET.Element:
    data = zip_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        xml_names = [n for n in z.namelist() if n.lower().endswith(".xml")]
        if not xml_names:
            raise RuntimeError(f"No XML file found inside {zip_path}")
        if len(xml_names) > 1:
            raise RuntimeError(f"Expected one XML file inside {zip_path}, found {xml_names}")
        return ET.fromstring(z.read(xml_names[0]))


def format_release(release: str) -> str:
    release = str(release).strip()
    return release.zfill(4) if release.isdigit() else ""


def sanitize_filename_part(name: str) -> str:
    for char in '<>:"/\\|?*':
        name = name.replace(char, " - ")

    name = re.sub(r"\s+", " ", name).strip()
    return name.rstrip(". ")


def build_new_base_name(title: str, region: str) -> str:
    base = title

    if region:
        base += f" ({region})"

    return sanitize_filename_part(base)


def find_matching_save_files(rom: Path) -> tuple[Path, ...]:
    candidates: list[Path] = []
    rom_stem_lower = rom.stem.lower()

    for file in rom.parent.iterdir():
        if not file.is_file():
            continue

        name_lower = file.name.lower()

        if name_lower == f"{rom_stem_lower}.sav":
            candidates.append(file)
        elif name_lower == f"{rom_stem_lower}.nds.sav":
            candidates.append(file)

    return tuple(candidates)


def build_rename_plan(rom: Path, by_crc: dict[str, dict[str, str]], by_game_code: dict[str, dict[str, str]]) -> RenamePlan | None:
    crc = crc32_file(rom)
    game_code = read_nds_header(rom)

    info = by_crc.get(crc)
    match_method = "CRC32" if info else ""

    if not info:
        info = by_game_code.get(game_code.upper())
        match_method = "game code" if info else ""

    if not info or not info.get("title"):
        return None

    release = format_release(info.get("release", ""))
    title = sanitize_filename_part(info["title"])
    region = region_from_game_code(game_code)
    new_base_name = build_new_base_name(title, region)

    return RenamePlan(
        rom=rom,
        destination=rom.with_name(new_base_name + ".nds"),
        crc=crc,
        game_code=game_code,
        match_method=match_method,
        release=release,
        title=title,
        region=region,
        matching_saves=find_matching_save_files(rom),
    )


def list_roms(folder: Path) -> list[Path]:
    roms = [
        p
        for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() == ".nds" and not p.name.startswith("._")
    ]
    return sorted(roms, key=lambda p: p.name.lower())


def log_collision(kind: str, source: Path, destination: Path) -> None:
    status = "IDENTICAL" if files_are_identical(source, destination) else "DIFFERENT"
    print(f"Could not rename {kind}: destination already exists and is {status}:")
    print(f"  origin:      {source.name}")
    print(f"  destination: {destination.name}")


def rename_save_files(save_files: tuple[Path, ...], renamed_rom: Path) -> tuple[int, int, int]:
    processed_sav = 0
    processed_nds_sav = 0
    renamed_saves = 0

    for save in save_files:
        if save.name.lower().endswith(".nds.sav"):
            processed_nds_sav += 1
        elif save.suffix.lower() == ".sav":
            processed_sav += 1

        new_save = renamed_rom.with_suffix(".sav")

        if save.name == new_save.name:
            print(f"Save already named correctly: {save.name}")
            continue

        if new_save.exists():
            log_collision("save", save, new_save)
            continue

        print("Renaming save:")
        print(f"  origin:      {save.name}")
        print(f"  destination: {new_save.name}")
        save.rename(new_save)
        renamed_saves += 1

    return processed_sav, processed_nds_sav, renamed_saves


def process_folder(folder: Path, database_zip: Path) -> int:
    root = load_advanscene_xml(database_zip)
    by_crc, by_game_code = build_advanscene_indexes(root)
    nds_files = list_roms(folder)

    processed_nds = 0
    processed_sav = 0
    processed_nds_sav = 0
    renamed_nds = 0
    renamed_saves = 0
    unmatched_nds = 0
    skipped_existing = 0
    already_named = 0

    print("NDS CLI renamer")
    print(f"Database ZIP: {database_zip}")
    print(f"ROM folder:   {folder}")
    print(f"Indexed CRC entries:       {len(by_crc)}")
    print(f"Indexed game-code entries: {len(by_game_code)}")
    print(f"Found .nds files:          {len(nds_files)}")
    print()

    for rom in nds_files:
        processed_nds += 1
        plan = build_rename_plan(rom, by_crc, by_game_code)

        if not plan:
            unmatched_nds += 1
            print(f"No database match: {rom.name}")
            continue

        print(f"Matched {rom.name}")
        print(f"  method:  {plan.match_method}")
        print(f"  crc32:   {plan.crc}")
        print(f"  code:    {plan.game_code or '(blank)'}")
        print(f"  title:   {plan.title}")
        print(f"  release: {plan.release or '(blank)'}")
        print(f"  region:  {plan.region or '(blank)'}")

        if rom.name == plan.destination.name:
            already_named += 1
            print(f"Already named correctly: {rom.name}")
            save_counts = rename_save_files(plan.matching_saves, rom)
            processed_sav += save_counts[0]
            processed_nds_sav += save_counts[1]
            renamed_saves += save_counts[2]
            print()
            continue

        if plan.destination.exists():
            skipped_existing += 1
            log_collision("ROM", rom, plan.destination)
            print()
            continue

        print("Renaming ROM:")
        print(f"  origin:      {rom.name}")
        print(f"  destination: {plan.destination.name}")
        rom.rename(plan.destination)
        renamed_nds += 1

        save_counts = rename_save_files(plan.matching_saves, plan.destination)
        processed_sav += save_counts[0]
        processed_nds_sav += save_counts[1]
        renamed_saves += save_counts[2]
        print()

    print("Processed files:")
    print(f".nds:     {processed_nds}")
    print(f".sav:     {processed_sav}")
    print(f".nds.sav: {processed_nds_sav}")
    print()
    print("Results:")
    print(f".nds renamed:              {renamed_nds}")
    print(f"saves renamed:             {renamed_saves}")
    print(f"already correctly named:   {already_named}")
    print(f"unmatched .nds:            {unmatched_nds}")
    print(f"skipped existing conflict: {skipped_existing}")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rename NDS ROMs from a local ADVANsCEne NDS CRC ZIP. Files are renamed in place.")
    parser.add_argument("--database-zip", required=True, type=Path, help="Path to ADVANsCEne_NDScrc.zip")
    parser.add_argument("--rom-folder", required=True, type=Path, help="Folder containing .nds files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.database_zip.is_file():
        raise RuntimeError(f"Database ZIP not found: {args.database_zip}")
    if not args.rom_folder.is_dir():
        raise RuntimeError(f"ROM folder not found: {args.rom_folder}")

    return process_folder(args.rom_folder, args.database_zip)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
