# NDS ROM Renamer

Command-line tool for renaming Nintendo DS `.nds` ROM files using a local
ADVANsCEne NDS CRC database. The script scans a folder, matches each ROM by
CRC32 first and by NDS header game code as a fallback, then renames matching
ROMs in place to a consistent ADVANsCEne-style filename.

When a ROM is renamed, matching save files are renamed too:

- `<rom name>.sav`
- `<rom name>.nds.sav`

## Requirements

- Python 3.10 or newer
- The ADVANsCEne NDS CRC ZIP database:
  <https://www.advanscene.com/offline/datas/ADVANsCEne_NDScrc.zip>

No third-party Python packages are required.

## Usage

Download `ADVANsCEne_NDScrc.zip`, then run:

```bash
python3 nds_rename.py \
  --database-zip /path/to/ADVANsCEne_NDScrc.zip \
  --rom-folder /path/to/rom-folder
```

Example:

```bash
python3 nds_rename.py \
  --database-zip ~/Downloads/ADVANsCEne_NDScrc.zip \
  --rom-folder ~/Games/NDS
```

The script prints every match, rename, skipped file, and final summary to the
terminal.

## Filename Format

Matched ROMs are renamed to:

```text
Game Title (Region).nds
```

The title and database match come from the ADVANsCEne data. The region is
inferred from the ROM's NDS header game code. Release numbers are printed in the
terminal output when available, but they are not included in renamed files.

## Options

```text
--database-zip PATH       Path to ADVANsCEne_NDScrc.zip
--rom-folder PATH         Folder containing .nds files to rename
```

## Safety Notes

- Files are renamed in place.
- The script does not download anything.
- The script does not delete files.
- If a destination filename already exists, the rename is skipped and reported.

Before running against a large collection, consider making a backup or testing
with a small folder first.

## Thanks

Thanks to [NDS-ROM-Renamer](https://github.com/AntonIT99/NDS-ROM-Renamer) for
the original project inspiration.
