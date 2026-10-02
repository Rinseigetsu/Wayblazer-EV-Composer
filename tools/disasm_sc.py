# -*- coding: utf-8 -*-
"""Generalized SYS5502 disassembler for SC/SP/SN/SG scripts.
Looks for image-compositing opcodes (hash operands + coordinates)."""
import os

import pefile, struct, json
from collections import Counter
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

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


EXE = os.path.join(GAME, 'AGE.EXE')
ALF = os.path.join(GAME, 'DATA1.ALF')
ALF11 = os.path.join(GAME, 'APPEND11.ALF')
opmap = {int(k): int(v, 16) for k, v in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'opcode_map.json'))).items()}

pe = pefile.PE(EXE)
base = pe.OPTIONAL_HEADER.ImageBase
raw = open(EXE, 'rb').read()
md = Cs(CS_ARCH_X86, CS_MODE_32)

def rva_to_off(rva):
    for s in pe.sections:
        lo = s.VirtualAddress; hi = lo + max(s.Misc_VirtualSize, s.SizeOfRawData)
        if lo <= rva < hi:
            return s.PointerToRawData + (rva - lo)
    return None

def follow(va):
    off = rva_to_off(va - base)
    if off is None: return va
    b = raw[off:off+5]
    if b[0] == 0xE9:
        rel = struct.unpack('<i', b[1:5])[0]
        return va + 5 + rel
    return va

def get_size(real_va):
    off = rva_to_off(real_va - base)
    if off is None: return None
    code = raw[off:off+80]
    for ins in md.disasm(code, real_va):
        if ins.mnemonic == 'mov' and '0x70218' in ins.op_str:
            toks = ins.op_str.replace(',', ' ').split()
            for t in toks:
                if t.startswith('0x') or t.lstrip('-').isdigit():
                    try:
                        v = int(t, 0)
                        if 0 < v < 0x100:
                            return v
                    except: pass
    return None

sizes = {}
for op in sorted(opmap):
    real = follow(opmap[op])
    s = get_size(real)
    sizes[op] = (real, s)

def read(off, size, alf=ALF):
    with open(alf, 'rb') as f:
        f.seek(off); return f.read(size)

def iw(body, i):
    if (i+1)*4 > len(body): return None
    return struct.unpack('<I', body[i*4:i*4+4])[0]

def sw(v):
    return v - (1<<32) if v >= 1<<31 else v

def disasm(name, offset, size, start=0x44, maxinstr=200000, only_hash=False, alf=ALF):
    data = read(offset, size, alf)
    body = data[start:]
    print("="*78)
    print("%s  size=%d  body=%d bytes" % (name, size, len(body)))
    opcount = Counter()
    hash_ops = Counter()
    pc = 0
    n = 0
    bad = 0
    while pc*4 < len(body) and n < maxinstr:
        op = iw(body, pc)
        if op is None: break
        if op < 0x400 and op in sizes:
            real, s = sizes[op]
            s = s if s else 1
            opcount[op] += 1
            nop = (s - 1)//2 if s >= 3 else 0
            ops = []
            for k in range(nop):
                t = iw(body, pc+1+k*2)
                v = iw(body, pc+2+k*2)
                if t is None: break
                ops.append((t, v))
            # detect hash operands (type 3) or big hash-like values
            has_hash = any(t == 3 or (v >> 24) == 0x17 for t, v in ops)
            if has_hash:
                hash_ops[op] += 1
            if has_hash or (not only_hash and n < 80):
                tag = '  <== HASH' if has_hash else ''
                ops_s = ' '.join('(%d:0x%X)' % (t, v) for t, v in ops)
                print("[%6d] op%-4d size=%-2d %s%s" % (pc, op, s, ops_s, tag))
            pc += s
            n += 1
        else:
            bad += 1
            if bad < 20:
                print("[%6d] op%-4d (UNKNOWN) val=0x%X" % (pc, op, op))
            pc += 1
            n += 1
    print("\n--- top opcodes ---")
    for op, c in opcount.most_common(30):
        print("   op%-4d x%d" % (op, c))
    print("\n--- opcodes with HASH (type3/0x17xxxxxx) operands ---")
    for op, c in hash_ops.most_common(40):
        print("   op%-4d x%d" % (op, c))
    print("bad=%d total_instructions=%d\n" % (bad, n))

if __name__ == '__main__':
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else 'SC0680'
    targets = {
        'SC0680': ("SC0680.BIN", 0x17AB3A94, 0x20E84),
        'SC0010': ("SC0010.BIN", 0x08189482, 0x1D4CD4),
        'SC0000': ("SC0000.BIN", 0x05061F90, 0xCF55C),
        'SC0500': ("SC0500.BIN", 0x0F202307, 0xB3B1C),
        'SC1000': ("SC1000.BIN", 0x1FCE09A7, 0x222CD8),
        'SC2000': ("SC2000.BIN", 0x2AA05426, 0x59364),
        'SC4000': ("SC4000.BIN", 0x2AF4F480, 0x5D8E8),
        'SP0024': ("SP0024.BIN", 0x0C5F7FD3, 0x4A2C),
        'SN0000': ("SN0000.BIN", 0x051314EC, 0x9A68),
        'SG0032': ("SG0032.BIN", 0x0D1ADF9F, 0x535C),
        'SP6900': ("SP6900.BIN", 0x24358079, 0x4E114, ALF11),
        'SP6901': ("SP6901.BIN", 0x243A618D, 0x49894, ALF11),
        'SP6902': ("SP6902.BIN", 0x243EFA21, 0x38AF4, ALF11),
        'SP6903': ("SP6903.BIN", 0x24428515, 0x3ACA8, ALF11),
        'SP6904': ("SP6904.BIN", 0x24CC9491, 0x46B0C, ALF11),
        'SP6905': ("SP6905.BIN", 0x244631BD, 0x9CD4C, ALF11),
        'SP6906': ("SP6906.BIN", 0x244FFF09, 0x4A270, ALF11),
        'SP6907': ("SP6907.BIN", 0x2454A179, 0x453A0, ALF11),
        'SP6908': ("SP6908.BIN", 0x2458F519, 0x487A0, ALF11),
        'SP6909': ("SP6909.BIN", 0x24D0FF9D, 0x47704, ALF11),
        'SP6910': ("SP6910.BIN", 0x245D7CB9, 0x4A784, ALF11),
        'SP6911': ("SP6911.BIN", 0x2462243D, 0x3DA44, ALF11),
        'SP6912': ("SP6912.BIN", 0x2465FE81, 0x4EA88, ALF11),
        'SP6913': ("SP6913.BIN", 0x246AE909, 0x40D80, ALF11),
        'SP6914': ("SP6914.BIN", 0x24D576A1, 0x42120, ALF11),
        'SP6915': ("SP6915.BIN", 0x246EF689, 0x44E90, ALF11),
        'SP6916': ("SP6916.BIN", 0x24734519, 0x4C288, ALF11),
        'SP6917': ("SP6917.BIN", 0x247807A1, 0x436BC, ALF11),
        'SP6918': ("SP6918.BIN", 0x247C3E5D, 0x46320, ALF11),
        'SP6919': ("SP6919.BIN", 0x24D997C1, 0x40000, ALF11),
        'SP6920': ("SP6920.BIN", 0x2480A17D, 0x5DDBC, ALF11),
        'SP6921': ("SP6921.BIN", 0x24867F39, 0x42F84, ALF11),
        'SP6922': ("SP6922.BIN", 0x248AAEBD, 0x498DC, ALF11),
        'SP6923': ("SP6923.BIN", 0x248F4799, 0x4B678, ALF11),
        'SP6924': ("SP6924.BIN", 0x24DD97C1, 0x40C70, ALF11),
        'SP6925': ("SP6925.BIN", 0x2493FE11, 0x4ED38, ALF11),
        'SP6926': ("SP6926.BIN", 0x2498EB49, 0x44CA8, ALF11),
        'SP6927': ("SP6927.BIN", 0x249D37F1, 0x43DB8, ALF11),
        'SP6928': ("SP6928.BIN", 0x24A175A9, 0x48B1C, ALF11),
        'SP6929': ("SP6929.BIN", 0x24E1A431, 0x42700, ALF11),
        'SP6930': ("SP6930.BIN", 0x24A600C5, 0x3C9F4, ALF11),
        'SP6931': ("SP6931.BIN", 0x24A9CAB9, 0x3861C, ALF11),
        'SP6932': ("SP6932.BIN", 0x24AD50D5, 0x36A18, ALF11),
        'SP6933': ("SP6933.BIN", 0x24E5CB31, 0x3AB00, ALF11),
        'SP6934': ("SP6934.BIN", 0x24E97631, 0x44FB0, ALF11),
        'SP6935': ("SP6935.BIN", 0x24BC8C01, 0x44338, ALF11),
        'SP6936': ("SP6936.BIN", 0x24EDC5E1, 0x40350, ALF11),
        'SP6937': ("SP6937.BIN", 0x24B0BAED, 0x43390, ALF11),
        'SP6938': ("SP6938.BIN", 0x24B4EE7D, 0x39FF4, ALF11),
        'SP6939': ("SP6939.BIN", 0x24B88E71, 0x3FD90, ALF11),
        'SP6940': ("SP6940.BIN", 0x24C0CF39, 0x308E8, ALF11),
        'SP6941': ("SP6941.BIN", 0x24C3D821, 0x3B984, ALF11),
        'SP6942': ("SP6942.BIN", 0x24C791A5, 0x502EC, ALF11),
        'EVINIT': ("EVINIT.BIN", 0x179D8EDC, 0x12288, ALF11),
        'CGINIT': ("CGINIT.BIN", 0x179D6C10, 0x12E0, ALF11),
    }
    name, off, size = targets[which][:3]
    alf = targets[which][3] if len(targets[which]) > 3 else ALF
    disasm(name, off, size, alf=alf)
