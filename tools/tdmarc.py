#!/usr/bin/env python3
"""Denpa Men romfs archive reader (hex-named files such as 28480000).

Container layout
----------------
header (0x18 bytes)
  0x00 u32  format version        (0x0000000A on every file seen)
  0x04 u32  archive id            == the hex filename, stored little-endian
  0x08 u32  zero
  0x0C u32  0x00010000            (sub-version?)
  0x10 u32  section count N
  0x14 u32  zero

N section records (0x1C bytes each, immediately after the header)
  0x00 u32  timestamp-like value (high byte always 0x00)
  0x04 u32  kind  (1, 4, 6, 0x0A, 0x0B, 0x14 observed)
  0x08 u32  payload size
  0x0C u32  payload offset, absolute from start of file
  0x10 u32  1
  0x14 u32  1
  0x18 u32  total uncompressed size of the payload

Each payload is a self-contained standard ZIP (deflate or stored), so the
real game files are simply the ZIP entries of every section.
"""
import io, os, struct, sys, zipfile

HDR, REC = 0x18, 0x1C


def lz10_decompress(data):
    """Nintendo LZ77 type 0x10 (forward), used for the non-zip sections."""
    assert data[0] == 0x10, f'not LZ10: {data[0]:#02x}'
    size = int.from_bytes(data[1:4], 'little')
    if size == 0:                       # extended 32-bit size
        size = struct.unpack_from('<I', data, 4)[0]
        p = 8
    else:
        p = 4
    out = bytearray()
    while len(out) < size:
        flags = data[p]; p += 1
        for bit in range(8):
            if len(out) >= size:
                break
            if flags & (0x80 >> bit):
                b0, b1 = data[p], data[p + 1]; p += 2
                n = (b0 >> 4) + 3
                disp = (((b0 & 0xF) << 8) | b1) + 1
                for _ in range(n):
                    out.append(out[-disp])
            else:
                out.append(data[p]); p += 1
    return bytes(out[:size])


def unwrap(blob):
    """Return (payload, compressed?) - sections are either a raw ZIP or LZ10."""
    if blob[:2] == b'PK':
        return blob, False
    if blob and blob[0] == 0x10:
        return lz10_decompress(blob), True
    return blob, None


class Archive:
    def __init__(self, path):
        self.path = path
        self.raw = open(path, 'rb').read()
        (self.version, self.id, z0, self.subver,
         self.count, z1) = struct.unpack_from('<6I', self.raw, 0)
        assert self.version == 0x0A, f'version {self.version:#x}'
        self.sections = []
        for i in range(self.count):
            ts, kind, size, off, a, b, raw = struct.unpack_from(
                '<7I', self.raw, HDR + i * REC)
            self.sections.append(dict(i=i, ts=ts, kind=kind, size=size,
                                      off=off, a=a, b=b, raw_size=raw))

    def payload(self, sec):
        blob = self.raw[sec['off']:sec['off'] + sec['size']]
        return unwrap(blob)

    def zip(self, sec):
        data, _ = self.payload(sec)
        if data[:2] != b'PK':
            return None
        return zipfile.ZipFile(io.BytesIO(data))

    def entries(self):
        """Yield (section, ZipInfo) for every inner file."""
        for s in self.sections:
            z = self.zip(s)
            if z is None:
                yield s, None
                continue
            for info in z.infolist():
                yield s, info

    def extract(self, outdir):
        n = 0
        for s in self.sections:
            z = self.zip(s)
            if z is None:
                d = os.path.join(outdir, f'_raw_{s["i"]:04d}.bin')
                os.makedirs(outdir, exist_ok=True)
                open(d, 'wb').write(self.raw[s['off']:s['off'] + s['size']])
                n += 1
                continue
            z.extractall(outdir)
            n += len(z.namelist())
        return n


if __name__ == '__main__':
    cmd, path = sys.argv[1], sys.argv[2]
    a = Archive(path)
    if cmd == 'info':
        print(f'{os.path.basename(path)} id={a.id:08X} ver={a.version} '
              f'sections={a.count} filesize={len(a.raw)}')
        for s, info in a.entries():
            if info is None:
                print(f'  [{s["i"]:>3}] kind={s["kind"]:<3} '
                      f'(not a zip, {s["size"]} bytes raw)')
            else:
                print(f'  [{s["i"]:>3}] kind={s["kind"]:<3} '
                      f'{info.file_size:>9} {info.filename}')
    elif cmd == 'ls':
        for s, info in a.entries():
            print(info.filename if info else f'_raw_{s["i"]:04d}.bin')
    elif cmd == 'x':
        print(a.extract(sys.argv[3]), 'entries ->', sys.argv[3])


# ---------------------------------------------------------------- data tables
# Sections that are not ZIPs hold a single LZ10-compressed Genius Sonority
# data table. Partially decoded header (all little-endian):
#   0x00 u32 record count
#   0x04 u32 0x0C        (constant: header/field-descriptor size?)
#   0x08 u32 0x40        (constant: offset of the table name)
#   0x0C u32 table type id
#   0x10 u32 main block offset
#   0x14 u32 main block size   (== record count * record size)
#   0x18 u32 aux block offset  (0 when absent)
#   0x1C u32 aux block size
#   0x28 u32 total size of the decompressed blob
#   0x38 u32 length of the name including its NUL terminator
#   0x40 char[] table name, NUL-padded
def table_header(data):
    f = struct.unpack_from('<16I', data, 0)
    nlen = min(f[14], 0x40)
    blob = data[0x40:0x40 + nlen]
    blob = blob.split(b'\0', 1)[0]
    name = blob.decode('ascii', 'replace') if blob.isascii() else ''
    if not all(32 <= c < 127 for c in blob):
        name = ''
    rec_count, main_size = f[0], f[5]
    return dict(name=name, count=rec_count, type=f[3],
                main_off=f[4], main_size=main_size,
                aux_off=f[6], aux_size=f[7], total=f[10],
                rec_size=(main_size // rec_count) if rec_count else 0)
