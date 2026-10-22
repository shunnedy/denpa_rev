#!/usr/bin/env python3
"""Build an IPS patch that re-points the game at your own server.

The game's endpoint strings all start with the 25-byte prefix
`https://la1.denpamen.com/`. A replacement of exactly the same length can be
written in place, which keeps every pointer and length in the binary valid and
means the patch is a handful of byte ranges with no relocation:

    https://la1.denpamen.com/      25 bytes
    http://colos.asahina.net/      25 bytes

Keep the scheme as `https://` so the connection stays verified; that leaves
room for a 16-character host, i.e. a four-letter subdomain of an 11-character
domain. The game also pins `la1.denpamen.com`'s certificate (docs/07), so the
server it now talks to has to present something the console accepts. `--cert`
rewrites that pinned certificate in place, which re-points the trust anchor
without turning verification off: pass the DER of the CA that signs your
host's certificate (export it from a browser). It has to be 1334 bytes or
fewer, the size of the certificate already in the binary.

IPS offsets are relative to the start of the DECOMPRESSED .code, which is what
Luma3DS and Azahar patch - the same thing as an offset into code_dec.bin, and
as a virtual address minus 0x00100000.

    python3 tools/mkpatch.py extracted/base/code_dec.bin out/code.ips \\
            --host colos.asahina.net
"""
import argparse, os, sys

OLD = b'https://la1.denpamen.com/'
CERT_CN = b'la1.denpamen.com'
MAX_CERT = 0x536          # the size of the certificate the game ships with


def find_cert(data):
    """(file offset, length) of the embedded DER certificate."""
    import re
    for m in re.finditer(rb'\x30\x82(..)\x30\x82', data, re.S):
        off = m.start()
        ln = int.from_bytes(data[off + 2:off + 4], 'big') + 4
        if 300 < ln < 4000 and off + ln <= len(data) and CERT_CN in data[off:off + ln]:
            return off, ln
    return None, None


def find_len_word(data, cert_off, cert_len, base=0x00100000):
    """Where the binary stores that certificate's length.

    The getter pair is `return <pointer>` / `return <length>`, so the pointer
    to the certificate and its length sit in two nearby literal pools. Find
    the word holding the pointer, then the word holding the length closest to
    it.
    """
    import struct
    va = cert_off + base
    ptr_sites = [i for i in range(0, len(data) - 3, 4)
                 if struct.unpack_from('<I', data, i)[0] == va]
    len_sites = [i for i in range(0, len(data) - 3, 4)
                 if struct.unpack_from('<I', data, i)[0] == cert_len]
    if not ptr_sites or not len_sites:
        return None, None
    best = min(((abs(l - p), p, l) for p in ptr_sites for l in len_sites),
               key=lambda t: t[0])
    return best[1], best[2]


def build_records(data, old, new):
    assert len(old) == len(new), 'replacement must be the same length'
    out, at = [], 0
    while True:
        i = data.find(old, at)
        if i < 0:
            return out
        out.append((i, new))
        at = i + len(old)


def ips(records):
    blob = bytearray(b'PATCH')
    for off, payload in records:
        if off > 0xFFFFFF:
            raise ValueError(f'offset {off:#x} does not fit in IPS (16 MB limit)')
        blob += off.to_bytes(3, 'big') + len(payload).to_bytes(2, 'big') + payload
    blob += b'EOF'
    return bytes(blob)


def apply_ips(data, patch):
    """Reference implementation, used to verify what we just produced."""
    assert patch[:5] == b'PATCH'
    out = bytearray(data)
    p = 5
    while True:
        if patch[p:p + 3] == b'EOF':
            return bytes(out)
        off = int.from_bytes(patch[p:p + 3], 'big'); p += 3
        size = int.from_bytes(patch[p:p + 2], 'big'); p += 2
        if size == 0:                       # RLE record
            rle = int.from_bytes(patch[p:p + 2], 'big'); p += 2
            val = patch[p]; p += 1
            out[off:off + rle] = bytes([val]) * rle
        else:
            out[off:off + size] = patch[p:p + size]; p += size


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('code', help='decompressed .code (code_dec.bin)')
    ap.add_argument('out', help='where to write the .ips')
    ap.add_argument('--host', default='colos.asahina.net',
                    help='your host; must make the URL exactly 25 bytes')
    ap.add_argument('--scheme', default='https', choices=['http', 'https'])
    ap.add_argument('--cert', help='DER of the CA to pin instead (<= 1334 bytes)')
    a = ap.parse_args()

    new = f'{a.scheme}://{a.host}/'.encode()
    if len(new) != len(OLD):
        sys.exit(f'{new.decode()!r} is {len(new)} bytes, needs to be {len(OLD)}; '
                 f'the host part has to be {len(OLD) - len(a.scheme) - 4} characters')

    data = open(a.code, 'rb').read()
    recs = build_records(data, OLD, new)
    if not recs:
        sys.exit('no endpoint strings found in that file')
    n_url = len(recs)

    if a.cert:
        der = open(a.cert, 'rb').read()
        if len(der) > MAX_CERT:
            sys.exit(f'that certificate is {len(der)} bytes; the slot holds '
                     f'{MAX_CERT}. Use the CA\'s DER, not a chain.')
        cert_off, cert_len = find_cert(data)
        if cert_off is None:
            sys.exit('could not find the embedded certificate')
        ptr_site, len_site = find_len_word(data, cert_off, cert_len)
        if len_site is None:
            sys.exit('found the certificate but not the word holding its length')
        recs.append((cert_off, der.ljust(MAX_CERT, b'\0')))
        recs.append((len_site, len(der).to_bytes(4, 'little')))
        print(f'  certificate slot at {cert_off:#08x} '
              f'(VA {cert_off + 0x00100000:#010x}), {cert_len} -> {len(der)} bytes')
        print(f'  length word at {len_site:#08x} '
              f'(VA {len_site + 0x00100000:#010x})')
    patch = ips(recs)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, 'wb').write(patch)

    patched = apply_ips(data, patch)
    assert len(patched) == len(data), 'patch changed the file length'
    diff = [i for i in range(len(data)) if data[i] != patched[i]]
    print(f'{os.path.basename(a.code)}: {n_url} endpoint strings'
          + (f' + certificate' if a.cert else '')
          + f' -> {a.out} ({len(patch)} bytes)')
    print(f'  replaced {OLD.decode()} with {new.decode()}')
    print(f'  bytes changed: {len(diff)}')
    print(f'  old URL remaining: {patched.count(OLD)}, '
          f'new URL present: {patched.count(new)}')
    assert patched.count(OLD) == 0, 'an endpoint string survived'
    assert patched.count(new) == n_url, 'not every endpoint string was replaced'
    if a.cert:
        import struct
        got = struct.unpack_from('<I', patched, len_site)[0]
        print(f'  certificate in place: {patched[cert_off:cert_off+2].hex()}... '
              f'length word now {got} (was {cert_len})')
        assert patched[cert_off:cert_off + len(der)] == der, 'certificate mismatch'
        assert got == len(der), 'length word not updated'
    for off, _ in recs[:3]:
        print(f'  e.g. offset {off:#08x} (VA {off + 0x00100000:#010x})')


if __name__ == '__main__':
    main()
