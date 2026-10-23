#!/usr/bin/env python3
"""Edit gold and jewels in a v1.17.0 電波人間のRPG FREE! save.

Jewels: a plain little-endian u32 at 0x2088 (no mirror, no checksum - docs/16).
Gold:   bit-packed variables var0x1a + var0x1b (30 bits each, cap 999,999,999)
        in the runtime variable store, which in a v1.17.0 save sits at byte
        0x965FF. Located from the gold anchor 999,999,999, confirmed on two
        saves (gold 28 and 999,999,999).

    python3 tools/moneyedit.py save.bin                       # read
    python3 tools/moneyedit.py save.bin --gold 999999999 --jewels 9999 --out new.bin
"""
import argparse, struct

JEWEL_OFF = 0x2088
VAR_BASE = 0x965FF          # variable store, v1.17.0
GOLD_LO_BIT = 65844         # var0x1a cumulative bit offset (varmap)
GOLD_HI_BIT = 65874         # var0x1b
W = 30
GOLD_CAP = 999999999


def getbits(buf, bit, w):
    bi = bit >> 3
    return (int.from_bytes(buf[bi:bi + 8], 'little') >> (bit & 7)) & ((1 << w) - 1)


def setbits(buf, bit, w, val):
    for k in range(w):
        p = bit + k
        b = (val >> k) & 1
        buf[p >> 3] = (buf[p >> 3] & ~(1 << (p & 7))) | (b << (p & 7))


def read(buf):
    gold = (getbits(buf, VAR_BASE * 8 + GOLD_LO_BIT, W)
            + getbits(buf, VAR_BASE * 8 + GOLD_HI_BIT, W))
    jew = struct.unpack_from('<I', buf, JEWEL_OFF)[0]
    return gold, jew


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('save')
    ap.add_argument('--gold', type=int)
    ap.add_argument('--jewels', type=int)
    ap.add_argument('--out')
    a = ap.parse_args()
    buf = bytearray(open(a.save, 'rb').read())
    g, j = read(buf)
    print(f'現在: gold={g:,}  jewels={j:,}')
    if a.gold is not None:
        v = min(max(a.gold, 0), GOLD_CAP)
        setbits(buf, VAR_BASE * 8 + GOLD_LO_BIT, W, v)   # all in the low half
        setbits(buf, VAR_BASE * 8 + GOLD_HI_BIT, W, 0)
    if a.jewels is not None:
        struct.pack_into('<I', buf, JEWEL_OFF, a.jewels & 0xFFFFFFFF)
    if a.gold is not None or a.jewels is not None:
        g2, j2 = read(buf)
        print(f'変更後: gold={g2:,}  jewels={j2:,}')
        if a.out:
            open(a.out, 'wb').write(buf)
            print(f'-> {a.out}')
        else:
            print('(--out 未指定: 保存せず)')


if __name__ == '__main__':
    main()
