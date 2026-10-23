#!/usr/bin/env python3
"""Export the game-variable dictionary from flagData.bin.

ScriptFlag::GetGold (0x00184C14) and the bit accessors
FUN_002deec8 (read) / FUN_002ddc78->FUN_002dd27c (write) show that game
variables live in one bit-packed array. Each variable's bit width and cap come
from flagData.bin (table FlagData): record +0 = max value, +8 = element count,
+0xb = bit width. The runtime assigns each variable a bit offset by summing the
widths of the variables before it (record +4, zero in ROM, filled at load).

This reproduces that offset assignment, so every variable resolves to
(bit offset, width, max, count). Known semantics from the code:

    0x1a + 0x1b  gold   (two 30-bit halves, summed, capped 999,999,999)
    0x1c         jewels (14-bit, cap 9,999)

    python3 tools/varmap.py extracted/update_romfs            # print the table
    python3 tools/varmap.py extracted/update_romfs --json vars.json
"""
import glob, json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmarc import Archive, table_header

KNOWN = {0x1a: 'gold (low half)', 0x1b: 'gold (high half)', 0x1c: 'jewels'}


def flagdata(romfs):
    for p in sorted(glob.glob(os.path.join(romfs, '*'))):
        b = os.path.basename(p)
        if len(b) != 8 or any(c not in '0123456789ABCDEF' for c in b):
            continue
        a = Archive(p)
        for s in a.sections:
            z = a.zip(s)
            blobs = ([z.read(i) for i in z.infolist()
                      if i.filename.endswith(('.bin', '.dat'))] if z
                     else [a.payload(s)[0]])
            for d in blobs:
                if len(d) < 0x44:
                    continue
                h = table_header(d)
                if h['valid'] and h['name'] == 'FlagData':
                    return h, d
    return None, None


def build(romfs):
    h, d = flagdata(romfs)
    if h is None:
        raise SystemExit('FlagData not found')
    out, bit = [], 0
    for i in range(h['count']):
        r = d[h['rec_off'] + i * h['rec_size']:h['rec_off'] + (i + 1) * h['rec_size']]
        mx = struct.unpack_from('<I', r, 0)[0]
        cnt = max(struct.unpack_from('<H', r, 8)[0], 1)
        width = r[0xb]
        out.append(dict(index=i, bit=bit, width=width, count=cnt, max=mx,
                        note=KNOWN.get(i, '')))
        bit += width * cnt
    return out, bit


if __name__ == '__main__':
    romfs = sys.argv[1]
    rows, total = build(romfs)
    if '--json' in sys.argv:
        path = sys.argv[sys.argv.index('--json') + 1]
        json.dump(dict(total_bits=total, total_bytes=(total + 7) // 8, vars=rows),
                  open(path, 'w'), ensure_ascii=False, indent=1)
        print(f'{len(rows)} vars, {total} bits ({(total + 7)//8} bytes) -> {path}')
    else:
        print(f'{len(rows)} variables, total {total} bits = {(total + 7)//8} bytes')
        for v in rows:
            tag = f'  <- {v["note"]}' if v['note'] else ''
            if v['max'] or v['note'] or v['count'] > 1:
                print(f"  var {v['index']:#04x}  bit {v['bit']:>7} "
                      f"w{v['width']:<2} x{v['count']:<4} max {v['max']:>11,}{tag}")
