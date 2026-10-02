# -*- coding: utf-8 -*-
"""Parse APPENDxx.AAI (S5AC index) with fixed-length fields; list EV files
and dump their AGF headers. Usage: python parse_append.py"""
import os

import struct, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_agf import lzss_decompress

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


def read_fixed(buf, pos, length, uni=True):
    field = buf[pos:pos+length]
    end = length
    if uni:
        for i in range(0, length-1, 2):
            if field[i] == 0 and field[i+1] == 0:
                end = i; break
        return field[:end].decode('utf-16-le', errors='replace'), pos + length
    for i in range(length):
        if field[i] == 0:
            end = i; break
    return field[:end].decode('ascii', errors='replace'), pos + length

def parse_aai(path, off=0x21C):
    d = open(path, 'rb').read()
    comp_len = struct.unpack('<I', d[off:off+4])[0]
    decomp = lzss_decompress(d[off+4:off+4+comp_len])
    pos = 0
    arc_count = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
    arcs = []
    for _ in range(arc_count):
        n, pos = read_fixed(decomp, pos, 0x200); arcs.append(n)
    file_count = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
    names = []
    for _ in range(file_count):
        n, pos = read_fixed(decomp, pos, 0x80)
        arc_id = struct.unpack('<i', decomp[pos:pos+4])[0]; pos += 4
        fno = struct.unpack('<i', decomp[pos:pos+4])[0]; pos += 4
        offset = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
        size = struct.unpack('<I', decomp[pos:pos+4])[0]; pos += 4
        if n and n != '@':
            names.append((n, arc_id, offset, size))
    return arcs, names

def read_agf_dims(alf, offset, size):
    with open(alf, 'rb') as f:
        f.seek(offset); data = f.read(min(size, 0x40))
    if len(data) < 0x24:
        return None
    is_acgf = data[:4] == b'ACGF'
    is_ev_variant = (data[:4] == bytes(4)
                     and struct.unpack('<I', data[4:8])[0] in (1, 2))
    if is_acgf or is_ev_variant:
        typ = struct.unpack('<I', data[4:8])[0]
        unpacked = struct.unpack('<I', data[12:16])[0]
        packed = struct.unpack('<I', data[20:24])[0]
        body = data[0x18:]
        try:
            if unpacked != packed and packed <= len(body):
                sec2 = lzss_decompress(body[:packed])
            else:
                sec2 = body[:unpacked]
            if len(sec2) < 0x20: return (typ, 0, 0, 0)
            w = struct.unpack('<I', sec2[0x14:0x18])[0]
            h = struct.unpack('<I', sec2[0x18:0x1C])[0]
            return (typ, w, h, 0)
        except Exception:
            return (typ, 0, 0, 0)
    return None  # not an AGF image

if __name__ == '__main__':
    path = os.path.join(GAME, 'APPEND11.AAI')
    alf  = os.path.join(GAME, 'APPEND11.ALF')
    arcs, names = parse_aai(path)
    print('arcs:', arcs, 'entries:', len(names))
    ev = [x for x in names if x[0].startswith('$11$EV')]
    print('EV entries:', len(ev))
    # group by base number
    bases = collections.defaultdict(list)
    import re
    for n, arc, off, size in ev:
        m = re.match(r'^\$11\$EV(\d+)(.*?)\.AGF$', n)
        if m:
            bases[m.group(1)].append((n, off, size))
    for num in sorted(bases, key=int):
        lst = bases[num]
        plain = [x for x in lst if '_' not in x[0]]
        suff  = [x for x in lst if '_' in x[0]]
        print('EV%s: base=%s diffs=%s' % (num, [x[0].replace('$11$','') for x in plain], len(suff)))
    # dims for EV126
    print()
    print('=== EV126 sizes ===')
    for n, arc, off, size in ev:
        if 'EV126' in n:
            dims = read_agf_dims(alf, off, size)
            print('  %-18s off=0x%X size=0x%X dims=%s' % (n.replace('$11$',''), off, size, dims))
