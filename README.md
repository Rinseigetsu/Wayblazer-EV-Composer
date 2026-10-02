# Wayblazer EV CG Composer

[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)]()

> Rebuild event CGs from **Wayblazer** (Eushully System5) by replaying the game's own
> compositing rules — base image plus differential layers, at their original offsets.
> Produces finished 1600×900 PNGs. No game engine involved.

Event CGs in this game are not stored as single images. Each one is a **base image plus a
number of differential layers** that the engine composites at fixed coordinates. This tool
reads the compositing recipe straight out of the game data and replays it offline.

- **138 events, 1092 layer combinations** across the base archives and the Chinese-patch append archive
- Output: 1600×900 PNGs named `EV<id>_diff<recipe>_g<variant>.png`
- One self-contained script — `--workers N` turns on multiprocessing, default is a single process

---

## Features

| | |
|---|---|
| **Exact, not approximated** | Compositing rules are read from the game's own recipe table (`EVINIT.BIN`), not fitted from screenshots |
| **Parallel batch mode** | `--workers N` composes dozens of events concurrently |
| **Portable** | Single self-contained script; drop it into the game folder and run |
| **Both archives** | Base archives (EV1–216) and the append archive (EV126–239) |
| **Non-destructive** | Only Pillow required; never writes to game files |
| **Research tooling included** | Index/image/recipe parsers, AGF library, SYS5502 disassembler, opcode map |

## Requirements

- Python 3.8 or newer
- Pillow (`pip install pillow`)

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Clone

```bash
git clone https://github.com/Rinseigetsu/Wayblazer-EV-Composer.git
cd Wayblazer-EV-Composer
pip install -r requirements.txt
```

### 2. Get the data

You need your own copy of the game. The tool reads these files from the game folder:

```
DATA1.ALF … DATA8.ALF     base archives
APPEND11.ALF, APPEND11.AAI append archive + its index
SYS5INI.BIN               base archive index
AGE.EXE                   (only needed by the disassembler in tools/)
```

### 3. Run

Copy `ev_compose.py` into the game folder, then:

```bash
python ev_compose.py                    # list every composable event
python ev_compose.py 126 2              # compose EV126, recipe #2
python ev_compose.py 11                 # compose every recipe of EV11
python ev_compose.py --all              # compose everything (~1092 images)
python ev_compose.py --out D:/cgout     # custom output directory
python ev_compose.py --all --workers 8  # same, across 8 processes
```

`--workers N` splits the work over N processes — one task per event, or per differential
recipe when a single event is requested. Each worker loads the indexes and recipe tables
itself, so start-up costs a few seconds; for one event a single process is usually fine.

Example session:

```
Reading SYS5INI.BIN (base index) ...   files: 35699
Reading APPEND11.AAI (append index) ... files: 3827
EVINIT recipes: base 215 + append 119 = 334, events: 138

    EV126 diff#2 layer0: EV126_ABA.AGF @ (232,238) [APPEND]
    EV126 diff#2 layer0: EV126_ABB.AGF @ (1200,188) [APPEND]
    -> EV_output/EV126_diff2_g0.png
Done: 1092 combinations composed
```

### 4. Output

```
<game folder>/EV_output/
├── EV126_diff1_g0.png     # EV126, recipe 1, variant 0
├── EV126_diff2_g0.png     # EV126, recipe 2, variant 0 (uses EV126_ABA)
├── EV126_diff2_g1.png     # same recipe, next variant
└── ...
```

- `diff<N>` — recipe index (a distinct differential combination for that event)
- `g<N>` — parallel layer set / variant within that recipe

---

## How It Works

```
  (1) Index            (2) Recipe             (3) Decode            (4) Compose
  SYS5INI.BIN    →     EVINIT.BIN        →    EV*.AGF          →   PIL
  name → location      base + diffs + XY      LZSS / BGR / alpha   finished PNG
```

1. **Index** — `SYS5INI.BIN` (base) and `APPEND11.AAI` (append) map file names to
   archive offsets/sizes. The **position of a record in the file list is its ID**,
   which is how resource references inside recipes are resolved.
2. **Recipe** — `EVINIT.BIN` is a data script: one record per (event, recipe) pair,
   listing which images to use and where to place them.
3. **Decode** — event images are a variant of the Eushully AGF format:
   LZSS-compressed, **BGR** channel order, bottom-up row order, with a separate
   `ACIF` section carrying the alpha channel for 32-bit images.
4. **Compose** — paste the base image full-frame, then paste each differential layer
   opaquely at its anchor coordinate.

Full details — field maps, format specs, address tables, verification method — are in
[`docs/FORMATS.md`](docs/FORMATS.md) and
[`docs/REVERSE_ENGINEERING.md`](docs/REVERSE_ENGINEERING.md).

### Verification without running the game

A differential layer *is* the corresponding region of the base image with edits applied.
Therefore the **top-left pixels of a differential must match the pixels at its anchor
coordinate in the base image**. Comparing those regions verifies every coordinate offline;
all offsets shipped in this project were checked this way.

---

## Supported Events

| Source | Event IDs |
|---|---|
| Base archives (`DATA1-8.ALF`) | 1 – 216 (subset) |
| Append archive (`APPEND11.ALF`) | 126 – 239 |
| **Total** | **138 events / 1092 images** |

Run `python ev_compose.py` with no arguments to list what your copy of the game provides —
IDs vary between releases and patches.

---

## Repository Layout

```
wayblazer-ev-composer/
├── ev_compose.py               the composer (self-contained, --workers N for parallel)
├── tools/                      research & debugging utilities
│   ├── parse_append.py           append-archive index parser
│   ├── parse_ev.py               event image (AGF) parser
│   ├── parse_evinit.py           compositing recipe parser
│   ├── extract_ev_rules.py       dump every recipe as a readable table
│   ├── analyze_agf.py            AGF / archive-index library
│   ├── locate_file.py            locate any file inside the ALF archives
│   ├── disasm_sc.py              SYS5502 bytecode disassembler
│   ├── disasm_full.py            full-script disassembler
│   └── opcode_map.json           opcode → handler address map (574 entries)
├── docs/
│   ├── FORMATS.md                file formats and compositing semantics
│   └── REVERSE_ENGINEERING.md    method, field maps, address tables
└── examples/
```

Tool scripts locate the game folder automatically, in this order:
`WAYBLAZER_DIR` environment variable → script directory → sibling directories → user home.
If your installation lives elsewhere:

```bash
# Linux / macOS
export WAYBLAZER_DIR="/path/to/WayblazerCHSR18"
# Windows (cmd)
set WAYBLAZER_DIR=D:\Games\WayblazerCHSR18
# Windows (PowerShell)
$env:WAYBLAZER_DIR = 'D:\Games\WayblazerCHSR18'

python tools/extract_ev_rules.py
```

---

## FAQ

**Missing-file error?**
Put the script in the game folder, or set `WAYBLAZER_DIR`. It needs `APPEND11.ALF`,
`APPEND11.AAI`, `DATA1.ALF` and `SYS5INI.BIN`.

**Colours look swapped (warm/cool inverted)?**
That happens when AGF pixels are treated as RGB. They are stored as **BGR** and
**bottom-up**; this project handles both.

**One event's differentials sit at the wrong offset?**
Please open an issue with the event ID, recipe number and a screenshot. Recipe layouts
differ between events (slot numbering is not uniform), and this project handles that by
classifying slots per value plus a pairing rule — see `docs/FORMATS.md` §2.3.

**Output differs slightly from an in-game screenshot?**
This tool reproduces the **data-level compositing rules**. Real-time engine behaviour
(blend states, tweened animation) is out of scope: static results match the game, but
mid-animation frames will not.

**Can I use this on other Eushully titles?**
Not directly — index offsets, recipe table locations and event IDs differ per title.
The framework here (index parsers, AGF decoder, SYS5502 disassembler) is a reasonable
starting point for a port.

**Which game version?**
Developed against the Chinese R18 patch build 1.04.0020 (`AGE.EXE`). Other builds may
place data at different offsets; see `docs/REVERSE_ENGINEERING.md` §1 for how to relocate them.

---

## Disclaimer

- This project exists for **interoperability and format research** — it lets players view
  content from a game they own, offline.
- **No game assets are included.** No images, scripts, executables or decompilation data
  are part of this repository. **You must own the game** to use it.
- Do **not** use the images this tool produces for **commercial purposes** or
  **redistribution**. Artwork remains the property of its rights holders.
- Reverse engineering has a different legal status in different jurisdictions. Use this
  software only where it is **lawful** to do so.
- Provided "as is", without warranty of any kind. The author is not liable for any
  consequences of its use.

## Acknowledgements

- [GARbro](https://github.com/morkt/GARbro) — invaluable reference for the ALF/AGF
  container formats (LZSS parameters, pixel layout, ACIF section)
- [Ghidra](https://ghidra-sre.org/) — decompilation and analysis platform
- [Pillow](https://python-pillow.org/) — image compositing

## License

[MIT](LICENSE) — covering the code and documentation in this repository only.
