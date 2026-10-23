#!/usr/bin/env python3
"""Read / write the jewel count in a 電波人間のRPG FREE! save (Azahar, extracted).

Unlike gold (bit-packed variables 0x1a+0x1b, docs/16), the jewel total is a
plain little-endian u32 in the profile section. Found by planting a known
value (99999) and locating it: offset 0x2088, section 0x2050, no mirror copy.

The header word at 0x04 is a constant magic (identical across a v1.0.0 and a
v1.17.0 save), not a content checksum, so the field can be written directly.

    python3 tools/jeweledit.py save.bin                 # read
    python3 tools/jeweledit.py save.bin 500000 out.bin  # write to a copy
"""
import struct, sys, shutil

JEWEL_OFF = 0x2088     # v1.17.0 profile section 0x2050 +0x38


def read(path):
    with open(path, 'rb') as f:
        f.seek(JEWEL_OFF)
        return struct.unpack('<I', f.read(4))[0]


def write(src, value, dst):
    shutil.copyfile(src, dst)
    with open(dst, 'r+b') as f:
        f.seek(JEWEL_OFF)
        f.write(struct.pack('<I', value & 0xFFFFFFFF))


if __name__ == '__main__':
    save = sys.argv[1]
    if len(sys.argv) == 2:
        print(f'jewels = {read(save)} (offset {JEWEL_OFF:#x})')
    else:
        val = int(sys.argv[2])
        out = sys.argv[3] if len(sys.argv) > 3 else save
        write(save, val, out)
        print(f'wrote jewels = {val} -> {out}  (verify: {read(out)})')
