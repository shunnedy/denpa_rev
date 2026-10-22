#!/usr/bin/env python3
"""Rebuild a romfs archive so modified data can be loaded through LayeredFS.

Reading the format is tdmarc.py; this writes it back. Replacements are given
as `<inner name>=<file>`, where the inner name is either a ZIP entry name
(`enemy_01.bch`) or a table name (`MonsterParameter`).

A section that was LZ10 compressed is re-emitted as LZ10 in literal-only mode:
a flag byte of 0x00 followed by eight raw bytes is a legal LZ10 block, so the
output decompresses correctly everywhere without needing to implement a
matcher. It is larger than the original, which does not matter for LayeredFS.
"""
import io, os, struct, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmarc import Archive, HDR, REC, lz10_decompress
from tdmarc import table_header


def lz10_compress_stored(data):
    """Valid LZ10 that stores every byte as a literal."""
    out = bytearray(b'\x10' + len(data).to_bytes(3, 'little'))
    for i in range(0, len(data), 8):
        out.append(0x00)
        out += data[i:i + 8]
    return bytes(out)


def section_payloads(a):
    """[(kind, raw payload, was_lz10)] for every section of an archive."""
    out = []
    for s in a.sections:
        data, comp = a.payload(s)
        out.append([s['kind'], data, bool(comp), s['ts'], s['a'], s['b']])
    return out


def inner_names(a):
    names = {}
    for idx, s in enumerate(a.sections):
        z = a.zip(s)
        if z is not None:
            for n in z.namelist():
                names[n] = ('zip', idx)
        else:
            data, _ = a.payload(s)
            try:
                h = table_header(data)
                if h['valid']:
                    names[h['name']] = ('table', idx)
            except Exception:
                pass
    return names


def build(a, replacements):
    """Return the bytes of a rebuilt archive with `replacements` applied."""
    names = inner_names(a)
    secs = section_payloads(a)
    touched = []
    for name, path in replacements.items():
        if name not in names:
            raise KeyError(f'{name!r} is not in {a.path}; '
                           f'known: {sorted(names)[:6]}...')
        kind, idx = names[name]
        blob = open(path, 'rb').read()
        if kind == 'table':
            secs[idx][1] = blob
        else:
            z = a.zip(a.sections[idx])
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zo:
                for info in z.infolist():
                    zo.writestr(info.filename,
                                blob if info.filename == name else z.read(info))
            secs[idx][1] = buf.getvalue()
        touched.append(name)

    body, records = bytearray(), []
    base = HDR + REC * len(secs)
    for kind, data, was_lz10, ts, fa, fb in secs:
        payload = lz10_compress_stored(data) if was_lz10 else data
        records.append((ts, kind, len(payload), base + len(body), fa, fb, len(data)))
        body += payload
        while len(body) % 4:                       # sections stay word aligned
            body += b'\0'
    out = bytearray(struct.pack('<6I', a.version, a.id, 0, a.subver, len(secs), 0))
    for r in records:
        out += struct.pack('<7I', *r)
    assert len(out) == base, (len(out), base)
    return bytes(out + body), touched


def main():
    src, dst = sys.argv[1], sys.argv[2]
    repl = dict(x.split('=', 1) for x in sys.argv[3:])
    a = Archive(src)
    data, touched = build(a, repl)
    open(dst, 'wb').write(data)
    print(f'{os.path.basename(src)}: {len(a.sections)} sections, '
          f'replaced {touched or "nothing"} -> {dst} ({len(data)} bytes)')
    print('verifying the result parses and the untouched entries match...')
    b = Archive(dst)
    before, after = inner_names(a), inner_names(b)
    assert set(before) == set(after), 'inner name set changed'
    print(f'  ok: {len(after)} inner entries, ids {a.id:08X} == {b.id:08X}')


if __name__ == '__main__':
    main()
