# -*- coding: utf-8 -*-
"""Locate any file (SC/SP/SN/AGF) in the ALF archives via SYS5INI.BIN index.
Usage: python locate_file.py SC0500.BIN  (prints archive, offset, size)
       python locate_file.py --list CG  (lists all CG-prefixed AGF files)
"""
import struct, sys, os
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


GAME = _find_game_dir()
INI = GAME + r'\SYS5INI.BIN'

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

def read_fixed_utf16(buf, pos, length):
    field = buf[pos:pos+length]; end = length
    for i in range(0, length - 1, 2):
        if field[i] == 0 and field[i+1] == 0: end = i; break
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
        n, pos = read_fixed_utf16(decomp, pos, 0x200)
        arcs.append(n)
    file_count = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
    files = []
    for _ in range(file_count):
        n, pos = read_fixed_utf16(decomp, pos, 0x80)
        arc_id = struct.unpack('<i', decomp[pos:pos+4])[0]; pos += 4
        fno = struct.unpack('<i', decomp[pos:pos+4])[0]; pos += 4
        offset = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
        size = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
        files.append((n, arc_id, fno, offset, size))
    return arcs, files

if __name__ == '__main__':
    arcs, files = parse_index()
    if len(sys.argv) > 1 and sys.argv[1] == '--list':
        pat = sys.argv[2] if len(sys.argv) > 2 else 'CG'
        for n, arc, fno, off, size in files:
            if pat.upper() in n.upper():
                print('%s arc=%s(%d) off=0x%X size=0x%X' % (n, arcs[arc] if arc >= 0 else '?', arc, off, size))
        sys.exit(0)
    if len(sys.argv) < 2:
        print('usage: locate_file.py NAME.BIN | --list PATTERN')
        sys.exit(1)
    q = sys.argv[1].upper()
    for n, arc, fno, off, size in files:
        if n.upper() == q:
            print('%s arc=%s(%d) fno=%d off=0x%X size=0x%X (%d)' % (n, arcs[arc] if arc >= 0 else '?', arc, fno, off, size, size))
            sys.exit(0)
    print('not found:', q)
