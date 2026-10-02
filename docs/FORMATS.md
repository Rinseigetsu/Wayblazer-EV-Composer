# File Format Reference

This document describes the data formats involved in EV CG compositing. Every structure
listed here is a **factual description** of the game's binary data; no game code or assets
are reproduced.

---

## 1. Archives and Indexes

### 1.1 ALF archives

Game resources are packed into several `*.ALF` archives:

| Archive | Contents |
|---|---|
| `DATA1.ALF` … `DATA8.ALF` | Base game resources (scripts, images, audio) |
| `APPEND01.ALF` / `APPEND11.ALF` | Append pack (CGs and voices added by the Chinese patch) |

The archives themselves **do not store file names** — an archive alone reveals nothing
about its contents.

### 1.2 Index files

File-name indexes are supplied by system files with a uniform structure
(**LZSS-compressed + fixed-length fields**):

| Index file | Magic | Compressed-data offset | Covers |
|---|---|---|---|
| `SYS5INI.BIN` | `S5IC` (UTF-16) | `0x224` | `DATA1-8.ALF` |
| `APPEND11.AAI` | `S5AC` (UTF-16) | `0x21C` | `APPEND11.ALF` |

Layout:

```
offset 0x224 / 0x21C : uint32  compressed data length
immediately after    : LZSS-compressed index data
```

The decompressed index:

```
uint32  archive count N
N × 0x200 bytes   archive names (UTF-16LE, fixed-length fields)
uint32  file count M
M × record:
    0x80 bytes  file name (UTF-16LE, fixed-length field)
    int32       archive id (arc_id)
    int32       file number within the archive
    uint32      offset within the archive
    uint32      size
```

> **File sequence number**: the record's **index in this list** (from 0) is that file's
> sequence number. It is the key to decoding resource references (see §3).

**LZSS parameters** (matching GARbro):

```
frame size        0x1000
initial fill      0
initial position  0xFEE
minimum match     3
control byte      8 flags per byte, LSB first: 1 = literal byte, 0 = match pair
match pair        (offset_low, (offset_high << 4) | (length - 3))
```

### 1.3 Append-pack file names

File names in the append index carry a `$11$` prefix (an internal path marker), e.g.
`$11$EV126A.AGF`. Strip the prefix to get the real file name.

---

## 2. Compositing Recipes (EVINIT.BIN)

`EVINIT.BIN` is a **SYS5502 data script**: the header matches an ordinary script, and the
body is a stream of "assign a value to a variable" records.

| Source | Location |
|---|---|
| Base | `DATA1.ALF` offset `0x518FEE78`, size `0x19514` |
| Append | `APPEND11.ALF` offset `0x179D8EDC`, size `0x12288` |

### 2.1 Header (0x44 bytes)

```
0x00  16 bytes  "SYS5502 " (UTF-16LE)
0x10  int32     version
0x14  int32     int variable array size
0x18  int32     float variable array size
0x1C  int32     string variable array size
0x20  int32     extra array 1 size
0x24  int32     extra array 2 size
0x28  int32     extra table size (28)
0x2C  24 bytes  3 × (count, offset) — table offsets relative to body
0x44  onward    instruction stream (body)
```

### 2.2 Instruction encoding

```
[opcode:uint32][operands × N, each 8 bytes = (type:uint32, value:int32)]
```

Opcodes used by this file:

| Opcode | Operands | Meaning |
|---|---|---|
| `90` | 3 | Compare (used as "current EV id == X") |
| `85` | 2 | Assignment: `var[op1] = op2` |
| `86` | 3 | Logical OR |
| `140` | 1 | Jump (to the next recipe) |
| `160` | 3 | Conditional jump |

### 2.3 Structure of one recipe

```
op90 (var EC42, value = EV id)      ← record start: which event this is
op90 (var EC43, value = diff id)    ← which differential group of that event
op85 (slot var, value)  × N         ← layers and coordinates
...
op140 (jump)                        ← end of record
```

**Slots fall into three classes** (distinguished by the variable's address range):

| Slot range | Role |
|---|---|
| `0x18D5xx` | Resource reference (points at an image) |
| `0x18D6xx` | X coordinate |
| `0x18D7xx` | Y coordinate |

> ⚠️ **Different events use different slot numbers** (e.g. EV126 uses the `0x18D5A5~`
> series, EV239 the `0x18D5B2~` series). So you must **not** classify by slot number
> alone: classify by **value** instead — a value that resolves to an EV image file name
> is a reference, anything else is a coordinate.

**Pairing of X and Y slots**:

```
X slot number - Y slot number = 0x60
example: 0x18D672 ↔ 0x18D712
```

If an X slot has **no corresponding Y slot** (which happens for some events), then
**Y = 0** for that coordinate. Do not "reuse the previous Y" — doing so shifts the image
downward, as observed in practice.

### 2.4 From recipe to layers

References inside one recipe appear in order, and two shapes have been observed:

```
Simple form:  [base, main diff, X, Y]
Full form:    [base, main diff, X1, Y1, secondary diff, X2, Y2, (mask)]
```

**Layer splitting rule**: a base-image reference appearing **again** starts a new layer.
A single recipe may therefore hold several parallel variants, emitted as `g0`, `g1`, ….

---

## 3. Decoding Resource References

References inside a recipe are numbers (e.g. `0xB000D52`, `0x6BB6`), not file names:

```
seq = reference & 0xFFFF
high 16 bits == 0xB00  →  look up entry "seq" in the append index (APPEND11.AAI)
high 16 bits anything else  →  look up entry "seq" in the base index (SYS5INI.BIN)
```

Worked examples:

| Reference | `& 0xFFFF` | Index entry | Result |
|---|---|---|---|
| `0xB000D52` | 3410 | APPEND11.AAI #3410 | `EV126A.AGF` ✅ |
| `0xB000D54` | 3412 | APPEND11.AAI #3412 | `EV126_ABA.AGF` ✅ |
| `0x6BB6` | 27574 | SYS5INI.BIN #27574 | `EV001A.AGF` ✅ |

---

## 4. Event Image Format (AGF variant)

Event images use a variant of the Eushully AGF format: **the header carries no `ACGF`
magic** (`[0x00]` is 0); the rest of the structure is identical.

```
0x00  uint32  0 (no magic; a standard AGF has "ACGF" here)
0x04  uint32  type: 1 = 24bpp, 2 = 32bpp
0x08  uint32  (unused / 0)
0x0C  uint32  decompressed size of sec2
0x10  uint32  same as above
0x14  uint32  compressed size of sec2
0x18  onward  sec2 data (LZSS-compressed; raw if both sizes match)
```

**sec2** (after decompression):

```
0x14  uint32  width
0x18  uint32  height
0x1E  uint16  source bit depth
```

**Pixel section** (immediately after the compressed sec2 data):

```
uint32  skip
uint32  data size
uint32  compressed size
        → LZSS-compressed pixel data (raw when the sizes match)
```

**Alpha section** (present only when `type = 2`, immediately after the pixel section):

```
0x00  4 bytes  "ACIF"
0x1C  uint32   decompressed size (= width × height)
0x20  uint32   compressed size
0x24  onward   LZSS-compressed alpha channel
```

### 4.1 Three things that matter

1. **Pixels are stored in BGR order** (not RGB). Skipping the swap exchanges red and blue
   — the picture's warm/cool tones invert.
2. **Pixels are stored bottom-up** and must be flipped row-wise.
3. **24bpp differentials are replacement patches**: they carry no transparency of their
   own and cover the base image entirely. Their content already includes a copy of the
   covered region, so the seams line up perfectly.

### 4.2 Sizes and roles

| Image | Typical size | Role |
|---|---|---|
| `EV<id>A.AGF` | 1600×900 | Base image (fills the frame) |
| `EV<id>_XXX.AGF` | 368×900, 544×448, 400×464, … | Differential (partial replacement patch) |
| `EVM<id>*.AGF` | 192×108, … | Engine auxiliary image, **not composited** |

---

## 5. Compositing Semantics

```
canvas = base image (1600×900)
for each layer in the recipe's layers:
    for each differential in that layer:
        canvas.paste(differential, (X, Y))   # opaque, (X, Y) is the top-left anchor
write PNG
```

- **Coordinates are top-left anchors**, not centres.
- Multiple layers under one recipe are **parallel variants**, each written out separately
  (`g0`, `g1`, …).
- Images with the `EVM` prefix are skipped.

### Verification method (pixel anchor test)

A differential matches the content of the region it covers, therefore:

```
mean colour of the differential's top-left N×N block
    == mean colour of the same-size block at (X, Y) in the base image
```

A match means the coordinate is correct. This works offline — no need to run the game —
and can validate any event's coordinates.
