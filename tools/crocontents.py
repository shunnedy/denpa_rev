#!/usr/bin/env python3
"""Inventory the event classes and dependencies of a contents*.cro module.

Each content module is compiled C++. Its RTTI type-name strings survive in
.rodata in the Itanium form without the `_ZTS` prefix - "10M02Opening" is the
class `M02Opening` - which gives a readable list of the event objects the
module implements. Its named imports say which functions of the static module
(see crosym.py) it calls, i.e. what the events actually do.
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from crosym import Cro

# <length><identifier> with the length matching exactly: an RTTI type name.
TYPENAME = re.compile(rb'(?<![0-9A-Za-z_])([0-9]{1,3})([A-Za-z_][A-Za-z0-9_]*)')


def typenames(data):
    out = []
    for m in TYPENAME.finditer(data):
        n = int(m.group(1))
        ident = m.group(2)
        if len(ident) >= n and n >= 3:
            out.append(ident[:n].decode('ascii'))
    return sorted(set(out))


def inventory(path):
    c = Cro(open(path, 'rb').read(), path)
    return dict(module=c.name,
                size=c.h['file_size'],
                exports=c.h['exp_num'] + c.h['iexp_num'],
                imports=[n for n, _ in c.imports()],
                classes=typenames(c.d))


if __name__ == '__main__':
    inv = inventory(sys.argv[1])
    print(f"{inv['module']}  size {inv['size']:#x}  "
          f"exports {inv['exports']}  imports {len(inv['imports'])}")
    print(f"  event classes ({len(inv['classes'])}):")
    for n in inv['classes']:
        print(f'    {n}')
