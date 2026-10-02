# -*- coding: utf-8 -*-
"""Full-structure AGF dump + naming convention analysis."""
import struct, re
from collections import defaultdict, Counter
import os

def _find_game_dir():
    """Locate the game main directory (the one holding APPEND11.ALF).
    Override with the WAYBLAZER_DIR environment variable."""
    cands = []
    if os.environ.get('WAYBLAZER_DIR'):
        cands.append(os.environ['WAYBLAZER_DIR'])
    here = os.path.dirname(os.path.abspath(__file__))
    cands += [here,
              os.path.join(here, '..', '..', 'WayblazerCHSR18'),
              os.path.join(here, '..', 'WayblazerCHSR18'),
              os.path.join(here, '..', '..', '..', 'WayblazerCHSR18'),
              os.path.join(os.path.expanduser('~'), 'WayblazerCHSR18')]
    for c in cands:
        if os.path.exists(os.path.join(c, 'APPEND11.ALF')):
            return os.path.abspath(c)
    return os.path.abspath(cands[-1])

GAME = _find_game_dir()


ALF = os.path.join(GAME, 'DATA1.ALF')
INI = os.path.join(GAME, 'SYS5INI.BIN')

def lzss_decompress(data, frame_size=0x1000, frame_fill=0, frame_init_pos=0xFEE, min_match=3):
    out = bytearray()
    frame = bytearray([frame_fill]) * frame_size
    frame_pos = frame_init_pos
    mask = frame_size - 1
    pos = 0
    n = len(data)
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
                lo = data[pos]; hi = data[pos+1]; pos += 2
                off = ((hi & 0xF0) << 4) | lo
                cnt = (hi & 0x0F) + min_match
                for _ in range(cnt):
                    v = frame[off & mask]; off += 1
                    frame[frame_pos & mask] = v; frame_pos += 1; out.append(v)
    return bytes(out)

def read_fixed_utf16(buf, pos, length):
    field = buf[pos:pos+length]
    end = length
    for i in range(0, length - 1, 2):
        if field[i] == 0 and field[i+1] == 0:
            end = i; break
    return field[:end].decode('utf-16-le', errors='replace'), pos + length

def parse_index():
    raw = open(INI, 'rb').read()
    off = 0x224
    comp_len = struct.unpack('<I', raw[off:off+4])[0]
    decomp = lzss_decompress(raw[off+4 : off+4+comp_len])
    pos = 0
    arc_count = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
    arcs = []
    for _ in range(arc_count):
        n, pos = read_fixed_utf16(decomp, pos, 0x200); arcs.append(n)
    file_count = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
    entries = []
    for _ in range(file_count):
        n, pos = read_fixed_utf16(decomp, pos, 0x80)
        arc_id = struct.unpack('<i', decomp[pos:pos+4])[0]; pos += 4
        file_no = struct.unpack('<i', decomp[pos:pos+4])[0]; pos += 4
        offset = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
        size = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
        entries.append((n, arc_id, file_no, offset, size))
    return arcs, entries

NAME_RE = re.compile(r'^([A-Z]{2})(\d{3})([A-Z]+)$')

def read_agf(alf_path, offset, size):
    with open(alf_path, 'rb') as f:
        f.seek(offset); data = f.read(size)
    typ = struct.unpack('<I', data[4:8])[0]
    unpacked = struct.unpack('<I', data[12:16])[0]
    packed = struct.unpack('<I', data[20:24])[0]
    body = data[0x18:]
    if unpacked != packed:
        sec2 = lzss_decompress(body[:packed])
    else:
        sec2 = body[:unpacked]
    h2 = sec2[:0x20]
    width  = struct.unpack('<I', h2[0x14:0x18])[0]
    height = struct.unpack('<I', h2[0x18:0x1C])[0]
    srcbpp = struct.unpack('<H', h2[0x1E:0x20])[0]
    return dict(typ=typ, unpacked=unpacked, packed=packed, sec2=sec2,
                width=width, height=height, srcbpp=srcbpp)

if __name__ == '__main__':
    arcs, entries = parse_index()
    print('arcs=%s total_files=%d' % (arcs, len(entries)))

    agfs = [e for e in entries if e[0].upper().endswith('.AGF')]
    print('AGF files: %d\n' % len(agfs))

    # --- naming analysis ---
    prefix_cnt = Counter()
    prefix_nums = defaultdict(set)
    bad = []
    for name, *_ in agfs:
        stem = name[:-4]
        m = NAME_RE.match(stem)
        if not m:
            bad.append(name); continue
        p, num, suf = m.groups()
        prefix_cnt[p] += 1
        prefix_nums[p].add(num)
    print('=== AGF filename prefixes ===')
    for p, c in prefix_cnt.most_common():
        nums = sorted(prefix_nums[p])
        print('  %-4s %5d files, %d numbers: %s' % (p, c, len(nums), nums[:12]))
    if bad:
        print('  non-matching names:', bad[:20])

    # suffix letters used per prefix
    print('\n=== suffix (differential marker) letters ===')
    for p in sorted(prefix_cnt):
        sufs = Counter()
        for name, *_ in agfs:
            stem = name[:-4]
            m = NAME_RE.match(stem)
            if m and m.group(1) == p:
                sufs[m.group(3)] += 1
        top = sufs.most_common(20)
        print('  %s: %d distinct suffixes, top: %s' % (p, len(sufs), top))

    # --- full dump for a few representative files ---
    print('\n' + '=' * 70)
    print('FULL STRUCTURE DUMP')
    want = ['CS009AAI.AGF', 'CA009AAI.AGF', 'CS009AAD.AGF', 'BG021AA.AGF', 'AE050AA.AGF']
    for e in agfs:
        name = e[0]
        if name in want:
            _, arc_id, _, offset, size = e
            info = read_agf(ALF, offset, size)
            print('=' * 70)
            print('%s  arc=%s off=0x%X size=0x%X  type=%d %dx%d srcbpp=%d  sec2_unpacked=%d packed=%d'
                  % (name, arcs[arc_id], offset, size, info['typ'], info['width'],
                     info['height'], info['srcbpp'], info['unpacked'], info['packed']))
            sec2 = info['sec2']
            print('  sec2[0x00:0x20] = ' + ' '.join('%02X' % c for c in sec2[:0x20]))
            print('  sec2[0x20:0x60] = ' + ' '.join('%02X' % c for c in sec2[0x20:0x60]))
            # BMP data section (3rd): read int32 data_size, int32 packed_size
            with open(ALF, 'rb') as f:
                f.seek(offset)
                raw = f.read(size)
            bmp_off = 0x18 + info['packed']
            if bmp_off + 8 <= len(raw):
                dsize = struct.unpack('<I', raw[bmp_off:bmp_off+4])[0]
                psize = struct.unpack('<I', raw[bmp_off+4:bmp_off+8])[0]
                print('  BMP sec: data_size=%d packed_size=%d' % (dsize, psize))
                if dsize != psize:
                    bmp = lzss_decompress(raw[bmp_off+8 : bmp_off+8+psize])
                else:
                    bmp = raw[bmp_off+8 : bmp_off+8+dsize]
                print('  BMP head[0:0x20] = ' + ' '.join('%02X' % c for c in bmp[:0x20]))
            # ACIF alpha header after BMP
            alpha_off = bmp_off + 8 + psize
            if alpha_off + 0x24 <= len(raw):
                ah = raw[alpha_off:alpha_off+0x24]
                print('  ACIF head = ' + ' '.join('%02X' % c for c in ah))
