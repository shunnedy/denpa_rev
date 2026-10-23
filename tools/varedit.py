#!/usr/bin/env python3
"""Read and write game variables in a save's bit-packed variable store.

The variable model is fully reverse-engineered (see docs/16, varmap.py): every
game variable is a bit field in one packed array, with width and cap from
flagData.bin, and the runtime read/write are FUN_002deec8 / FUN_002dd27c.
This reproduces both in Python. Gold = var 0x1a + var 0x1b (capped
999,999,999); jewels = var 0x1c (capped 9,999).

The one value this cannot derive from a save by itself is the array's byte
offset, when the save is all zeros (early game, gold 0): every candidate base
satisfies the "value <= max" check, so nothing discriminates. Pass --base once
it is known (from any save with non-zero gold/jewels, or by tracing the
loader), and every variable - and a working editor - follows.

    python3 tools/varedit.py save.bin --vars vars.json --base 0x3548 get gold
    python3 tools/varedit.py save.bin --vars vars.json --base 0x3548 set jewels 9999
    python3 tools/varedit.py save.bin --vars vars.json --find-base   # list candidates
"""
import argparse, json, struct, sys


def getbits(buf, bitbase, off, w):
    p = bitbase + off
    bi = p >> 3
    chunk = int.from_bytes(buf[bi:bi + 8].ljust(8, b'\0'), 'little')
    return (chunk >> (p & 7)) & ((1 << w) - 1)


def setbits(buf, bitbase, off, w, val):
    p = bitbase + off
    for k in range(w):
        bytei = (p + k) >> 3
        biti = (p + k) & 7
        bit = (val >> k) & 1
        buf[bytei] = (buf[bytei] & ~(1 << biti)) | (bit << biti)


def var_by_name(vars_, name):
    name = name.lower()
    for v in vars_:
        if v['note'] and name in v['note'].lower():
            yield v
    if name.startswith('0x'):
        idx = int(name, 16)
        for v in vars_:
            if v['index'] == idx:
                yield v


def read_gold(buf, base, vmap):
    lo = next(v for v in vmap if v['index'] == 0x1a)
    hi = next(v for v in vmap if v['index'] == 0x1b)
    return (getbits(buf, base * 8, lo['bit'], lo['width'])
            + getbits(buf, base * 8, hi['bit'], hi['width']))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('save')
    ap.add_argument('--vars', required=True, help='varmap.py --json output')
    ap.add_argument('--base', type=lambda x: int(x, 0),
                    help='byte offset of the variable bit array in the save')
    ap.add_argument('--find-base', action='store_true')
    ap.add_argument('op', nargs='?', choices=['get', 'set'])
    ap.add_argument('name', nargs='?')
    ap.add_argument('value', nargs='?', type=lambda x: int(x, 0))
    a = ap.parse_args()
    vmap = json.load(open(a.vars))['vars']
    data = bytearray(open(a.save, 'rb').read())

    if a.find_base:
        # every section offset that satisfies all max-constraints; on an all-zero
        # save this is ambiguous, which is the point this surfaces.
        cands = set()
        for o in range(0x14, 0x400, 8):
            off, sz = struct.unpack_from('<2I', data, o)
            if off < len(data) and 0 < sz <= len(data) and off + sz <= len(data):
                cands.add(off)
        cons = [(v['bit'] + e * v['width'], v['width'], v['max'])
                for v in vmap if 0 < v['max'] < (1 << v['width'])
                for e in range(v['count'])]
        total = (max(v['bit'] + v['width'] * v['count'] for v in vmap) + 7) // 8
        for base in sorted(cands):
            if base + total > len(data):
                continue
            bad = sum(1 for off, w, mx in cons if getbits(data, base * 8, off, w) > mx)
            nz = sum(1 for x in data[base:base + 0x4000] if x)
            if bad == 0:
                print(f'  base={base:#08x}  ok  nonzero(16KB)={nz}')
        print('note: an all-zero early save leaves several candidates; '
              'confirm with a save that has non-zero gold/jewels')
        return

    if a.base is None:
        sys.exit('--base is required for get/set (use --find-base to list candidates)')

    if a.op == 'get' and a.name == 'gold':
        print(read_gold(data, a.base, vmap))
        return
    hits = list(var_by_name(vmap, a.name)) if a.name else []
    if not hits:
        sys.exit(f'unknown variable: {a.name}')
    v = hits[0]
    if a.op == 'get':
        print(getbits(data, a.base * 8, v['bit'], v['width']))
    elif a.op == 'set':
        val = min(a.value, v['max']) if v['max'] else a.value
        setbits(data, a.base * 8, v['bit'], v['width'], val)
        open(a.save, 'wb').write(data)
        print(f"set var {v['index']:#x} = {val} at bit {v['bit']} (base {a.base:#x})")


if __name__ == '__main__':
    main()
