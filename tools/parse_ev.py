# -*- coding: utf-8 -*-
"""Parse EV (and ACGF-less AGF) files from APPEND11.ALF using GARbro's
AgfFormat logic: header[0x18] -> type/unpacked/packed -> LZSS sec2 ->
width/height at sec2[0x14]/[0x18]. Also dump the raw 2nd section for
layer-offset analysis. Usage: python parse_ev.py EV126A.AGF"""
import os

import struct, sys

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


ALF = os.path.join(GAME, 'APPEND11.ALF')

def lzss_decompress(data, frame_size=0x1000, frame_fill=0, frame_init_pos=0xFEE, min_match=3):
    out = bytearray(); frame = bytearray([frame_fill]) * frame_size
    pos = 0; n = len(data); frame_pos = frame_init_pos; mask = frame_size - 1
    while pos < n:
        ctl = data[pos]; pos += 1
        for bit in range(8):
            if pos >= n: break
            if ctl & (1 << bit):
                b = data[pos]; pos += 1
                frame[frame_pos & mask] = b; frame_pos += 1; out.append(b)
            else:
                if pos + 1 >= n: break
                lo = data[pos]; hi = data[pos+1]; pos += 2
                off = ((hi & 0xF0) << 4) | lo; cnt = (hi & 0x0F) + min_match
                for _ in range(cnt):
                    v = frame[off & mask]; off += 1
                    frame[frame_pos & mask] = v; frame_pos += 1; out.append(v)
    return bytes(out)

def parse(name, offset, size):
    with open(ALF, 'rb') as f:
        f.seek(offset); data = f.read(size)
    print('==== %s  off=0x%X size=0x%X ====' % (name, offset, size))
    h1 = data[:0x18]
    type_ = struct.unpack('<I', h1[4:8])[0]
    unpacked = struct.unpack('<I', h1[0x0C:0x10])[0]
    packed = struct.unpack('<I', h1[0x14:0x18])[0]
    print('  type=%d unpacked(0x0C)=0x%X(%d) packed(0x14)=0x%X(%d)' % (type_, unpacked, unpacked, packed, packed))
    print('  extra dwords: [0x08]=0x%X [0x10]=0x%X [0x18]=0x%X [0x1C]=0x%X' % (
        struct.unpack('<I', h1[8:12])[0], struct.unpack('<I', h1[0x10:0x14])[0],
        struct.unpack('<I', data[0x18:0x1C])[0], struct.unpack('<I', data[0x1C:0x20])[0]))
    # GARbro: DataOffset = 0x18 + packed; OpenSection reads from current pos (after 0x18)
    body = data[0x18:]
    try:
        if unpacked != packed:
            sec2 = lzss_decompress(body[:packed])
        else:
            sec2 = body[:unpacked]
    except Exception as ex:
        print('  LZSS failed:', ex)
        return
    print('  sec2 len=%d' % len(sec2))
    if len(sec2) >= 0x20:
        h2 = sec2[:0x20]
        print('  sec2 head:', h2.hex())
        d2 = [struct.unpack('<I', h2[i:i+4])[0] for i in range(0, 0x20, 4)]
        print('  sec2 dwords:', ' '.join('%08X' % v for v in d2))
        w = struct.unpack('<I', h2[0x14:0x18])[0]
        h = struct.unpack('<I', h2[0x18:0x1C])[0]
        bpp = struct.unpack('<H', h2[0x1E:0x20])[0]
        print('  -> WIDTH=%d HEIGHT=%d srcbpp=%d' % (w, h, bpp))
        # dump sec2[0x20:0x60] for offset/order info
        print('  sec2[0x20:0x60]:', sec2[0x20:0x60].hex())
        # BMP section after sec2
        bmp_off = 0x18 + packed
        if bmp_off + 8 <= len(data):
            dsize = struct.unpack('<I', data[bmp_off:bmp_off+4])[0]
            psize = struct.unpack('<I', data[bmp_off+4:bmp_off+8])[0]
            print('  BMP sec at 0x%X: data=%d packed=%d' % (bmp_off, dsize, psize))
            print('  BMP head:', data[bmp_off+8:bmp_off+8+0x18].hex())

if __name__ == '__main__':
    import sys as _sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from parse_append import parse_aai
    arcs, names = parse_aai(os.path.join(GAME, 'APPEND11.AAI'))
    by_name = {}
    for n, arc, off, size in names:
        by_name[n.replace('$11$', '')] = (off, size)
    which = _sys.argv[1] if len(_sys.argv) > 1 else 'EV126A.AGF'
    if which in by_name:
        off, size = by_name[which]
        parse(which, off, size)
    else:
        print('unknown:', which)
        print('known EV126:', [k for k in by_name if 'EV126' in k])
