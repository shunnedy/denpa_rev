#!/usr/bin/env python3
"""Self-test for denpaedit.py against a real v1.17.0 save.

The save is not in the repository; point DENPA_SAVE at one. The checks use the
four denpa whose in-game status screens were transcribed (docs/19): the stat
formula must reproduce them, the appearance hash must match, and every edit
must round-trip and leave the rest of the file untouched.

    DENPA_SAVE=savedata3.bin python3 tools/test_denpaedit.py
"""
import os, sys, tempfile, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import denpaedit as E

SAVE = os.environ.get('DENPA_SAVE')
if not SAVE:
    print('DENPA_SAVE not set - skipped'); sys.exit(0)
DICT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'denpa-dict.json')
dic = E.Dict(DICT)
sv = E.Save(SAVE, dic)
ok = 0

def check(cond, msg):
    global ok
    if not cond:
        raise SystemExit(f'FAIL: {msg}')
    ok += 1

# transcribed status screens: (slot, name, level, exp, HP, AP, atk, def, spd, eva, antenna, gen, maxgen, happy)
KNOWN = [('p0', 'かげとら', 5, 158, 64, 18, None, 14, 7, 6, 'ちょっとふっかつ', 1, 7, 3),      # atk has +equipment
         ('p1', 'かぐら', 50, 814127, 354, 48, 74, 74, 69, 6, 'すこしわざアップ', 3, 6, 0),
         ('b0', 'きわむ', 50, 838798, 566, 51, 99, 86, 70, 3, 'アンテナふうじ', 3, 6, 0),
         ('b1', 'ゆうき', 50, 822351, 489, 73, 92, 84, None, 6, 'みんなちょっとふっかつ', 3, 6, 0)]
for slot, name, lv, exp, *st, ant, gen, maxgen, happy in KNOWN:
    d = sv.slot(slot)
    check(d.name() == name, f'{slot} name {d.name()!r}')
    check(d.level == lv and d.u32(0x98) == exp, f'{slot} level/exp')
    check(d.u16(0x78) == st[0] and d.u8(0x7a) == st[1], f'{slot} hp/ap')
    calc = d.stats()
    for k, want in enumerate(st):
        if want is not None:
            check(calc[k] == want, f'{slot} stat {E.STAT_NAMES[k]} calc {calc[k]} want {want}')
    check(dic.groups[d.u8(0x94)]['display'] == ant, f'{slot} antenna')
    check(d.gen + 1 == gen and d.u8(0x83) + 1 == maxgen, f'{slot} generation')
    check(d.u16(0x80) == happy, f'{slot} happiness')
    check(d.u8(0x95) == d.antenna_tier(), f'{slot} antenna tier stored {d.u8(0x95)}')
    tier = d.u8(0x95)
    g = dic.groups[d.u8(0x94)]
    check(d.u16(0x62) == (g['tiers'][tier - 1]['skill_id'] if tier else 1), f'{slot} current skill')
    if d.kind in E.HASH_KINDS:
        check(d.u16(0x60) == d.appearance_hash(), f'{slot} appearance hash')
print(f'known denpa: {ok} checks passed')

# happiness max per generation (status screen shows 3/20 and 0/50)
check(dic.d['parameter_cap'][0]['happy_max'] == 20 and dic.d['parameter_cap'][2]['happy_max'] == 50, 'happy max')
# level cap 50 for 3rd generation (the three Lv50 denpa sit at the cap with surplus exp)
check(dic.d['parameter_cap'][2]['level_cap'] == 50, 'level cap')
# element affinity of white and black/white mix
d = sv.slot('p0')
bc = dic.body_color(d.u8(0x71), d.u8(0x72))
check(bc['elements'][6] == 2 and bc['elements'][7] == -2, 'しろ = 光+2 闇-2')
bc = dic.body_color(sv.slot('b1').u8(0x71), sv.slot('b1').u8(0x72))
check(bc['elements'][6] == 1, 'くろ+しろ = 光+1')
# inventory
items = dict(sv.items())
check(items.get(1850) == 1 and items.get(1) == 1, f'inventory {items}')
# voice generation reproduces the stored voice of a known name
check(dic.voice('かげとら') == d.voice(), f'voice {dic.voice("かげとら").hex()} vs {d.voice().hex()}')

# ---- edits round-trip and touch only the record
orig = bytes(sv.buf)
d = sv.slot('p1')
E.set_field(d, 'level', '30')
check(d.level == 30 and d.u32(0x98) == dic.d['level_exp'][29], 'set level')
check(d.u8(0x95) == 0 and d.u16(0x62) == 1, 'tier recomputed')
E.set_field(d, 'antenna', 'ちょっとふっかつ')
check(d.u8(0x94) == 9 and d.u8(0x95) == 1 and d.u16(0x62) == 29, 'antenna set + skill')
E.set_field(d, 'colora', 'むらさき')
E.set_field(d, 'colorb', 'きん')
check(d.u8(0x71) == 27 and d.u8(0x72) == 33 and d.u8(0x70) == 1, 'colours')
E.set_field(d, 'name', 'たろう')
check(d.name() == 'たろう' and d.voice() == bytes.fromhex('c0dbb0'), f'name/voice {d.voice().hex()}')
E.set_field(d, 'equip1', 'ちからのうでわ')
check(d.u32(0xb0) == 0x8000073a, 'equip')
E.set_field(d, 'equip1', 'none')
check(d.u32(0xb0) == 0, 'unequip')
E.set_field(d, 'gen', '1')
check(d.gen == 0 and d.u8(0x83) >= 0, 'gen')
diff = [i for i in range(len(orig)) if orig[i] != sv.buf[i]]
check(all(d.base <= i < d.base + E.REC for i in diff), 'edits confined to the record')

# ---- new denpa from template, copy, delete
sv = E.Save(SAVE, dic)
d2 = sv.slot('b5')
check(d2.empty, 'b5 empty')
d2.buf[d2.base:d2.base + E.REC] = sv.slot('b0').raw()
d2.w32(0, sv.next_instance())
E.set_field(d2, 'name', 'コピー')
E.set_field(d2, 'level', '50')
check(d2.stats() == sv.slot('b0').stats(), 'copy keeps computed stats')
check(d2.u32(0) == 5, 'fresh instance id')
d2.buf[d2.base:d2.base + E.REC] = bytes(E.REC)
check(sv.slot('b5').empty, 'delete')

# ---- blank new denpa via the CLI
with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, 'o.bin')
    r = subprocess.run([sys.executable, E.__file__, SAVE, 'new', 'b9', 'name=てすと', 'level=15',
                        'antenna=すこしわざアップ', 'colora=あか', '--out', out, '--dict', DICT],
                       capture_output=True, text=True)
    check(r.returncode == 0, r.stderr)
    sv2 = E.Save(out, dic)
    d3 = sv2.slot('b9')
    check(d3.name() == 'てすと' and d3.level == 15 and d3.u8(0x94) == 107, 'cli new')
    check(d3.u16(0x78) == d3.stats()[0], 'new: HP set to computed max')
    r = subprocess.run([sys.executable, E.__file__, out, 'item', 'キズぐすり', '50', '--out', out, '--dict', DICT],
                       capture_output=True, text=True)
    check(r.returncode == 0 and E.Save(out, dic).item_count(1) == 50, 'cli item')
    sv3 = E.Save(out, dic)
    diff = [i for i in range(len(orig)) if orig[i] != sv3.buf[i]]
    check(all(d3.base <= i < d3.base + E.REC or 0x965ff <= i < 0x965ff + 96426 for i in diff), 'cli edits confined')
print(f'all {ok} checks passed')
