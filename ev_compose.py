# -*- coding: utf-8 -*-
"""
Wayblazer EV CG Composer
========================
Rebuilds event CGs from the game data by replaying the original compositing rules
(base image + differential layers, with coordinates).

Drop this file into the game's main directory (the one holding DATA*.ALF /
APPEND*.ALF / SYS5INI.BIN) and run it.
Requires Python 3.8+ and Pillow (pip install pillow). No game file is modified.

Sources of the compositing data:
  1) Base pack:   SYS5INI.BIN index + DATA1-8.ALF + EVINIT.BIN inside DATA1
  2) Append pack: APPEND11.AAI index + APPEND11.ALF + EVINIT.BIN inside APPEND11
  A rule is one EVINIT.BIN recipe record: base image + differentials @ coordinates.
  Images with the "EVM" prefix are auxiliary and are ignored.

Usage:
    python ev_compose.py                     # list every composable event
    python ev_compose.py 11                  # compose every differential of EV11
    python ev_compose.py 11 2                # compose EV11, diff#2
    python ev_compose.py 126 2               # append-pack EV126, diff#2
    python ev_compose.py --all               # batch-compose everything
    python ev_compose.py --all --workers 8   # same, across 8 processes
    python ev_compose.py 11 --out D:/cg      # custom output directory

Output: by default "<game dir>/EV_output/EV11_diff2_g0.png".

--workers N runs the work across N processes (one task per event, or per differential
recipe for a single event). Each worker loads the indexes and recipe tables itself, so
start-up costs a few seconds; leave it at 1 for a single event on a fast disk.

See docs/ (FORMATS.md, REVERSE_ENGINEERING.md) for the underlying formats.
"""
import os
import sys
import struct

# ---------------- LZSS ----------------
def lzss_decompress(data, frame_size=0x1000, frame_fill=0, frame_init_pos=0xFEE, min_match=3):
    out = bytearray()
    frame = bytearray([frame_fill]) * frame_size
    pos = 0
    n = len(data)
    frame_pos = frame_init_pos
    mask = frame_size - 1
    while pos < n:
        ctl = data[pos]; pos += 1
        for bit in range(8):
            if pos >= n:
                break
            if ctl & (1 << bit):
                b = data[pos]; pos += 1
                frame[frame_pos & mask] = b; frame_pos += 1; out.append(b)
            else:
                if pos + 1 >= n:
                    break
                lo = data[pos]; hi = data[pos + 1]; pos += 2
                off = ((hi & 0xF0) << 4) | lo
                cnt = (hi & 0x0F) + min_match
                for _ in range(cnt):
                    v = frame[off & mask]; off += 1
                    frame[frame_pos & mask] = v; frame_pos += 1; out.append(v)
    return bytes(out)

# ---------------- index parsing ----------------
def read_fixed(buf, pos, length, uni=True):
    field = buf[pos:pos + length]
    end = length
    if uni:
        for i in range(0, length - 1, 2):
            if field[i] == 0 and field[i + 1] == 0:
                end = i; break
        return field[:end].decode('utf-16-le', errors='replace'), pos + length
    for i in range(length):
        if field[i] == 0:
            end = i; break
    return field[:end].decode('ascii', errors='replace'), pos + length

def parse_sys5ini(path):
    """SYS5INI.BIN (S5IC) -> list[(arc_name, name, offset, size)] indexed by seq"""
    with open(path, 'rb') as f:
        d = f.read()
    comp_len = struct.unpack('<I', d[0x224:0x228])[0]
    decomp = lzss_decompress(d[0x228:0x228 + comp_len])
    pos = 0
    arc_count = struct.unpack('<I', decomp[pos:pos + 4])[0]; pos += 4
    arcs = []
    for _ in range(arc_count):
        n, pos = read_fixed(decomp, pos, 0x200)
        arcs.append(n)
    file_count = struct.unpack('<I', decomp[pos:pos + 4])[0]; pos += 4
    out = []
    for _ in range(file_count):
        n, pos = read_fixed(decomp, pos, 0x80)
        arc_id = struct.unpack('<i', decomp[pos:pos + 4])[0]; pos += 4
        _ = struct.unpack('<i', decomp[pos:pos + 4])[0]; pos += 4
        offset = struct.unpack('<I', decomp[pos:pos + 4])[0]; pos += 4
        size = struct.unpack('<I', decomp[pos:pos + 4])[0]; pos += 4
        if n and n != '@':
            out.append((arcs[arc_id] if arc_id >= 0 else '?', n, offset, size))
    return out

def parse_aai(path):
    """APPEND11.AAI (S5AC) -> list[(arc_name, name, offset, size)] indexed by seq"""
    with open(path, 'rb') as f:
        d = f.read()
    comp_len = struct.unpack('<I', d[0x21C:0x220])[0]
    decomp = lzss_decompress(d[0x220:0x220 + comp_len])
    pos = 0
    arc_count = struct.unpack('<I', decomp[pos:pos + 4])[0]; pos += 4
    arcs = []
    for _ in range(arc_count):
        n, pos = read_fixed(decomp, pos, 0x200)
        arcs.append(n)
    file_count = struct.unpack('<I', decomp[pos:pos + 4])[0]; pos += 4
    out = []
    for _ in range(file_count):
        n, pos = read_fixed(decomp, pos, 0x80)
        arc_id = struct.unpack('<i', decomp[pos:pos + 4])[0]; pos += 4
        _ = struct.unpack('<i', decomp[pos:pos + 4])[0]; pos += 4
        offset = struct.unpack('<I', decomp[pos:pos + 4])[0]; pos += 4
        size = struct.unpack('<I', decomp[pos:pos + 4])[0]; pos += 4
        if n and n != '@':
            out.append((arcs[arc_id] if arc_id >= 0 else '?', n.replace('$11$', ''), offset, size))
    return out

# ---------------- EVINIT.BIN recipe table ----------------
def parse_evinit(data):
    body = data[0x44:]
    n = len(body)
    i = 0
    rec = None
    records = []
    while i * 4 < n:
        op = struct.unpack('<I', body[i * 4:i * 4 + 4])[0]
        if op == 90:
            v = struct.unpack('<I', body[(i + 6) * 4:(i + 7) * 4])[0]
            h = struct.unpack('<I', body[(i + 4) * 4:(i + 5) * 4])[0]
            if h == 0xEC42:
                if rec:
                    records.append(rec)
                rec = {'ev': v, 'layers': []}
            elif h == 0xEC43 and rec is not None:
                rec['diff'] = v
            i += 7
        elif op == 85 and rec is not None:
            h = struct.unpack('<I', body[(i + 2) * 4:(i + 3) * 4])[0]
            v = struct.unpack('<I', body[(i + 4) * 4:(i + 5) * 4])[0]
            rec['layers'].append((h, v))
            i += 5
        elif op in (140, 5, 196):
            i += 3 if op == 140 else (1 if op == 5 else 3)
        else:
            i += 1
    if rec:
        records.append(rec)
    return records

# ---------------- EV AGF decoding ----------------
def decode_agf(alf_path, offset, size):
    with open(alf_path, 'rb') as f:
        f.seek(offset)
        data = f.read(size)
    typ = struct.unpack('<I', data[4:8])[0]
    unpacked = struct.unpack('<I', data[12:16])[0]
    packed = struct.unpack('<I', data[20:24])[0]
    body = data[0x18:]
    if unpacked != packed:
        sec2 = lzss_decompress(body[:packed])
    else:
        sec2 = body[:unpacked]
    w = struct.unpack('<I', sec2[0x14:0x18])[0]
    h = struct.unpack('<I', sec2[0x18:0x1C])[0]
    srcbpp = struct.unpack('<H', sec2[0x1E:0x20])[0]
    bmp_off = 0x18 + packed
    _skip = struct.unpack('<I', data[bmp_off:bmp_off + 4])[0]
    dsize = struct.unpack('<I', data[bmp_off + 4:bmp_off + 8])[0]
    psize = struct.unpack('<I', data[bmp_off + 8:bmp_off + 12])[0]
    if dsize != psize:
        px = lzss_decompress(data[bmp_off + 12:bmp_off + 12 + psize])
    else:
        px = data[bmp_off + 12:bmp_off + 12 + dsize]
    if srcbpp <= 8:
        # palette lives in sec2
        pal = sec2[0x20:0x20 + 256 * 3]
        out = bytearray(w * h * 4)
        for i in range(w * h):
            c = px[i]
            out[i * 4] = pal[c * 3]; out[i * 4 + 1] = pal[c * 3 + 1]
            out[i * 4 + 2] = pal[c * 3 + 2]; out[i * 4 + 3] = 255
        return w, h, 'RGBA', bytes(out)
    # pixels are BGR and stored bottom-up -> flip rows and swap R/B
    stride = w * 3
    rgb = bytearray(w * h * 3)
    for y in range(h):
        src_row = (h - 1 - y) * stride
        for x in range(w):
            s = src_row + x * 3
            d = y * stride + x * 3
            rgb[d] = px[s + 2]; rgb[d + 1] = px[s + 1]; rgb[d + 2] = px[s]
    if typ == 1:
        return w, h, 'RGB', bytes(rgb)
    acif_off = bmp_off + 12 + psize
    alpha = None
    if data[acif_off:acif_off + 4] == b'ACIF' and acif_off + 0x24 <= len(data):
        ah = data[acif_off:acif_off + 0x24]
        au = struct.unpack('<I', ah[0x1C:0x20])[0]
        ap = struct.unpack('<I', ah[0x20:0x24])[0]
        if au != ap:
            alpha = lzss_decompress(data[acif_off + 0x24:acif_off + 0x24 + ap])
        else:
            alpha = data[acif_off + 0x24:acif_off + 0x24 + au]
    if alpha is None or len(alpha) < w * h:
        return w, h, 'RGB', bytes(rgb)
    out = bytearray(w * h * 4)
    for i in range(w * h):
        out[i * 4] = rgb[i * 3]; out[i * 4 + 1] = rgb[i * 3 + 1]
        out[i * 4 + 2] = rgb[i * 3 + 2]; out[i * 4 + 3] = alpha[i]
    return w, h, 'RGBA', bytes(out)

# ---------------- compositing ----------------
class Resolver:
    """resource id -> (alf_path, offset, size); the high bits select base vs append index"""
    def __init__(self, base_dir, sys5_table, append_table):
        self.base = base_dir
        self.sys5 = {seq: (arc, n, off, size) for seq, (arc, n, off, size) in enumerate(sys5_table)}
        self.append = {seq: (arc, n, off, size) for seq, (arc, n, off, size) in enumerate(append_table)}
        self._arc_cache = {}

    def _alf(self, arc):
        p = os.path.join(self.base, arc)
        if arc not in self._arc_cache:
            self._arc_cache[arc] = p
        return p

    def resolve(self, ref):
        seq = ref & 0xFFFF
        if (ref >> 16) in (0xB00, 0x0B00):   # append-pack reference
            info = self.append.get(seq)
            tag = 'APPEND'
        else:                                 # base-pack reference
            info = self.sys5.get(seq)
            tag = 'SYS5'
        if not info:
            return None, None, None, None, None
        arc, name, off, size = info
        return self._alf(arc), off, size, tag, name

def compose_ev(records, res, ev, diff=None, outdir='EV_output', quiet=False):
    import PIL.Image as Image
    targets = [r for r in records if r['ev'] == ev and (diff is None or r.get('diff') == diff)]
    if not targets:
        return 0
    total_made = 0
    for r in targets:
        refs = []
        x_by_low = {}
        y_by_low = {}
        for h, v in r['layers']:
            low = h & 0xFF
            grp = h >> 8
            if grp in (0x18D5, 0x18D6, 0x18D7):
                # classify by VALUE: resolves to an EV file name -> resource reference,
                # otherwise treat it as a coordinate according to its slot group
                _p, _o, _s, _t, nm = res.resolve(v)
                if nm and nm.upper().startswith('EV'):
                    refs.append(v)
                elif grp == 0x18D6:
                    x_by_low[low] = v
                elif grp == 0x18D7:
                    y_by_low[low] = v
        if not refs:
            continue
        # pair coordinates by slot: an x slot's low byte is 0x60 above its y slot's
        # (0x18d6xx <-> 0x18d7(xx-0x60))
        x_lows = sorted(x_by_low)
        xs = [x_by_low[low] for low in x_lows]
        ys = [y_by_low.get(low - 0x60) for low in x_lows]  # None = that y slot is absent
        base_v = refs[0]
        # reference -> (path, offset, size, tag, name)
        def resolve_name(v):
            p, off, size, tag, nm = res.resolve(v)
            return p, off, size, tag, nm
        base_info = resolve_name(base_v)
        if base_info[0] is None:
            continue
        base_fn = base_info[4] or os.path.basename(base_info[0])
        layers, cur = [], []
        for v in refs:
            if v == base_v and cur:
                layers.append(cur)
                cur = []
            cur.append(v)
        if cur:
            layers.append(cur)
        # drop base-image placeholders and EVM auxiliary images
        def fname(v):
            _, _, _, _, nm = res.resolve(v)
            return nm
        layers = [[v for v in L if v != base_v and 'EVM' not in (fname(v) or '').upper()]
                  for L in layers]
        layers = [L for L in layers if L]
        xi = yi = 0
        info = []
        for L in layers:
            coords = []
            for _ in L:
                x = xs[xi] if xi < len(xs) else 0
                xi += 1
                # absent y slot -> 0 (e.g. the tall EV13 BA layer anchors at y=0)
                y = ys[yi] if yi < len(ys) and ys[yi] is not None else 0
                yi += 1
                coords.append((x, y))
            info.append((L, coords))

        def load(v):
            p, off, size, tag, nm = res.resolve(v)
            if not p:
                return None
            w, h, mode, raw = decode_agf(p, off, size)
            im = Image.frombytes('RGBA' if mode == 'RGBA' else 'RGB', (w, h), raw)
            if mode == 'RGB':
                im = im.convert('RGBA')
            return im

        base_im = load(base_v)
        if base_im is None:
            continue
        os.makedirs(outdir, exist_ok=True)
        if not layers:
            # single-image event (no differential): emit the base image as-is
            outp = os.path.join(outdir, 'EV%d_diff%s_g0.png' % (ev, r.get('diff', '?')))
            base_im.convert('RGB').save(outp)
            total_made += 1
            if not quiet:
                print('    EV%d diff#%s: single image %s' % (ev, r.get('diff', '?'), base_fn))
                print('    -> %s' % outp)
            continue
        for gi, (L, coords) in enumerate(info):
            canvas = base_im.convert('RGBA')
            for k, v in enumerate(L):
                p, off, size, tag, nm = res.resolve(v)
                im = load(v)
                if im is None:
                    continue
                x, y = coords[k] if k < len(coords) else (0, 0)
                canvas.alpha_composite(im, (x, y))
                if not quiet:
                    print('    EV%d diff#%s layer%d: %s @ (%d,%d) [%s]' % (
                        ev, r.get('diff', '?'), gi, nm, x, y, tag))
            outp = os.path.join(outdir, 'EV%d_diff%s_g%d.png' % (ev, r.get('diff', '?'), gi))
            canvas.convert('RGB').save(outp)
            total_made += 1
            if not quiet:
                print('    -> %s' % outp)
    return total_made

# ---------------- multiprocessing worker ----------------
_W = {}

def _init_worker(base_dir, sys5_table, append_table, evinit_main, evinit_app):
    _W['res'] = Resolver(base_dir, sys5_table, append_table)
    _W['main'] = parse_evinit(evinit_main)
    _W['app'] = parse_evinit(evinit_app)

def _work_task(task):
    ev, diff, outdir = task
    recs = _W['main'] if any(r['ev'] == ev for r in _W['main']) else _W['app']
    return ev, diff, compose_ev(recs, _W['res'], ev, diff, outdir, quiet=True)

# ---------------- entry point ----------------
def main():
    base = os.path.dirname(os.path.abspath(__file__))
    outdir = os.path.join(base, 'EV_output')
    workers = 1
    args = []
    raw = sys.argv[1:]
    i = 0
    while i < len(raw):
        if raw[i] == '--out' and i + 1 < len(raw):
            outdir = raw[i + 1]; i += 2
        elif raw[i] == '--workers' and i + 1 < len(raw):
            try:
                workers = max(1, int(raw[i + 1]))
            except ValueError:
                workers = 1
            i += 2
        else:
            args.append(raw[i]); i += 1

    need = ['SYS5INI.BIN', 'DATA1.ALF', 'APPEND11.ALF', 'APPEND11.AAI']
    missing = [f for f in need if not os.path.exists(os.path.join(base, f))]
    if missing:
        print('error: missing file(s): %s' % ', '.join(missing))
        print('Put this script in the game main directory (the one holding '
              'DATA*.ALF / APPEND*.ALF / SYS5INI.BIN) and run it again.')
        sys.exit(1)
    try:
        import PIL.Image
    except ImportError:
        print('error: Pillow is required. Run: python -m pip install pillow')
        sys.exit(1)

    print('Reading SYS5INI.BIN (base index) ...')
    sys5 = parse_sys5ini(os.path.join(base, 'SYS5INI.BIN'))
    print('  files: %d' % len(sys5))
    print('Reading APPEND11.AAI (append index) ...')
    app = parse_aai(os.path.join(base, 'APPEND11.AAI'))
    print('  files: %d' % len(app))

    # the two EVINIT tables
    with open(os.path.join(base, 'DATA1.ALF'), 'rb') as f:
        f.seek(0x518FEE78)
        evinit_main = f.read(0x19514)
    with open(os.path.join(base, 'APPEND11.ALF'), 'rb') as f:
        f.seek(0x179D8EDC)
        evinit_app = f.read(0x12288)
    recs_main = parse_evinit(evinit_main)
    recs_app = parse_evinit(evinit_app)
    all_recs = recs_main + recs_app
    evs = sorted({r['ev'] for r in all_recs})
    print('EVINIT records: base %d + append %d = %d, events: %d' % (
        len(recs_main), len(recs_app), len(all_recs), len(evs)))

    def recs_for(ev):
        return recs_main if any(r['ev'] == ev for r in recs_main) else recs_app

    def run(tasks):
        """tasks = [(ev, diff_or_None), ...]; returns the number of images written"""
        total = 0
        if workers > 1 and len(tasks) > 1:
            import multiprocessing
            # each worker builds its own Resolver and recipe tables
            ctx = multiprocessing.get_context('spawn')
            with ctx.Pool(workers, initializer=_init_worker,
                          initargs=(base, sys5, app, evinit_main, evinit_app)) as pool:
                done = 0
                for ev, diff, made in pool.imap_unordered(_work_task,
                                                          [(e, d, outdir) for e, d in tasks]):
                    total += made
                    done += 1
                    print('  [%d/%d] EV%d%s: %d images' % (
                        done, len(tasks), ev, '' if diff is None else ' diff#%d' % diff, made),
                        flush=True)
        else:
            res = Resolver(base, sys5, app)
            for ev, diff in tasks:
                made = compose_ev(recs_for(ev), res, ev, diff, outdir)
                total += made
                if len(tasks) > 1:
                    print('  EV%d%s: %d images' % (
                        ev, '' if diff is None else ' diff#%d' % diff, made), flush=True)
        return total

    if args and args[0].lower() == '--all':
        total = run([(ev, None) for ev in evs])
        print('Done: %d combinations composed, output in %s%s' % (
            total, outdir, '' if workers == 1 else ' (workers=%d)' % workers))
        return
    if not args:
        print('\nAvailable events:')
        for ev in evs:
            recs = recs_for(ev)
            diffs = sorted({r.get('diff') for r in recs if r['ev'] == ev})
            tag = 'base' if recs is recs_main else 'append'
            print('  EV%-4d (%s) diff: %s' % (ev, tag, diffs))
        print('\nUsage:')
        print('  python ev_compose.py <EV id> [diff id] [--out DIR] [--workers N]')
        print('  python ev_compose.py --all [--workers N]')
        return
    try:
        ev = int(args[0])
    except ValueError:
        print('invalid EV id: %s' % args[0])
        sys.exit(1)
    diff = int(args[1]) if len(args) > 1 else None
    recs = recs_for(ev)
    if diff is not None:
        tasks = [(ev, diff)]
    elif workers > 1:
        diffs = sorted({r.get('diff') for r in recs if r['ev'] == ev})
        tasks = [(ev, d) for d in diffs] or [(ev, None)]
    else:
        tasks = [(ev, None)]
    n = run(tasks)
    if n == 0:
        print('no record found for EV%d%s' % (ev, (' diff#' + str(diff)) if diff else ''))
        sys.exit(1)
    print('Done: %d combinations composed, output in %s' % (n, outdir))

if __name__ == '__main__':
    main()
