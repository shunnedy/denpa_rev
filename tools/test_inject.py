#!/usr/bin/env python3
"""End-to-end self test for the injection tooling, against tools/mockrsp.py.

Proves the RSP client and inject.py work without Azahar running: it serves a
toy memory image containing ItemCommon's vtable and one function body, then
drives the real CLI against it and checks the bytes that land in memory.
"""
import os, subprocess, sys, threading, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mockrsp
from rsp import Rsp

PORT = 24731
CRS = os.path.join(os.path.dirname(HERE), 'extracted/base_romfs/app/lanai.crs')
VTABLE = 0x0047DC48          # vtable for ItemCommon
FUNC = 0x0017F150            # ItemCommon::IsOpenItem()
REGIONS = [(VTABLE, bytes.fromhex('01105000' '11105000' '21105000' '31105000')),
           (FUNC, bytes.fromhex('80b500af' '0346fff7' '00f880bd'))]

fails = []


def check(name, got, want):
    ok = got == want
    print(f'  {"ok  " if ok else "FAIL"} {name}: {got}' + ('' if ok else f' != {want}'))
    if not ok:
        fails.append(name)


def peek(addr, n):
    """Open a short-lived connection; the stub serves one client at a time."""
    r = Rsp('127.0.0.1', PORT); r.connect()
    try:
        return r.read_mem(addr, n)
    finally:
        r.close()


def cli(*args):
    r = subprocess.run([sys.executable, os.path.join(HERE, 'inject.py'),
                        '--port', str(PORT), '--crs', CRS, *args],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout, r.stderr)
        fails.append(' '.join(args))
    return r.stdout.strip()


def main():
    journal = os.path.join(HERE, 'inject-journal.json')
    if os.path.exists(journal):
        os.remove(journal)
    t = threading.Thread(target=mockrsp.serve, args=(PORT, REGIONS, False), daemon=True)
    t.start()
    time.sleep(0.4)

    print('RSP client:')
    r = Rsp('127.0.0.1', PORT); feat = r.connect()
    check('no-ack negotiated', r.no_ack, True)
    check('halt reason', r.halt_reason(), 'S05')
    check('vtable[0] read', hex(r.read_u32(VTABLE)), '0x501001')
    r.write_u32(VTABLE + 4, 0xDEADBEEF)
    check('u32 round trip', hex(r.read_u32(VTABLE + 4)), '0xdeadbeef')
    r.write_u32(VTABLE + 4, 0x00501011)
    big = bytes(range(256)) * 4
    r.write_mem(0x00500000, big)
    check('1KB round trip', r.read_mem(0x00500000, len(big)) == big, True)
    r.close()

    print('inject.py:')
    check('sym lookup', 'ItemCommon::IsOpenItem()' in cli('sym', 'IsOpenItem'), True)
    out = cli('vtget', 'vtable for ItemCommon', '--count', '4')
    check('vtget lists 4 entries', len(out.splitlines()), 4)
    cli('vtset', 'vtable for ItemCommon', '2', '0x0017F164')
    check('vtset wrote the pointer', peek(VTABLE + 8, 4).hex(), '64f11700')
    cli('retval', 'ItemCommon::IsOpenItem', '1')
    check('retval emitted MOVS r0,#1 / BX lr', peek(FUNC, 4).hex(), '01207047')

    cli('restore')
    check('restore put the vtable back', peek(VTABLE + 8, 4).hex(), '21105000')
    check('restore put the code back', peek(FUNC, 4).hex(), '80b500af')
    check('journal removed', os.path.exists(journal), False)

    print('\nFAILED:' if fails else '\nall checks passed', *fails)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
