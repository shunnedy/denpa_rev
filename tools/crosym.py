#!/usr/bin/env python3
"""CRO0 parser for the 3DS dynamic-module format (.cro / .crs).

The static module `app/lanai.crs` is the main executable's export registry:
its segment table holds the real virtual addresses of .text/.rodata/.data, so
every named export resolves to an absolute address in code.bin. Each
`contents*.cro` additionally lists the static symbols it imports, which says
what a given content module actually calls.

Header (the 0x80 bytes before it are four SHA-256 hashes):
  0x080 "CRO0"
  0x090 u32 file size            0x094 u32 bss size
  0x0C0 u32 module name offset   0x0C4 u32 module name size
  0x0C8 u32 segment table off    0x0CC u32 segment count      (12 bytes each)
  0x0D0 u32 named export off     0x0D4 u32 count              (8 bytes each)
  0x0D8 u32 indexed export off   0x0DC u32 count              (4 bytes each)
  0x0E0 u32 export strings off   0x0E4 u32 size
  0x0E8 u32 export tree off      0x0EC u32 count
  0x0F0 u32 import module off    0x0F4 u32 count              (20 bytes each)
  0x0F8 u32 import patches off   0x0FC u32 count
  0x100 u32 named import off     0x104 u32 count              (8 bytes each)
  0x108 u32 indexed import off   0x10C u32 count
  0x110 u32 anonymous import off 0x114 u32 count
  0x118 u32 import strings off   0x11C u32 size
  0x120 u32 static anon sym off  0x124 u32 count
  0x128 u32 relocation patch off 0x12C u32 count
  0x130 u32 static patch off     0x134 u32 count

The tables are laid out back to back in this order, which is how the parser
validates a file: named exports (8 bytes each) -> export tree (8) ->
indexed exports (4) -> export strings.

A symbol's location is one u32: `segment index = v & 0xF`, `offset = v >> 4`.
Odd resulting addresses mean Thumb (the low bit is the Thumb flag).
"""
import struct, sys, os, csv

H = 0x80
F = {k: H + v for k, v in dict(
    magic=0x00, file_size=0x10, bss_size=0x14,
    name_off=0x40, name_size=0x44, seg_off=0x48, seg_num=0x4C,
    exp_off=0x50, exp_num=0x54, iexp_off=0x58, iexp_num=0x5C,
    estr_off=0x60, estr_size=0x64, etree_off=0x68, etree_num=0x6C,
    imod_off=0x70, imod_num=0x74, ipatch_off=0x78, ipatch_num=0x7C,
    imp_off=0x80, imp_num=0x84, iimp_off=0x88, iimp_num=0x8C,
    aimp_off=0x90, aimp_num=0x94, istr_off=0x98, istr_size=0x9C,
    sanon_off=0xA0, sanon_num=0xA4, reloc_off=0xA8, reloc_num=0xAC,
    spatch_off=0xB0, spatch_num=0xB4).items()}


class Cro:
    def __init__(self, data, path='<mem>'):
        self.d, self.path = data, path
        assert data[H:H + 4] == b'CRO0', f'not a CRO0: {data[H:H+4]!r}'
        self.h = {k: self.u32(o) for k, o in F.items() if k != 'magic'}
        self.name = self.cstr(self.h['name_off'])
        self.segments = [struct.unpack_from('<3I', data, self.h['seg_off'] + i * 12)
                         for i in range(self.h['seg_num'])]

    def u32(self, o):
        return struct.unpack_from('<I', self.d, o)[0]

    def cstr(self, o):
        return self.d[o:].split(b'\0', 1)[0].decode('ascii', 'replace')

    def resolve(self, v):
        """(segment index, offset) -> absolute virtual address."""
        seg, off = v & 0xF, v >> 4
        if seg >= len(self.segments):
            return None, seg, off
        return self.segments[seg][0] + off, seg, off

    def exports(self):
        """Yield (name, absolute address, segment, raw offset)."""
        for i in range(self.h['exp_num']):
            noff, soff = struct.unpack_from('<2I', self.d, self.h['exp_off'] + i * 8)
            addr, seg, off = self.resolve(soff)
            yield self.cstr(noff), addr, seg, off

    def imports(self):
        """Named imports: symbols this module expects from elsewhere."""
        for i in range(self.h['imp_num']):
            noff, poff = struct.unpack_from('<2I', self.d, self.h['imp_off'] + i * 8)
            yield self.cstr(noff), poff

    def import_modules(self):
        for i in range(self.h['imod_num']):
            noff = self.u32(self.h['imod_off'] + i * 20)
            yield self.cstr(noff)

    def check(self):
        """Self-consistency of the table arithmetic; returns a list of problems."""
        p = []
        for a, sz, nxt in (('exp', 8, 'etree'), ('etree', 8, 'iexp'),
                           ('iexp', 4, 'estr')):
            end = self.h[f'{a}_off'] + self.h[f'{a}_num'] * sz
            if end != self.h[f'{nxt}_off']:
                p.append(f'{a} ends {end:#x} but {nxt} starts {self.h[f"{nxt}_off"]:#x}')
        if self.h['file_size'] != len(self.d):
            p.append(f'file size field {self.h["file_size"]:#x} != {len(self.d):#x}')
        return p


# A segment's TYPE is its third field, not its index: 0 .text, 1 .rodata,
# 2 .data, 3 .bss. In .cro files the order differs from the static module.
SEGTYPE = {0: '.text', 1: '.rodata', 2: '.data', 3: '.bss'}


def segname(c, i):
    if i >= len(c.segments):
        return f'seg{i}'
    return SEGTYPE.get(c.segments[i][2], f'type{c.segments[i][2]}')

if __name__ == '__main__':
    cmd = sys.argv[1]
    c = Cro(open(sys.argv[2], 'rb').read(), sys.argv[2])
    if cmd == 'info':
        print(f'module {c.name!r}  file {c.h["file_size"]:#x}  bss {c.h["bss_size"]:#x}')
        for i, (o, sz, sid) in enumerate(c.segments):
            print(f'  seg{i} {SEGTYPE.get(sid,"?"):8s} {o:#010x} size {sz:#x}')
        print(f'  exports: {c.h["exp_num"]} named, {c.h["iexp_num"]} indexed')
        print(f'  imports: {c.h["imp_num"]} named, {c.h["iimp_num"]} indexed, '
              f'{c.h["aimp_num"]} anonymous, modules {c.h["imod_num"]}')
        prob = c.check()
        print('  consistency:', 'OK' if not prob else prob)
    elif cmd == 'exports':
        w = csv.writer(sys.stdout)
        w.writerow(['address', 'segment', 'name'])
        for name, addr, seg, off in c.exports():
            w.writerow([f'0x{addr:08X}' if addr is not None else '', segname(c, seg), name])
    elif cmd == 'imports':
        for name, poff in c.imports():
            print(name)
