#!/usr/bin/env python3
"""Live patching of 電波人間のRPG FREE! over the Azahar / Citra GDB stub.

Why this shape: the emulator recompiles guest code in blocks and caches them,
and the ARM11 keeps an instruction cache, so overwriting .text while the game
runs is not guaranteed to take effect. Patching DATA is. The game is C++ and
its static module exports its vtables by name, so redirecting a virtual
method - one word in .data - is both the safest and the most reversible way
to swap behaviour at runtime. `vtset` does that; `tramp` is there for the
cases where a .text patch is unavoidable.

Addresses come from the static module's export table, so they are real
virtual addresses (see tools/crosym.py). Every write is journalled with the
bytes it replaced, so `restore` puts the process back without a restart.

  python3 tools/inject.py --crs extracted/base_romfs/app/lanai.crs \\
      sym 'ItemCommon::OpenTreasure'
  python3 tools/inject.py --crs ... vtget 'vtable for ItemCommon' --count 8
  python3 tools/inject.py --crs ... vtset 'vtable for ItemCommon' 3 0x00123456
  python3 tools/inject.py --crs ... retval 'ItemCommon::IsOpenItem' 1
  python3 tools/inject.py restore
"""
import argparse, json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crosym import Cro
from rsp import Rsp

JOURNAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inject-journal.json')


# ---------------------------------------------------------------- symbols
def demangle(names):
    try:
        out = subprocess.run(['c++filt'], input='\n'.join(names),
                             capture_output=True, text=True).stdout.splitlines()
        return out if len(out) == len(names) else names
    except FileNotFoundError:
        return names


def load_symbols(crs_path):
    """{demangled or raw name: address} from a .crs / .cro export table."""
    c = Cro(open(crs_path, 'rb').read(), crs_path)
    raw = [(n, a) for n, a, s, o in c.exports() if a is not None]
    nice = demangle([n for n, _ in raw])
    table = {}
    for (mangled, addr), pretty in zip(raw, nice):
        table.setdefault(pretty, addr)
        table.setdefault(mangled, addr)
    return table, c


def find(table, query):
    if query in table:
        return [(query, table[query])]
    if query.lower().startswith('0x'):
        return [(query, int(query, 16))]
    hits = sorted((k, v) for k, v in table.items() if query in k)
    return hits


# ---------------------------------------------------------- code emitters
def thumb_abs_jump(target):
    """LDR.W PC,[PC,#0] + literal. 8 bytes, needs a 4-byte aligned site."""
    return bytes.fromhex('dff8 00f0'.replace(' ', '')) + \
        int(target).to_bytes(4, 'little')


def arm_abs_jump(target):
    """LDR PC,[PC,#-4] + literal. 8 bytes."""
    return bytes.fromhex('04f01fe5') + int(target).to_bytes(4, 'little')


def thumb_return(value):
    """MOVS r0,#imm8 ; BX lr - only for 0..255."""
    if not 0 <= value <= 255:
        raise ValueError('thumb_return takes an 8-bit immediate')
    return bytes([value, 0x20, 0x70, 0x47])


def arm_return(value):
    """MOV r0,#imm8 ; BX lr"""
    if not 0 <= value <= 255:
        raise ValueError('arm_return takes an 8-bit immediate')
    return bytes([value, 0x00, 0xA0, 0xE3]) + bytes.fromhex('1eff2fe1')


# ----------------------------------------------------------------- journal
def journal_add(entry):
    log = json.load(open(JOURNAL)) if os.path.exists(JOURNAL) else []
    log.append(entry)
    json.dump(log, open(JOURNAL, 'w'), indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=24689,
                    help='Azahar GDB stub (Citra used 4000)')
    ap.add_argument('--crs', help='path to app/lanai.crs for symbol lookup')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('sym', help='look a symbol up, no connection needed')
    p.add_argument('query')
    p = sub.add_parser('read', help='hexdump guest memory')
    p.add_argument('where'); p.add_argument('length', type=lambda x: int(x, 0))
    p = sub.add_parser('write', help='write raw hex bytes')
    p.add_argument('where'); p.add_argument('hexbytes')
    p = sub.add_parser('vtget', help='read a vtable')
    p.add_argument('query'); p.add_argument('--count', type=int, default=8)
    p = sub.add_parser('vtset', help='redirect one virtual method')
    p.add_argument('query'); p.add_argument('index', type=int)
    p.add_argument('target')
    p = sub.add_parser('retval', help='make a function return a constant')
    p.add_argument('query'); p.add_argument('value', type=lambda x: int(x, 0))
    p.add_argument('--arm', action='store_true', help='site is ARM, not Thumb')
    p = sub.add_parser('tramp', help='overwrite a function with a jump')
    p.add_argument('query'); p.add_argument('target')
    p.add_argument('--arm', action='store_true')
    p = sub.add_parser('blob', help='upload a file into guest memory')
    p.add_argument('where'); p.add_argument('path')
    sub.add_parser('restore', help='undo every journalled write')
    sub.add_parser('status', help='stub features and halt reason')

    a = ap.parse_args()
    table = {}
    if a.crs:
        table, _ = load_symbols(a.crs)

    def addr_of(q):
        hits = find(table, q)
        if not hits:
            sys.exit(f'symbol not found: {q}')
        if len(hits) > 1:
            print('ambiguous:', file=sys.stderr)
            for k, v in hits[:12]:
                print(f'  0x{v:08X}  {k}', file=sys.stderr)
            sys.exit(1)
        return hits[0][1]

    if a.cmd == 'sym':
        for k, v in find(table, a.query)[:40]:
            print(f'0x{v:08X}  {k}')
        return

    r = Rsp(a.host, a.port)
    feat = r.connect()

    if a.cmd == 'status':
        print('features:', feat)
        print('halt reason:', r.halt_reason())
    elif a.cmd == 'read':
        base = addr_of(a.where)
        data = r.read_mem(base, a.length)
        for i in range(0, len(data), 16):
            c = data[i:i + 16]
            print(f'{base+i:08X}  {c.hex(" ")}')
    elif a.cmd == 'write':
        base, data = addr_of(a.where), bytes.fromhex(a.hexbytes)
        old = r.read_mem(base, len(data))
        r.write_mem(base, data)
        journal_add(dict(addr=base, old=old.hex(), new=data.hex(), how='write'))
        print(f'wrote {len(data)} bytes at {base:08X} (was {old.hex()})')
    elif a.cmd == 'vtget':
        base = addr_of(a.query)
        for i in range(a.count):
            v = r.read_u32(base + i * 4)
            print(f'  [{i}] {base+i*4:08X} -> 0x{v:08X}')
    elif a.cmd == 'vtset':
        base = addr_of(a.query) + a.index * 4
        target = addr_of(a.target)
        old = r.read_u32(base)
        r.write_u32(base, target)
        journal_add(dict(addr=base, old=old.to_bytes(4, 'little').hex(),
                         new=int(target).to_bytes(4, 'little').hex(), how='vtset'))
        print(f'vtable[{a.index}] at {base:08X}: 0x{old:08X} -> 0x{target:08X}')
    elif a.cmd in ('retval', 'tramp'):
        site = addr_of(a.query) & ~1
        if a.cmd == 'retval':
            code = arm_return(a.value) if a.arm else thumb_return(a.value)
        else:
            t = addr_of(a.target)
            code = arm_abs_jump(t) if a.arm else thumb_abs_jump(t)
            if site % 4:
                sys.exit(f'{site:08X} is not 4-byte aligned; '
                         'the literal pool would be misread')
        old = r.read_mem(site, len(code))
        r.write_mem(site, code)
        journal_add(dict(addr=site, old=old.hex(), new=code.hex(), how=a.cmd))
        print(f'patched {site:08X}: {old.hex()} -> {code.hex()}')
        print('note: a .text patch may not take effect until the emulator '
              'invalidates its cached block for that address')
    elif a.cmd == 'blob':
        base = addr_of(a.where)
        data = open(a.path, 'rb').read()
        old = r.read_mem(base, len(data))
        r.write_mem(base, data)
        journal_add(dict(addr=base, old=old.hex(), new=data.hex(), how='blob'))
        print(f'uploaded {len(data)} bytes to {base:08X}')
    elif a.cmd == 'restore':
        log = json.load(open(JOURNAL)) if os.path.exists(JOURNAL) else []
        for e in reversed(log):
            r.write_mem(e['addr'], bytes.fromhex(e['old']))
            print(f'restored {e["addr"]:08X} ({e["how"]})')
        if log:
            os.remove(JOURNAL)
        else:
            print('journal is empty')
    r.close()


if __name__ == '__main__':
    main()
