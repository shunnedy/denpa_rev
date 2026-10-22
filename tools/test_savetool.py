#!/usr/bin/env python3
"""Self test for savetool.py: build a save-shaped file with known structures
inside and check the locator finds them.

No real save was available, so this proves the search logic rather than the
game's actual layout. The synthetic file imitates what the real one should
contain: a roster of records that each start with a name from the game's own
name pool, a gold field, a six-stat block and a run of item ids.
"""
import json, os, struct, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

fails = []


def check(name, got, want):
    ok = got == want
    print(f'  {"ok  " if ok else "FAIL"} {name}: {got}' + ('' if ok else f' != {want}'))
    if not ok:
        fails.append(name)


def main(dbdir):
    names = [r['name'] for r in json.load(open(f'{dbdir}/MessageDenpaName.json'))['rows']
             if 1 < len(r['name']) <= 10][:8]
    items = [r['id'] for r in json.load(open(f'{dbdir}/ItemData.json'))['rows']
             if r['id'] not in (0,)][:4]
    stats = (120, 48, 73, 65, 51, 44)
    gold = 1234567
    stride = 0x80

    buf = bytearray(0x5000)
    for i, nm in enumerate(names):                 # roster: name at record start
        off = 0x400 + i * stride
        enc = nm.encode('utf-16-le')
        buf[off:off + len(enc)] = enc
    struct.pack_into('<6H', buf, 0x1000, *stats)   # stat block
    struct.pack_into('<4H', buf, 0x1100, *items)   # item ids
    struct.pack_into('<I', buf, 0x2000, gold)      # gold

    with tempfile.TemporaryDirectory() as td:
        sp = os.path.join(td, 'save.bin')
        open(sp, 'wb').write(bytes(buf))

        def run(*args):
            r = subprocess.run([sys.executable, f'{HERE}/savetool.py', *args,
                                '--db', dbdir], capture_output=True, text=True)
            if r.returncode:
                print(r.stdout, r.stderr)
                fails.append(' '.join(args))
            return r.stdout

        out = run('names', sp)
        check('finds every planted name', sum(1 for nm in names if nm in out), len(names))
        check('infers the record stride', f'most common spacing: {stride} bytes' in out, True)

        out = run('value', sp, str(gold))
        check('finds gold as u32', f'{0x2000:#08x}  as u32' in out, True)

        out = run('stats', sp)
        check('finds the stat block', f'{0x1000:#08x}  {stats}' in out, True)

        out = run('items', sp)
        check('finds the item run', f'{0x1100:#08x}' in out, True)

        other = bytearray(buf)
        struct.pack_into('<I', other, 0x2000, gold + 1)
        other[0x3000] ^= 0xFF
        op = os.path.join(td, 'after.bin')
        open(op, 'wb').write(bytes(other))
        out = run('diff', sp, op)
        check('diff reports both edits', out.count('0x00') >= 2
              and f'{0x2000:#08x}' in out and f'{0x3000:#08x}' in out, True)

    print('\nFAILED:' if fails else '\nall checks passed', *fails)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'out/db'))
