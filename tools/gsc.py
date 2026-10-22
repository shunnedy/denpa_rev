#!/usr/bin/env python3
"""Read a .gsc resource wrapper out of a Denpa Men romfs archive.

Despite the name, a .gsc is not a script: it is a thin container that wraps one
build-time resource (in this game always a map-model .bch) together with the
original source path and a transform.

header (0x180 bytes, little-endian)
  0x0C u16 1, u16 1      version
  0x14 u32               block offset (0x30 observed)
  0x18 u32               end of the path region
  0x24 u32               extra block offset, 0 when absent
                         (starts with u32 0x10, then an AABB as 6 floats)
  0x34 u32               block count (2, 3 or 16 observed)
  0x38 u32               payload offset, always 0x180
  0x3C u32               payload size
  0x40 u32               source path offset, always 0x54
  0x54      UTF-16LE source path, e.g.
            rom:/cg/model/map/map_parts/bgpt_15_green/bgpt_15_green_01.bch
  (0x18)+0x24
            3 floats, scale - (1.0, 1.0, 1.0) on 656 of 657 base files.
            Not at a fixed offset: it sits after the variable-length path,
            at the value of 0x18 plus 0x24.
  0x180     payload

Of the 980 .gsc in base + update romfs, 979 wrap a .bch under rom:/cg/model/map.
The payload size at 0x3C does not always reach the end of the file: 634 files
carry a further block, whose offset is the value at 0x24.
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmarc import Archive


def parse(data):
    off, size = struct.unpack_from('<2I', data, 0x38)
    poff = struct.unpack_from('<I', data, 0x40)[0]
    path = data[poff:poff + 0x200].decode('utf-16-le', 'ignore').split('\0')[0]
    return dict(path=path,
                blocks=struct.unpack_from('<I', data, 0x34)[0],
                extra_off=struct.unpack_from('<I', data, 0x24)[0],
                scale=struct.unpack_from(
                    '<3f', data, struct.unpack_from('<I', data, 0x18)[0] + 0x24),
                payload_off=off, payload_size=size,
                magic=data[off:off + 4], total=len(data))


if __name__ == '__main__':
    a = Archive(sys.argv[1])
    for s in a.sections:
        z = a.zip(s)
        if z is None:
            continue
        for i in z.infolist():
            if not i.filename.endswith('.gsc'):
                continue
            h = parse(z.read(i))
            print(f"{i.filename}\n  {h['path']}\n  payload {h['magic']} "
                  f"{h['payload_off']:#x}+{h['payload_size']:#x} of {h['total']:#x}"
                  f"  blocks={h['blocks']} extra={h['extra_off']:#x} scale={h['scale']}")
