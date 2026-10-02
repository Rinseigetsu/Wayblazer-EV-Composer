# -*- coding: utf-8 -*-
"""Full disassembly dump for SC scripts. Reuses disasm_sc machinery.
Usage: python disasm_full.py SC0500 [outfile]
Writes every instruction (not just hash ops) to a txt file."""
import sys, os
from collections import Counter
import disasm_sc as d

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
}

def fmt_op(t, v):
    if t == 0:
        return '(0:0x%X)' % v
    if t == 3:
        return '(3:0x%X)' % v
    if t == 9:
        return '(9:0x%X)' % v
    if t == 2:
        # string operand - value may be an offset; show raw
        return '(2:0x%X)' % v
    if t == 1:
        return '(1:0x%X)' % v
    return '(%d:0x%X)' % (t, v)

def disasm_full(name, offset, size, start=0x44, outpath=None):
    data = d.read(offset, size)
    body = data[start:]
    opcount = Counter()
    hash_ops = Counter()
    lines = []
    pc = 0
    n = 0
    bad = 0
    header = ["="*78,
              "%s  size=%d  body=%d bytes" % (name, size, len(body)),
              "format: [instr_idx] opCODE size=LEN  operands (t:val)  t=0 imm, t=3 hashvar, t=9 local, t=2 strref"]
    while pc*4 < len(body):
        op = d.iw(body, pc)
        if op is None: break
        if op < 0x400 and op in d.sizes:
            real, s = d.sizes[op]
            s = s if s else 1
            opcount[op] += 1
            nop = (s - 1)//2 if s >= 3 else 0
            ops = []
            for k in range(nop):
                t = d.iw(body, pc+1+k*2)
                v = d.iw(body, pc+2+k*2)
                if t is None: break
                ops.append((t, v))
            has_hash = any(t == 3 or (v >> 24) == 0x17 or (t == 0 and v >= 0x100000) for t, v in ops)
            if has_hash:
                hash_ops[op] += 1
            tag = '  <== HASH' if has_hash else ''
            ops_s = ' '.join(fmt_op(t, v) for t, v in ops)
            lines.append("[%6d] op%-4d size=%-2d %s%s" % (pc, op, s, ops_s, tag))
            pc += s
            n += 1
        else:
            bad += 1
            lines.append("[%6d] op%-4d (UNKNOWN) val=0x%X" % (pc, op, op))
            pc += 1
            n += 1
    # stats
    lines.append("")
    lines.append("--- total instructions: %d  unknown: %d ---" % (n, bad))
    lines.append("--- top 60 opcodes ---")
    for op, c in opcount.most_common(60):
        lines.append("   op%-4d x%d" % (op, c))
    lines.append("")
    lines.append("--- opcodes with HASH-type operands ---")
    for op, c in hash_ops.most_common(60):
        lines.append("   op%-4d x%d" % (op, c))
    out = "\n".join(header + lines)
    if outpath:
        with open(outpath, 'w', encoding='utf-8') as f:
            f.write(out + "\n")
        print("wrote %s: %d instructions, %d unknown, %d lines -> %s" % (name, n, bad, len(lines), outpath))
    else:
        print(out)
    return n, bad

if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'SC0500'
    outpath = sys.argv[2] if len(sys.argv) > 2 else None
    name, off, size = targets[which]
    if outpath is None:
        outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), which + '_full_disasm.txt')
    disasm_full(name, off, size, outpath=outpath)
