#!/usr/bin/env python3
"""Export the game's reference data as JSON: ids, names and descriptions.

Every table shares the layout in docs/04, and the strings its records point at
live in the table's own pool, so a record's name is just a pool offset. That
makes an id -> name index possible for anything the game names: items, skills,
monsters, the denpa name pool, equipment categories.

A save editor needs exactly this to show something other than raw numbers, and
it is also the dataset behind any kind of in-game encyclopedia.

    python3 tools/dbexport.py extracted/update_romfs out/db
"""
import glob, json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmarc import Archive, table_header
from gsmsg import decode, is_message_table

# table -> how many leading u32 slots to try as string pointers
WANT = {
    'ItemData': 2, 'SkillData': 4, 'MonsterParameter': 4, 'MessageDenpaName': 0,
    'ConditionData': 2, 'DenpaCustom': 2, 'EquipInfo': 2, 'LotRareDenpa': 2,
    'ColosseumDenpa': 3, 'ColosseumDenpaTeam': 2, 'CounterStop': 0,
    'LevelStatusData': 0, 'ParameterCap': 0, 'LevelData': 0,
}


def utf16_at(data, off, limit):
    end = off
    while end + 1 < limit and data[end:end + 2] != b'\0\0':
        end += 2
    try:
        return data[off:end].decode('utf-16-le')
    except UnicodeDecodeError:
        return ''


def tables(romfs):
    for p in sorted(glob.glob(os.path.join(romfs, '*'))):
        b = os.path.basename(p)
        if len(b) != 8 or any(c not in '0123456789ABCDEF' for c in b):
            continue
        a = Archive(p)
        for s in a.sections:
            z = a.zip(s)
            blobs = ([(i.filename, z.read(i)) for i in z.infolist()
                      if i.filename.endswith(('.bin', '.dat'))] if z
                     else [(None, a.payload(s)[0])])
            for fn, d in blobs:
                if len(d) < 0x44:
                    continue
                h = table_header(d)
                if h['valid']:
                    yield b, fn, h, d


def export_messages(h, d):
    """Message tables address their text by (start, end) instead of a pool
    pointer, so they are decoded with the message reader - that also strips the
    ruby control codes and gives both the kanji and the kana form."""
    ids = (struct.unpack_from(f"<{h['count']}I", d, h['b2_off'])
           if h['b2_size'] == h['count'] * 4 else None)
    pool_end = h['pool_off'] + h['pool_size']
    out = []
    for i in range(h['count']):
        # (start, end) are the first two words whatever the record length is:
        # the name pool uses 8-byte records, the dialogue tables 12.
        start, end = struct.unpack_from('<2I', d, h['rec_off'] + i * h['rec_size'])
        if not (h['pool_off'] <= start <= end <= pool_end):
            continue
        kanji, kana, _ = decode(d[start:end])
        # the slice includes the terminating NUL pair, and .strip() keeps it
        kanji = kanji.replace('\0', '').strip()
        kana = kana.replace('\0', '').strip()
        out.append(dict(index=i,
                        id=(ids[i] & 0x7FFFFFFF) if ids and i < len(ids) else i,
                        name=kanji,
                        text=[kana] if kana != kanji else [],
                        raw=''))
    return out


def export(h, d, slots):
    """[{id, index, name, text:[...], raw}] for one table."""
    lim = h['pool_off'] + h['pool_size']
    ids = (struct.unpack_from(f"<{h['count']}I", d, h['b2_off'])
           if h['b2_size'] == h['count'] * 4 else None)
    out = []
    for i in range(h['count']):
        rec = d[h['rec_off'] + i * h['rec_size']:
                h['rec_off'] + (i + 1) * h['rec_size']]
        texts = []
        for k in range(min(slots, h['rec_size'] // 4)):
            v = struct.unpack_from('<I', rec, k * 4)[0]
            if h['pool_off'] <= v < lim:
                t = utf16_at(d, v, lim).strip()
                if t:
                    texts.append(t)
        out.append(dict(index=i,
                        id=(ids[i] & 0x7FFFFFFF) if ids else i,
                        name=texts[0] if texts else '',
                        text=texts[1:],
                        raw=rec.hex()))
    return out


def main():
    romfs, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    seen, total = {}, 0
    for arc, fn, h, d in tables(romfs):
        slots = WANT.get(h['name'])
        if slots is None:
            continue
        key = f"{h['name']}{'-' + fn[:-4] if fn and h['name'] in ('EquipInfo', 'LotRareDenpa', 'ColosseumDenpaTeam') else ''}"
        if key in seen:
            continue
        rows = (export_messages(h, d) if is_message_table(h['name'])
                else export(h, d, slots))
        seen[key] = len(rows)
        total += len(rows)
        json.dump(dict(table=h['name'], archive=arc, file=fn,
                       record_size=h['rec_size'], rows=rows),
                  open(os.path.join(outdir, key + '.json'), 'w'),
                  ensure_ascii=False, indent=1)
    for k in sorted(seen):
        print(f'  {seen[k]:>5}  {k}.json')
    print(f'{len(seen)} tables, {total} records -> {outdir}')


if __name__ == '__main__':
    main()
