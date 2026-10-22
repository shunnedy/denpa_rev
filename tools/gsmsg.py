#!/usr/bin/env python3
"""Decode Genius Sonority message tables (Message*, *_msg) out of a romfs archive.

Message tables use the ordinary table layout (see tdmarc.table_header). Each
record is (start, end, flags) with byte offsets into the blob, delimiting one
message - the text is NOT NUL terminated, which is why the explicit end offset
is there.

Text is UTF-16LE. A control code is three UTF-16 units: U+0001, an opcode
character, and a u16 argument.

  opcode  meaning
  '8'     start of a ruby base (kanji)
  '9'     start of the reading (kana)
  ':'     end of ruby
  '"'     page / text-box break
  '7'     insert text from another table. The argument is the number of
          items that follow; each item starts with a u16 type:
            type 3 = u16 length (in u16 units) + inline ASCII string
            type 2 = u16 value + u16 flag
          e.g. ["MessageMapName", 15, "message"] = substitute entry 15 of
          MessageMapName's "message" group (a map name) at this position
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmarc import Archive, table_header

ESC = 0x0001
RUBY_BASE, RUBY_READ, RUBY_END, BREAK, INSERT = 0x38, 0x39, 0x3A, 0x22, 0x37


def units(blob):
    return [struct.unpack_from('<H', blob, i)[0]
            for i in range(0, len(blob) - 1, 2)]


def decode(blob):
    """Return (kanji form, kana form, list of inserted table references)."""
    u = units(blob)
    kanji, kana, refs = [], [], []
    i, mode = 0, 'both'
    while i < len(u):
        if u[i] == ESC and i + 2 < len(u):
            op, arg = u[i + 1], u[i + 2]
            i += 3
            if op == RUBY_BASE:
                mode = 'kanji'
            elif op == RUBY_READ:
                mode = 'kana'
            elif op == RUBY_END:
                mode = 'both'
            elif op == BREAK:
                kanji.append('\n'); kana.append('\n')
            elif op == INSERT:
                item = []
                for _ in range(arg):
                    if i >= len(u):
                        break
                    kind = u[i]; i += 1
                    if kind == 3 and i < len(u):
                        ln = u[i]; i += 1
                        raw = b''.join(struct.pack('<H', x) for x in u[i:i + ln])
                        item.append(raw.split(b'\0', 1)[0].decode('ascii', 'replace'))
                        i += ln
                    elif kind == 2 and i + 1 < len(u):
                        item.append(str(u[i])); i += 2
                    else:
                        break
                refs.append('/'.join(item))
                kanji.append('{%s}' % refs[-1])
                kana.append('{%s}' % refs[-1])
            continue
        c = chr(u[i]); i += 1
        if mode in ('both', 'kanji'):
            kanji.append(c)
        if mode in ('both', 'kana'):
            kana.append(c)
    return ''.join(kanji), ''.join(kana), refs


def messages(data):
    """Yield (index, kanji, kana, refs) for a message table blob."""
    h = table_header(data)
    if h['rec_size'] < 12:
        return
    for i in range(h['count']):
        start, end, flags = struct.unpack_from('<3I', data, h['rec_off'] + i * h['rec_size'])
        if not (h['pool_off'] <= start <= end <= h['pool_off'] + h['pool_size']):
            continue
        k, y, r = decode(data[start:end])
        yield i, k, y, r


def is_message_table(name):
    return name.startswith('Message') or name.endswith('_msg')


if __name__ == '__main__':
    a = Archive(sys.argv[1])
    want = sys.argv[2] if len(sys.argv) > 2 else None
    for s in a.sections:
        if a.zip(s) is not None:
            continue
        data, _ = a.payload(s)
        if len(data) < 0x44:
            continue
        h = table_header(data)
        if not h['valid'] or not is_message_table(h['name']):
            continue
        if want and h['name'] != want:
            continue
        print(f"== {h['name']}  ({h['count']} records, section {s['i']})")
        for i, k, y, r in messages(data):
            if k.strip():
                print(f'  [{i}] {k}')
