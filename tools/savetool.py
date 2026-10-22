#!/usr/bin/env python3
"""Locate structures inside a 電波人間のRPG FREE! save file.

There is no documented save layout, so this works the way save editors are
normally bootstrapped: take what the ROM tells us and look for it in the save.

  strings   UTF-16LE text in the save - player and denpa names show up here
  names     names that also exist in the game's name pool (MessageDenpaName),
            which is how the generated denpa are named, so a hit is very
            likely an actual party/roster entry
  value     every offset holding a given number as u8/u16/u32 - point it at
            your gold, level or item count to find that field
  stats     runs of six 16-bit values in a plausible range: the game's stats
            are HP / AP / attack / defence / speed / evasion, and
            LevelStatusData stores them exactly that way
  items     runs of plausible item ids (checked against ItemData)
  diff      changed ranges between two saves - do one thing in game, save,
            and the field you touched is in the output

Azahar keeps savegames as plain files, so point this straight at the file.
A save pulled off hardware is wrapped in a DISA container; extract it first
(any 3DS save manager does this) - this tool does not parse DISA.

    python3 tools/savetool.py names save.bin --db out/db
    python3 tools/savetool.py value save.bin 123456
    python3 tools/savetool.py diff before.bin after.bin
"""
import argparse, json, os, struct, sys


def load_names(dbdir):
    path = os.path.join(dbdir, 'MessageDenpaName.json')
    if not os.path.exists(path):
        return set()
    rows = json.load(open(path))['rows']
    return {r['name'] for r in rows if 1 < len(r['name']) <= 10}


def load_item_ids(dbdir):
    path = os.path.join(dbdir, 'ItemData.json')
    if not os.path.exists(path):
        return set()
    return {r['id'] for r in json.load(open(path))['rows']}


def utf16_strings(data, minlen=2):
    out, i = [], 0
    while i + 1 < len(data):
        if data[i + 1] in (0x30, 0x4E, 0x5F, 0x60, 0x62, 0x66, 0x67, 0x80,
                           0x82, 0x8A, 0x90, 0x97, 0x9A, 0xFF, 0x00):
            j = i
            while j + 1 < len(data):
                cu = struct.unpack_from('<H', data, j)[0]
                if not (0x20 <= cu <= 0xFFFD) or cu == 0:
                    break
                j += 2
            if (j - i) // 2 >= minlen:
                try:
                    s = data[i:j].decode('utf-16-le')
                    if sum(1 for c in s if c.isprintable()) == len(s):
                        out.append((i, s))
                except UnicodeDecodeError:
                    pass
                i = j
                continue
        i += 2
    return out


def find_value(data, value):
    hits = []
    for width, fmt in ((1, 'B'), (2, '<H'), (4, '<I')):
        if value >= (1 << (width * 8)):
            continue
        packed = struct.pack(fmt, value)
        at = data.find(packed)
        while at >= 0:
            hits.append((at, width))
            at = data.find(packed, at + 1)
    return hits


def find_stat_runs(data, lo=1, hi=9999, count=6, stride=2):
    """Six consecutive u16 all inside a plausible stat range."""
    out = []
    for off in range(0, len(data) - count * stride, stride):
        vals = struct.unpack_from(f'<{count}H', data, off)
        if all(lo <= v <= hi for v in vals) and len(set(vals)) >= 3:
            out.append((off, vals))
    return out


def find_item_runs(data, item_ids, run=4):
    out = []
    for off in range(0, len(data) - run * 2, 2):
        vals = struct.unpack_from(f'<{run}H', data, off)
        if all(v in item_ids and v != 0 for v in vals):
            out.append((off, vals))
    return out


def diff(a, b):
    ranges, start = [], None
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            if start is None:
                start = i
        elif start is not None:
            ranges.append((start, i))
            start = None
    if start is not None:
        ranges.append((start, min(len(a), len(b))))
    merged = []
    for s, e in ranges:
        if merged and s - merged[-1][1] <= 4:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('cmd', choices=['strings', 'names', 'value', 'stats',
                                    'items', 'diff'])
    ap.add_argument('save')
    ap.add_argument('arg', nargs='?')
    ap.add_argument('--db', default='out/db', help='dbexport.py output')
    ap.add_argument('--limit', type=int, default=40)
    a = ap.parse_args()
    data = open(a.save, 'rb').read()
    print(f'{os.path.basename(a.save)}: {len(data)} bytes ({len(data)/1024:.0f} KiB)')

    if a.cmd == 'strings':
        for off, s in utf16_strings(data)[:a.limit]:
            print(f'  {off:#08x}  {s!r}')
    elif a.cmd == 'names':
        pool = load_names(a.db)
        if not pool:
            sys.exit(f'no usable names in {a.db}/MessageDenpaName.json '
                     f'- run dbexport.py against the romfs first')
        hits = [(o, s) for o, s in utf16_strings(data) if s in pool]
        print(f'  name-pool matches: {len(hits)} (pool holds {len(pool)} names)')
        for off, s in hits[:a.limit]:
            print(f'  {off:#08x}  {s}')
        if len(hits) > 1:
            d = [hits[i + 1][0] - hits[i][0] for i in range(len(hits) - 1)]
            common = max(set(d), key=d.count)
            print(f'  most common spacing: {common} bytes'
                  f' ({d.count(common)}/{len(d)} gaps) <- likely the record stride')
    elif a.cmd == 'value':
        v = int(a.arg, 0)
        hits = find_value(data, v)
        print(f'  {v} appears {len(hits)} times')
        for off, w in hits[:a.limit]:
            print(f'  {off:#08x}  as u{w * 8}')
    elif a.cmd == 'stats':
        runs = find_stat_runs(data)
        print(f'  six-u16 candidate runs: {len(runs)}')
        for off, vals in runs[:a.limit]:
            print(f'  {off:#08x}  {vals}')
    elif a.cmd == 'items':
        ids = load_item_ids(a.db)
        if not ids:
            sys.exit(f'no ItemData.json under {a.db}')
        runs = find_item_runs(data, ids)
        print(f'  item-id runs: {len(runs)}')
        for off, vals in runs[:a.limit]:
            print(f'  {off:#08x}  {vals}')
    elif a.cmd == 'diff':
        other = open(a.arg, 'rb').read()
        rs = diff(data, other)
        print(f'  changed ranges: {len(rs)}'
              f' ({sum(e - s for s, e in rs)} bytes)')
        for s, e in rs[:a.limit]:
            print(f'  {s:#08x}-{e:#08x} ({e - s}B)  '
                  f'{data[s:e][:12].hex()} -> {other[s:e][:12].hex()}')


if __name__ == '__main__':
    main()
