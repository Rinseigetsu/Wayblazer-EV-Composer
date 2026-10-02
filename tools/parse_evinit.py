# -*- coding: utf-8 -*-
"""Parse EVINIT.BIN: EV -> layer table (agf-ref hash, x, y) per diff combo.
Records are op90(EC42, EV) + op90(EC43, diff#) + op85 sets + op140 jump."""
import struct, re
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


ALF = os.path.join(GAME, 'APPEND11.ALF')

def read(off, size):
    with open(ALF, 'rb') as f:
        f.seek(off); return f.read(size)

def main():
    data = read(0x179D8EDC, 0x12288)
    body = data[0x44:]
    n = len(body)
    # walk records: op90(size7) op90(size7) op86 op160 ... op85* op140/op5
    i = 0
    rec = None
    records = []
    while i * 4 < n:
        op = struct.unpack('<I', body[i*4:i*4+4])[0]
        if op == 90:  # op90 (9:0x0) (3:HASH) (0:VAL)
            v = struct.unpack('<I', body[(i+6)*4:(i+7)*4])[0]   # operand3 value
            h = struct.unpack('<I', body[(i+4)*4:(i+5)*4])[0]   # operand2 value
            if h == 0xEC42:
                if rec: records.append(rec)
                rec = {'ev': v, 'layers': []}
            elif h == 0xEC43:
                rec['diff'] = v
            i += 7
        elif op == 85:  # op85 (3:HASH) (0:VAL)
            h = struct.unpack('<I', body[(i+2)*4:(i+3)*4])[0]
            v = struct.unpack('<I', body[(i+4)*4:(i+5)*4])[0]
            rec['layers'].append((h, v))
            i += 5
        elif op == 140 or op == 5 or op == 196:
            i += 3 if op == 140 else (1 if op == 5 else 3)
        else:
            i += 1
    if rec: records.append(rec)
    print('EV records: %d' % len(records))
    # group by EV
    from collections import OrderedDict
    evs = OrderedDict()
    for r in records:
        evs.setdefault(r['ev'], []).append(r)
    for ev, lst in evs.items():
        print('=== EV%d (%d differential combinations) ===' % (ev, len(lst)))
        for r in lst:
            # layers: group 18D5xx (ref), 18D6xx (x), 18D7xx (y)
            refs = {}
            for h, v in r['layers']:
                grp = h >> 8
                if grp == 0x18D5:
                    refs.setdefault('ref', []).append(v)
                elif grp == 0x18D6:
                    refs.setdefault('x', []).append(v)
                elif grp == 0x18D7:
                    refs.setdefault('y', []).append(v)
                elif grp == 0x18D5A or grp == 0x18D5B or grp == 0x18D5C:
                    refs.setdefault('ref2', []).append(v)
            print('  diff#%d: refs=%s x=%s y=%s' % (r.get('diff','?'),
                  [hex(v) for v in refs.get('ref', [])],
                  [hex(v) for v in refs.get('x', [])],
                  [hex(v) for v in refs.get('y', [])]))

if __name__ == '__main__':
    main()
