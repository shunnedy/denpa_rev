#!/usr/bin/env python3
"""Generate a pool of Wi-Fi Colosseum opponent teams for the revival server.

The game downloads opponents and fights them locally (docs/20); it never
uploads, so without other players there is nobody to fight. This builds a
ladder of valid opponent parties by taking real denpa records as seeds and
varying their level, antenna, colour and name through the same edit path the
save editor uses (tools/denpaedit.py), then packing them with
tools/colosseum.py. Every team is therefore a party the game accepts.

    python3 tools/make_roster.py --seed-save savedata.bin --out /path/opponents
    # prints the --opponent args for tools/denpa_server.py

Needs a save only as a source of valid base records; nothing from it is
published.
"""
import argparse, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import denpaedit as E
import colosseum as C

# (team name, [(seed slot, name, level, antenna, colorA, colorB)]) — a 1..5 ladder
LADDER = [
    ('みならい隊', [('p0', 'ちび', 12, 'ちょっとふっかつ', 'みどり', '0'),
                    ('p0', 'ぷち', 10, 'ちょっとおたから', 'きいろ', '0')]),
    ('かけだし団', [('b0', 'あおば', 25, 'すこしわざアップ', 'あお', '0'),
                    ('b1', 'こまち', 22, 'みんなちょっとふっかつ', 'ももいろ', '0')]),
    ('なかよし組', [('b0', 'りく', 40, 'アンテナふうじ', 'だいだい', '0'),
                    ('b1', 'そら', 38, 'みんなちょっとふっかつ', 'みずいろ', '0'),
                    ('p1', 'みく', 36, 'すこしわざアップ', 'むらさき', '0')]),
    ('精鋭ズ', [('b0', 'ゴウ', 60, 'アンテナふうじ', 'くろ', '0'),
                ('b1', 'レイ', 58, 'みんなちょっとふっかつ', 'あか', '0'),
                ('p1', 'ナナ', 55, 'すこしわざアップ', 'あお', 'きん')]),
    ('火の軍団', [('b0', 'マグマ', 85, 'アンテナふうじ', 'あか', 'こいあか'),
                  ('b1', 'ヒバナ', 80, 'みんなちょっとふっかつ', 'だいだい', '0')]),
    ('王者チーム', [('b0', 'オウ', 120, 'アンテナふうじ', 'きん', 'ぎん'),
                    ('b1', 'ヒメ', 115, 'みんなちょっとふっかつ', 'むらさき', 'しろ'),
                    ('p1', 'キシ', 110, 'すこしわざアップ', 'あお', 'こいあお')]),
]


def build_record(sv, slot, name, level, antenna, ca, cb):
    buf = bytearray(sv.slot(slot).raw())
    d = E.Denpa(buf, 0, sv.dic)
    E.set_field(d, 'name', name)
    E.set_field(d, 'antenna', antenna)
    E.set_field(d, 'colora', ca)
    E.set_field(d, 'colorb', cb)
    E.set_field(d, 'level', str(level))
    st = d.stats()
    d.w16(0x78, st[0]); d.w8(0x7a, min(255, st[1]))     # fill current HP/AP
    return bytes(buf)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--seed-save', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--dict', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'denpa-dict.json'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    dic = E.Dict(a.dict)
    sv = E.Save(a.seed_save, dic)
    args = []
    for i, (team, members) in enumerate(LADDER):
        recs = [build_record(sv, *m) for m in members]
        blob = C.pack_party(recs, team_id=0x1000 + i)
        path = os.path.join(a.out, f'team{i}.blob')
        open(path, 'wb').write(blob)
        lv = [struct.unpack_from('<H', r, 0x96)[0] for r in recs]
        print(f'  {team}: {len(recs)} denpa Lv{lv} -> {path}')
        args.append(f'--opponent "{team}:{path}"')
    print('\nserver args:\n  ' + ' \\\n  '.join(args))


if __name__ == '__main__':
    main()
