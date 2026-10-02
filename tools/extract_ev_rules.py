# -*- coding: utf-8 -*-
"""EV CG compositing rule extractor: EVINIT.BIN + APPEND11.AAI -> for every event
and every differential combination, the layer list (AGF file, x, y).
Writes the full table to ev_composite_rules.txt next to this script.
"""
import os

import struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_append import parse_aai

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


ALF11 = os.path.join(GAME, 'APPEND11.ALF')
AAI = os.path.join(GAME, 'APPEND11.AAI')

def read(off, size):
    with open(ALF11, 'rb') as f:
        f.seek(off); return f.read(size)

def main():
    arcs, names = parse_aai(AAI)
    # sequence number -> file name (strip the $11$ prefix)
    seq2name = {i: n.replace('$11$', '') for i, (n, a, o, s) in enumerate(names)}
    print('APPEND11 entries:', len(names))

    data = read(0x179D8EDC, 0x12288)
    body = data[0x44:]
    n = len(body)
    rec = None
    records = []
    i = 0
    while i * 4 < n:
        op = struct.unpack('<I', body[i*4:i*4+4])[0]
        if op == 90:
            v = struct.unpack('<I', body[(i+6)*4:(i+7)*4])[0]
            h = struct.unpack('<I', body[(i+4)*4:(i+5)*4])[0]
            if h == 0xEC42:
                if rec: records.append(rec)
                rec = {'ev': v, 'layers': []}
            elif h == 0xEC43:
                rec['diff'] = v
            i += 7
        elif op == 85:
            h = struct.unpack('<I', body[(i+2)*4:(i+3)*4])[0]
            v = struct.unpack('<I', body[(i+4)*4:(i+5)*4])[0]
            rec['layers'].append((h, v))
            i += 5
        elif op in (140, 5, 196):
            i += 3 if op == 140 else (1 if op == 5 else 3)
        else:
            i += 1
    if rec: records.append(rec)

    def resname(v):
        v &= 0xFFFFFFFF
        if (v >> 16) == 0xB00 or (v >> 16) == 0x0B00:
            seq = v & 0xFFFF
            return seq2name.get(seq, 'seq?%d' % seq)
        return hex(v)

    out = []
    out.append('EV CG compositing rules (EVINIT.BIN, %d records)' % len(records))
    out.append('per layer = [refA base, refB diff, refC secondary diff, refD part] + coordinate groups (x1,y1)(x2,y2)')
    out.append('=' * 90)
    for r in records:
        out.append('EV%d diff#%d:' % (r['ev'], r.get('diff', '?')))
        # walk the op85 sequence
        layers = []
        cur = {'refA': None, 'refB': None, 'refC': None, 'refD': None, 'x': [], 'y': []}
        for h, v in r['layers']:
            low = h & 0xFF
            grp = h >> 8
            if grp == 0x18D5:
                if low in (0xAA, 0xAB, 0xAC, 0xAD, 0xA9, 0xAE, 0xAF):
                    cur['refA'] = v
                else:
                    cur['refB'] = v if cur['refB'] is None else cur['refB']
                    # several 18D5Dx slots: keep the first, record the rest as refC
                    if cur.get('refC') is None and cur['refB'] != v:
                        cur['refC'] = v
            elif grp == 0x18D7 and 0xA9 <= low <= 0xB0:
                cur['refD'] = v
            elif grp == 0x18D6:
                cur['x'].append(v)
            elif grp == 0x18D7:
                cur['y'].append(v)
        layers.append(cur)
        # emit
        for L in layers:
            def f(v): return resname(v) if v else '-'
            xs = ','.join(hex(x) for x in L['x'])
            ys = ','.join(hex(y) for y in L['y'])
            out.append('   A=%s B=%s C=%s D=%s   x=[%s] y=[%s]' % (
                f(L['refA']), f(L['refB']), f(L['refC']), f(L['refD']), xs, ys))
        out.append('-' * 60)
    txt = '\n'.join(out)
    outp = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ev_composite_rules.txt')
    open(outp, 'w', encoding='utf-8').write(txt)
    print('written:', outp)
    print(txt[:4000])

if __name__ == '__main__':
    main()
