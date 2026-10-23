#!/usr/bin/env python3
"""Generate Azahar/Citra (Gateway/Action-Replay) cheat codes for Denpa Men FREE!.

Gold and jewels are not flat values - they are bit-packed variables read
through ScriptFlag::GetGold / GetJewel (docs/16). The robust, save-independent
cheat is to overwrite those getters so they return a constant. Both are ARM
thunks, so three 32-bit writes each replace them with:

    LDR r0, [pc, #0]   ; E59F0000  (ARM pipeline: PC+8 -> the literal below)
    BX  lr             ; E12FFF1E
    .word VALUE

AR line `0AAAAAAA VVVVVVVV` writes the 32-bit VVVVVVVV to guest address
0AAAAAAA (top nibble 0 = 32-bit write).

Addresses are for the UPDATED game (v1.17.0, title 0004000E00125D00):
    GetGold  0x00191DD4
    GetJewel 0x00191E24

    python3 tools/mkcheat.py            # default gold 999999999, jewels 9999
    python3 tools/mkcheat.py --gold 50000 --jewels 500
"""
import argparse, struct

GETTERS = {'Gold': 0x00191DD4, 'Jewel': 0x00191E24}
LDR_PC0 = 0xE59F0000     # LDR r0,[pc,#0]
BX_LR   = 0xE12FFF1E     # BX lr


def patch_lines(addr, value):
    return [(addr, LDR_PC0), (addr + 4, BX_LR), (addr + 8, value & 0xFFFFFFFF)]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--gold', type=int, default=999999999)   # cap 999,999,999
    ap.add_argument('--jewels', type=int, default=9999)      # cap 9,999
    a = ap.parse_args()
    gold = min(max(a.gold, 0), 999999999)
    jew = min(max(a.jewels, 0), 9999)

    print('[Gold max (always ' + f'{gold:,})]')
    for addr, val in patch_lines(GETTERS['Gold'], gold):
        print(f'{addr:08X} {val:08X}')
    print()
    print('[Jewels max (always ' + f'{jew:,})]')
    for addr, val in patch_lines(GETTERS['Jewel'], jew):
        print(f'{addr:08X} {val:08X}')


if __name__ == '__main__':
    main()
