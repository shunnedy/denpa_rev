#!/usr/bin/env python3
"""List / edit / copy denpa (電波人間) records in a v1.17.0 save.

Each denpa is a self-contained 252-byte (0xFC) record. Party = 16 slots from
0x2588; box = slots from 0x3548. A slot is empty when its first u32 (instance
id) is 0; a non-zero id means the slot is occupied, so adding a denpa is just
writing a valid 252-byte record into an empty slot.

Fields confirmed by cross-matching four known denpa (level 5 and 50):
    +0x00 u32  instance id (sequential in creation order)
    +0x14      name, UTF-16LE (<= ~10 code units)
    +0x1c..    body colour / antenna / face parts / owner name "AZAHAR"
               (appearance genetics - not fully decoded)
    +0x78 u16  HP
    +0x7a u8   AP
    +0x80 u8   happiness
    +0x96 u8   level
    +0x98 u32  cumulative EXP
Attack/defence/speed/evasion are NOT stored - the game computes them from
level + antenna + build, so they cannot be edited directly here.

    python3 tools/denpaedit.py save.bin list
    python3 tools/denpaedit.py save.bin get p1
    python3 tools/denpaedit.py save.bin set p0 level 50 --out new.bin
    python3 tools/denpaedit.py save.bin set p0 exp 814127 --out new.bin
    python3 tools/denpaedit.py save.bin set p0 name カスタム --out new.bin
    python3 tools/denpaedit.py save.bin copy b0 p2 --out new.bin   # 任意個体を出す
"""
import struct, sys, argparse

REC = 0xFC
PARTY, BOX = 0x2588, 0x3548
PARTY_SLOTS = 16
FIELDS = {'hp': (0x78, 2), 'ap': (0x7a, 1), 'happy': (0x80, 1),
          'level': (0x96, 1), 'exp': (0x98, 4), 'id': (0x00, 4)}


def slot_addr(spec):
    kind, idx = spec[0], int(spec[1:])
    base = PARTY if kind == 'p' else BOX
    if kind == 'p' and idx >= PARTY_SLOTS:
        raise SystemExit('party slots are p0..p15')
    return base + idx * REC


def name_of(buf, base):
    raw = buf[base + 0x14:base + 0x14 + 20]
    raw = raw.split(b'\x00\x00', 1)[0]
    try:
        return raw.decode('utf-16-le', 'ignore').rstrip('\x00')
    except Exception:
        return ''


def rd(buf, base, field):
    off, w = FIELDS[field]
    return int.from_bytes(buf[base + off:base + off + w], 'little')


def show(buf, spec):
    base = slot_addr(spec)
    occ = rd(buf, base, 'id')
    if not occ:
        return f'  {spec}: (empty)'
    return (f"  {spec}: {name_of(buf, base)}  Lv{rd(buf,base,'level')} "
            f"exp{rd(buf,base,'exp')} HP{rd(buf,base,'hp')} AP{rd(buf,base,'ap')} "
            f"幸福{rd(buf,base,'happy')} id{occ}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('save')
    ap.add_argument('cmd', choices=['list', 'get', 'set', 'copy'])
    ap.add_argument('a', nargs='?')
    ap.add_argument('b', nargs='?')
    ap.add_argument('c', nargs='?')
    ap.add_argument('--out', help='write result here (default: read-only)')
    args = ap.parse_args()
    buf = bytearray(open(args.save, 'rb').read())

    if args.cmd == 'list':
        print('party:')
        for i in range(PARTY_SLOTS):
            if rd(buf, PARTY + i * REC, 'id'):
                print(show(buf, f'p{i}'))
        print('box:')
        for i in range(64):
            if rd(buf, BOX + i * REC, 'id'):
                print(show(buf, f'b{i}'))
        return
    if args.cmd == 'get':
        print(show(buf, args.a))
        return
    if args.cmd == 'set':
        base = slot_addr(args.a)
        field, val = args.b, args.c
        if field == 'name':
            enc = val.encode('utf-16-le')[:0x1e] + b'\x00\x00'
            buf[base + 0x14:base + 0x14 + len(enc)] = enc
        else:
            off, w = FIELDS[field]
            buf[base + off:base + off + w] = int(val).to_bytes(w, 'little')
        print(show(buf, args.a))
    elif args.cmd == 'copy':
        src, dst = slot_addr(args.a), slot_addr(args.b)
        rec = bytes(buf[src:src + REC])
        buf[dst:dst + REC] = rec
        # give the copy a fresh instance id so it does not collide
        ids = [rd(buf, (PARTY if k == 'p' else BOX) + i * REC, 'id')
               for k in 'pb' for i in range(64)
               if (PARTY if k == 'p' else BOX) + i * REC + REC <= len(buf)]
        buf[dst:dst + 4] = (max(ids) + 1).to_bytes(4, 'little')
        print(f'copied {args.a} -> {args.b}')
        print(show(buf, args.b))
    if args.out:
        open(args.out, 'wb').write(buf)
        print(f'-> {args.out}')
    elif args.cmd in ('set', 'copy'):
        print('(--out 未指定: 保存していません)')


if __name__ == '__main__':
    main()
