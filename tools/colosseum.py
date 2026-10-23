#!/usr/bin/env python3
"""Build Wi-Fi Colosseum opponent data for 電波人間のRPG FREE!

The game never uploads a party (no HTTP POST exists in the binary): Wi-Fi
Colosseum works by DOWNLOADING opponents from `gameserver?req=rand3` and
fighting them locally. Each opponent is two base64 fields — a 32-byte name and
a 1256-byte party blob — copied into a 1288-byte entry and then handed to the
battle setup (docs/13, docs/20).

The party blob is the exact structure the game's own fallback generator
(`FUN_001e8a04`) writes and its loader (`FUN_00186140`) reads back:

    0x000  u32   active denpa count (the generator writes 3)
    0x004  u32   0
    0x018  8 x 148-byte denpa slots  (FUN_00295aa4 packs a 252-byte record)
    0x4bc  20B   representative name block (copied from a name-table record)
    0x4d0  u32   random team id
    0x4d4  20B   (zero)

A 148-byte slot is a repacked denpa record. HP / AP / EXP / timestamps are NOT
carried — the battle recomputes stats from level + antenna + appearance (the
formula in docs/19), so an opponent is fully described by its genotype, level,
bonuses and equipment. That means any record from a save (tools/denpaedit.py)
can be served as an opponent.

    # serve your own party as the opponent
    python3 tools/colosseum.py from-save savedata.bin --slots p0,p1,p2 -o party.blob
    # pack explicit 252-byte records
    python3 tools/colosseum.py pack a.denpa.bin b.denpa.bin -o party.blob
    # verify the pack/unpack round-trips every field
    python3 tools/colosseum.py selftest savedata.bin
"""
import argparse, os, struct, sys

REC = 0xFC
SLOT = 0x94          # 148
BLOB = 0x4E8         # 1256
SLOT0 = 0x18         # first denpa slot
TEMPLATE_OFF = 0x4BC  # word 0x12f: representative name block (20 bytes)
TEAMID_OFF = 0x4D0    # word 0x134

# (record offset, slot offset, length) — the field map of FUN_00295aa4,
# which equals FUN_00186140 read in reverse.
FIELDS = [
    (0x04, 0x00, 4),    # =1
    (0x08, 0x04, 4),    # creation timestamp
    (0x14, 0x08, 24),   # name + reading block
    (0x4c, 0x20, 20),   # owner name
    (0x60, 0x34, 22),   # appearance genetics
    (0x76, 0x4a, 1),    # sex / name group
    (0x77, 0x4b, 1),    # voice type
    (0x82, 0x4c, 1),    # generation
    (0x84, 0x4d, 1),    # breed / child flags
    (0x94, 0x4e, 1),    # antenna group
    (0x95, 0x4f, 1),    # antenna tier
    (0x96, 0x50, 2),    # level
    (0x9c, 0x52, 2),    # form / transform target
    (0x9e, 0x54, 1),    # growth type (low nibble significant)
    (0x83, 0x55, 1),    # max generation
    (0xa0, 0x56, 6),    # this-generation stat bonus
    (0xa6, 0x5c, 6),    # permanent stat bonus
    (0xac, 0x64, 32),   # equipment, 8 x u32
    (0xec, 0x84, 16),   # tail
]


def pack_denpa(rec):
    """252-byte record -> 148-byte colosseum slot (FUN_00295aa4)."""
    if len(rec) < REC:
        raise ValueError('record too short')
    slot = bytearray(SLOT)
    for ro, so, n in FIELDS:
        slot[so:so + n] = rec[ro:ro + n]
    return bytes(slot)


def unpack_denpa(slot):
    """148-byte slot -> partial 252-byte record (FUN_00186140). HP/AP/EXP and
    timestamps are not present; everything else is restored verbatim."""
    rec = bytearray(REC)
    for ro, so, n in FIELDS:
        rec[ro:ro + n] = slot[so:so + n]
    # note: the loader (FUN_0023c8a8) forces the kind nibble at +0x06 to 6
    # ("external data") after reading the slot; the slot itself preserves the
    # source record's +0x04..+0x07 verbatim, so this is a pure inverse.
    return bytes(rec)


def pack_party(records, team_id=0x12345678):
    """Up to 8 records -> 1256-byte party blob."""
    recs = [r for r in records][:8]
    if not recs:
        raise ValueError('need at least one denpa')
    blob = bytearray(BLOB)
    struct.pack_into('<I', blob, 0, len(recs))      # active count
    # fill all 8 slots the way the game does; cycle the party for the spares
    for i in range(8):
        slot = pack_denpa(recs[i] if i < len(recs) else recs[i % len(recs)])
        blob[SLOT0 + i * SLOT:SLOT0 + (i + 1) * SLOT] = slot
    # representative name block = first denpa's name block (20 bytes)
    blob[TEMPLATE_OFF:TEMPLATE_OFF + 20] = recs[0][0x14:0x14 + 20]
    struct.pack_into('<I', blob, TEAMID_OFF, team_id & 0xffffffff)
    return bytes(blob)


def records_from_save(path, slots=None):
    """Pull 252-byte records out of a save. slots like 'p0,p1,b3'; default =
    the whole party (non-empty p0..p15)."""
    buf = open(path, 'rb').read()
    party = struct.unpack_from('<II', buf, 0x14 + 8 * 5)
    box = struct.unpack_from('<II', buf, 0x14 + 8 * 6)
    spare = struct.unpack_from('<II', buf, 0x14 + 8 * 7)
    areas = {'p': party, 'b': box, 'x': spare}

    def rec(spec):
        off, size = areas[spec[0]]
        i = int(spec[1:])
        return buf[off + i * REC:off + (i + 1) * REC]

    if slots:
        return [rec(s) for s in slots.split(',')]
    off, size = party
    out = []
    for i in range(size // REC):
        r = buf[off + i * REC:off + (i + 1) * REC]
        if struct.unpack_from('<I', r, 0)[0]:
            out.append(r)
    return out


def team_name_field(name):
    """32-byte name field (the A field of rand3): UTF-16LE, NUL padded."""
    return name.encode('utf-16-le')[:0x20].ljust(0x20, b'\0')


def selftest(save):
    recs = records_from_save(save)
    assert recs, 'no party denpa'
    ok = 0
    for r in recs:
        slot = pack_denpa(r)
        assert len(slot) == SLOT
        back = unpack_denpa(slot)
        for ro, so, n in FIELDS:
            assert back[ro:ro + n] == r[ro:ro + n], f'field {ro:#x} lost'
        ok += len(FIELDS)
    blob = pack_party(recs)
    assert len(blob) == BLOB, len(blob)
    assert struct.unpack_from('<I', blob, 0)[0] == min(len(recs), 8)
    # every slot deserialises to the right denpa
    for i in range(8):
        slot = blob[SLOT0 + i * SLOT:SLOT0 + (i + 1) * SLOT]
        src = recs[i] if i < len(recs) else recs[i % len(recs)]
        assert unpack_denpa(slot)[0x96:0x98] == src[0x96:0x98]
        ok += 1
    print(f'selftest OK: {ok} checks, {len(recs)} denpa, blob {len(blob)} bytes')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('from-save'); s.add_argument('save'); s.add_argument('--slots'); s.add_argument('-o', required=True); s.add_argument('--name')
    p = sub.add_parser('pack'); p.add_argument('records', nargs='+'); p.add_argument('-o', required=True)
    t = sub.add_parser('selftest'); t.add_argument('save')
    a = ap.parse_args()
    if a.cmd == 'selftest':
        selftest(a.save)
    elif a.cmd == 'from-save':
        recs = records_from_save(a.save, a.slots)
        open(a.o, 'wb').write(pack_party(recs))
        print(f'{len(recs)} denpa -> {a.o} ({BLOB} bytes)')
    elif a.cmd == 'pack':
        recs = [open(r, 'rb').read() for r in a.records]
        open(a.o, 'wb').write(pack_party(recs))
        print(f'{len(recs)} denpa -> {a.o} ({BLOB} bytes)')


if __name__ == '__main__':
    main()
