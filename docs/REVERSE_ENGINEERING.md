# Reverse-Engineering Method and Structure Map

This document records **how** the compositing rules used by this project were obtained,
along with the engine-side structure map, as a reference for porting to other System5
titles or for further research.

> Note: everything below is a **structural description** of the target binary
> (addresses, field offsets, data flow). No game code itself is reproduced.

---

## 1. Analysis Method (static only)

No debugger was used and the game never had to be run. The techniques applied:

| Technique | Purpose | Example |
|---|---|---|
| **Error-string xrefs** | Walk backwards from a visible message to its function | `"描画元テクスチャが作成されていません"` → the texture-draw function |
| **Data-structure cross-referencing** | Combine how one offset is used across several functions to infer field meanings | `obj+0x808` behaves as a map header in the find / iterate / insert functions |
| **Thunk following** | Resolve dispatch-table entries to real function bodies | `E9 rel32` jumps in the opcode dispatch table |
| **Call-site scanning** | Find who calls a key function | Scanning `E8 rel32` to locate every sprite-operation entry point |
| **Sequence-number continuity** | Infer how resources are encoded | References increase monotonically → the low bits are an index-table sequence number |
| **Pixel consistency** | Verify geometric parameters | Differential's top-left colour == base colour at the anchor |

Tooling: Ghidra (decompilation), capstone + pefile (byte-level scanning), GARbro sources
(format cross-checking).

---

## 2. Script Virtual Machine (SYS5502)

CG presentation is script-driven. Script format:

```
0x00  16 bytes  "SYS5502 "
0x10  int32     version
0x14~0x24       sizes of the various variable arrays
0x28  extra table size
0x2C  3 × (count, offset)
0x44  instruction stream
```

**Instruction**: `[opcode:int32][operands × N, each 8 bytes = (type, value)]`

**Operand types**:

| Type | Meaning |
|---|---|
| 0 | Immediate |
| 1 | Signed integer |
| 2 | String (index) |
| 3 | **Hashed variable** (looked up in the variable table and decoded) |
| 4 / 5 | Float array / string array |
| 9 / 10 / 11 / 12 | Script-local int / float / string / array |

**Dispatch**: for opcode < 0x400 a **dispatch table** (embedded in the main object at
`+0xb8114`, 1024 entries) jumps to the handler; the cursor then advances by `size*4`.

`tools/opcode_map.json` holds the complete opcode → handler mapping for this title
(574 entries), and `tools/disasm_sc.py` disassembles any script with it.

---

## 3. Main Object Structure Map

The script interpreter, layer tables, textures and render state all live in one large
object (shown as `param_1` in decompilation, i.e. C++ `this`). Known fields:

### 3.1 Script engine area

| Offset | Meaning | Evidence |
|---|---|---|
| `+0x701A4` | Current script layer (scripts nest; layers indexed by `×0x78`) | Every script field is indexed by it |
| `+0x701B8` | Script data buffer pointer | Written by the loader after allocation |
| `+0x701BC` | Instruction cursor | Operand reads are positioned from it |
| `+0x7012C` | Hashed-variable table | Type-3 operands are looked up here |
| `+0x716BC` | Variable codec key | Used by every hashed-variable read/write |
| `+0x701D8` / `+0x701DC` | Local int / float arrays | Allocated by the loader from header counts |
| `+0x701E0` | Local string array (24 bytes per entry) | As above |
| `+0x701F4` | depth | Error string `"Depth が不正です"` |
| `+0x70218` | Current instruction length | Used to advance the cursor after dispatch |

### 3.2 Object-table area

| Offset | Meaning |
|---|---|
| `+0x808` | **Layer (sprite) table**: key-ordered map structure |
| `+0x818` | Surface table |
| `+0x828` | Polygon table |
| `+0x830` / `+0x834` | Special layer key ranges (extra checks during drawing) |

### 3.3 Render and texture area

| Offset | Meaning |
|---|---|
| `+0xB40` | Render device object (polymorphic interface) |
| `+0xB4C … +0xB5C` | **4 blend-state slots** (selected by argument when drawing) |
| `+0xCCCC` | **Texture slot table** (indexed by texture number when drawing) |
| `+0xCD5C` / `+0xCD60` | Full-screen surface objects (clear / background) |
| `+0xDC6C` | Current effect mode |
| `+0xDC88` / `+0xDC90` | Layer dirty flags (set when a layer changes) |
| `+0xDCB0` | Scene transform matrix |
| `+0xDDB8` | Render mode (online / offline) |

### 3.4 System area

| Offset | Meaning |
|---|---|
| `+0xBE684` | Version marker (`"S5"` / `"S4"`) |
| `+0xDDD8C` | System / registry interface object |

---

## 4. Layer (Sprite) Structure

Layers are kept in a key-value map; each value is a structure of roughly **768 bytes**:

| Offset | Field |
|---|---|
| `+0x00` | Flags: bit0 exists, bit1 visible, bit2 uses the animation matrix |
| `+0x04` | Texture slot number |
| `+0x08` | Source rectangle (left, top, right, bottom) |
| `+0x18` | Size (width, height) |
| `+0x20` | Size auxiliary parameters |
| `+0x24` | Position (x, y) |
| `+0x2C` | Alpha |
| `+0x30` ~ `+0x58` | Several x / y pairs (animation start and target values, used for tweening) |
| `+0x60` / `+0x64` | ARGB colour |
| `+0x68` | Matrix enable flag |
| `+0x70` ~ | Identity matrix |
| `+0xB0` / `+0x1B0` / `+0x260` / `+0x2A0` | Several 4×4 transform matrices (scale, rotate, translate) |

The script-level drawing instructions (§5) write into exactly these fields.

---

## 5. Drawing Instructions and Engine Calls

| Opcode | Operands | Semantics |
|---|---|---|
| `514` | layer, x, y, alpha, colour | Set position + ARGB + visible |
| `515` | layer, x, y, ARGB | Set position + colour |
| `544` | layer, x, y, f1, f2, f3 | Set position + transform matrix |
| `542` | same as 544, arguments are percentages (divided by 100) | Set position + scale |
| `537` | layer, x, y, alpha | Set position + alpha directly |
| `535` | layer, w, h, ? | Set size |
| `536` / `538` | layer, variable ×3 | Read size / position + alpha |
| `552` | flag, layer, variable ×3 | Read matrix translation |
| `503` | object, mode | Release layer / surface |

---

## 6. Render Pipeline

```
script drawing instructions
      ↓
layer field writes (position / colour / matrix) → dirty flag set
      ↓
per-frame render loop: merge the three tables — layers / surfaces / polygons — in key order
      ↓
for each visible layer: copy the structure → build vertices → call draw
      ↓
draw function (DrawTexture): fetch texture by "texture slot number",
                             pick one of 4 blend states by argument → submit
```

This project's offline compositing **reproduces only the data-level compositing rules**
(which images, placed where, in what order). Blend states and real-time animation are out
of scope — for static finished images both paths agree.

---

## 7. Key Function Addresses (this title)

| Address | Role |
|---|---|
| `0x432A70` | Script interpreter main loop (message pump + per-instruction interpretation) |
| `0x467900` / `0x466BF0` | Integer / float operand readers |
| `0x464B40` / `0x465850` | Variable write / read |
| `0x43A1A0` | Script loader |
| `0x4D7720` / `0x4CCB40` | Layer lookup (lazy creation) / fetch |
| `0x4F4AE0` | Hash → layer node |
| `0x4E6400` | Scene render loop |
| `0x4EA190` | Draw a single layer |
| `0x4DAF90` | Texture draw (DrawTexture) |
| `0x4D2C80` / `0x4D1F20` | Vertex construction |
| `0x425920` / `0x47CF50` | Image file search / open |

> These addresses correspond to the build used here (Chinese patch 1.04.0020). Other
> builds may differ — relocate them with the methods in §1.

---

## 8. Reproduction Steps

```
 1. Decompile the interpreter main loop → get to know the main object
 2. Decompile operand readers / variable read-write → understand the script variable system
 3. Decompile layer lookup / fetch → recover the layer structure
 4. Decompile the render loop and draw function → understand the draw pipeline
 5. Locate the drawing-instruction handlers → build the script ↔ engine mapping
 6. Parse the index files → file name ↔ sequence number
 7. Parse the compositing recipe table (EVINIT) → layers and coordinates
 8. Decode resource references (FORMATS.md §3)
 9. Decode event images (FORMATS.md §4)
10. Compose and verify with the pixel anchor test (FORMATS.md §5)
```

### Ghidra headless notes

When batch-decompiling in an environment where the user profile directory is not
writable (containers, restricted setups), redirect it:

```bash
# Windows
set APPDATA=D:\tmp\ghidra_user
set JAVA_HOME=<path to your JDK>
analyzeHeadless.bat <project dir> <project name> -process AGE.EXE -noanalysis \
    -scriptPath <script dir> -postScript DecompileXxx.java
```

(`analyzeHeadless` writes `%APPDATA%\ghidra\...\java_home.save`, so a non-writable
profile must be redirected, and `JAVA_HOME` must point at a JDK.)

---

## 9. Details Still Unconfirmed

The following are inferred but were not verified at runtime (they do not affect offline
compositing results):

1. **Layer draw order**: assumed to be ascending layer key (map iteration order); script
   execution order is the alternative.
2. **Blend-state slots**: four exist for certain, but their individual parameters
   (plain alpha blend, additive blend, …) were not confirmed one by one.
3. **Runtime variable table contents**: the codec is confirmed (rotate-XOR), but no
   runtime dump was compared against it.
4. **When texture slots are assigned**: drawing reads the slot by number, confirmed, but
   the exact code that binds a decoded image to a slot was not pinpointed (presumably the
   engine-level resource loading path).

To settle these, break at the draw function in a debugger and dump the texture slot table
and blend-state parameters.
