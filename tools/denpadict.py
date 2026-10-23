#!/usr/bin/env python3
"""Build data/denpa-dict.json: everything the save editor needs to turn the raw
bytes of a denpa record into names and back.

All of it comes from the ROM tables (docs/04) of the user's own dump, so the
file holds only short labels and numeric parameters, never game text bodies:

    skills_by_id         SkillData        name / category / description
    antenna_groups       AntennaGroup     6 skill tiers + level thresholds,
                                          stat multipliers, growth type
    heads                HeadData         AP bonus, inheritance %
    body_types           BodyData         scale, evasion, stat %
    color_data           ColorData        the 39 colours a denpa can be (name,
                                          rgb, element mask)
    body_color_effects   BodyColorData    per colour-pair: element affinities,
                                          defence %, extra effect
    color_genetics       BodyColorGenetic child colour lottery per parent pair
    parameter_cap        ParameterCap     per generation: level cap, happiness
                                          max, stat %, rebirth parameters
    level_status         LevelStatusData  base stats per level, 3 growth types
    level_exp            LevelData        cumulative EXP per level
    items_by_id          ItemData         item names
    voice_map            MessageDenpaName kana -> voice-synth byte(s), learned
                                          from the 2,765 (name, voice) pairs

How each field is interpreted is in docs/19 (all code-confirmed in Ghidra).

    python3 tools/denpadict.py extracted/update_romfs data/denpa-dict.json
"""
import collections, json, os, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dbexport import tables, export

# The eight denpa attributes are colours, confirmed from BodyColorData:
# mask bit 0x2..0x100 -> element index 0..7, each named by the colour that
# gives +2 affinity there. (Earlier guesses of 火/水/… were wrong.)
ELEMENTS = ['あか', 'みずいろ', 'みどり', 'だいだい', 'きいろ', 'あお', 'しろ', 'むらさき']
RGB565 = None


def load(romfs):
    """name -> (header, bytes); the first table of each name wins."""
    out = {}
    for _, fn, h, d in tables(romfs):
        out.setdefault(h['name'], (h, d))
    return out


def recs(t):
    h, d = t
    return [d[h['rec_off'] + i * h['rec_size']:h['rec_off'] + (i + 1) * h['rec_size']]
            for i in range(h['count'])]


def s6(x):
    x &= 0x3f
    return x - 64 if x >= 32 else x


def s4(x):
    x &= 0xf
    return x - 16 if x >= 8 else x


def cstr16(d, off):
    end = off
    while struct.unpack_from('<H', d, end)[0]:
        end += 2
    return d[off:end].decode('utf-16-le', 'replace')


def cstr8(d, off):
    return d[off:d.index(b'\0', off)]


def skills(t):
    rows = export(t[0], t[1], 4)
    return {str(r['id']): dict(index=r['index'], name=r['name'],
                               category=r['text'][0] if r['text'] else '',
                               desc=r['text'][1] if len(r['text']) > 1 else '')
            for r in rows}


def antenna_groups(t, sk):
    out = []
    for i, r in enumerate(recs(t)):
        tiers = []
        thr = struct.unpack_from('<6H', r, 0x22)
        for k in range(6):
            sid = struct.unpack_from('<I', r, 4 + 4 * k)[0]
            if sid & 0x80000000 and (sid & 0x7fffffff):
                sid &= 0x7fffffff
                tiers.append(dict(skill_id=sid, name=sk.get(str(sid), {}).get('name', ''),
                                  level=thr[k]))
        w0 = struct.unpack_from('<I', r, 0)[0]
        out.append(dict(index=i,
                        display=tiers[0]['name'] if tiers else '',
                        tiers=tiers,
                        thresholds=list(thr),
                        stat_mult=list(r[0x3d:0x42]),          # HP AP ATK DEF SPD, (x*2+748)/1000
                        stat_bonus=[s6(w0 >> (6 * k)) for k in range(5)],
                        growth_type=(struct.unpack_from('<H', r, 0x1e)[0] >> 8) & 0xf))
    return out


def heads(t):
    return [dict(index=i, ap_bonus=r[0xc], inherit_pct=r[0xe]) for i, r in enumerate(recs(t))]


def body_types(t):
    out = []
    for i, r in enumerate(recs(t)):
        out.append(dict(index=i,
                        scale=[round(x, 3) for x in struct.unpack_from('<3f', r, 0)],
                        eva=r[0x31],
                        stat_pct=list(r[0x33:0x37])))             # HP ATK DEF SPD
    return out


def color_data(t):
    h, d = t
    out = []
    for i, r in enumerate(recs(t)):
        off = struct.unpack_from('<I', r, 0)[0]
        out.append(dict(index=i, name=cstr16(d, off),
                        mask=struct.unpack_from('<H', r, 4)[0],
                        rgb='#%02x%02x%02x' % (r[6], r[7], r[8])))
    return out


def body_color_effects(t):
    out = []
    for i, r in enumerate(recs(t)):
        w0 = struct.unpack_from('<I', r, 0)[0]
        w1 = struct.unpack_from('<H', r, 4)[0]
        ma, mb = struct.unpack_from('<HH', r, 8)
        out.append(dict(index=i, mask_a=ma, mask_b=mb,
                        elements=[s4(w0 >> (4 * k)) for k in range(8)],
                        rare_elements=[(w1 >> (2 * k)) & 3 for k in range(8)],
                        effect_c=r[0xc], effect_d=r[0xd], def_pct=r[0xe],
                        category=r[0xf]))
    return out


def color_genetics(t):
    out = []
    for i, r in enumerate(recs(t)):
        a, b = struct.unpack_from('<HH', r, 0)
        sets = []
        for base in (4, 12):
            s = r[base:base + 8]
            sets.append([(s[0], s[1]), (s[2], s[3]), (s[6], s[7])])
        out.append(dict(index=i, parent_a=a, parent_b=b, lots=sets))
    return out


def parameter_cap(t):
    out = []
    for g, r in enumerate(recs(t)):
        w0, w1, _, w3, w4 = struct.unpack_from('<5I', r, 0)
        out.append(dict(gen=g, valid=bool(w0 & 1),
                        happy_max=(w0 & 0x7fff) >> 5,
                        rebirth_happy=(w0 & 0x1ffffff) >> 15,
                        level_cap=(w1 & 0xfffff) >> 10,
                        hp_bonus=w3 & 0x3ff, ap_bonus=(w3 & 0xfffff) >> 10,
                        atk_bonus=(w3 & 0x3fffffff) >> 20,
                        def_bonus=w4 & 0x3ff, spd_bonus=(w4 & 0xfffff) >> 10,
                        child_days=(w4 >> 20) & 0xf,        # code: (w4>>18)&0x3c, stored in rec+0x84 bits 2-5
                        f16=struct.unpack_from('<H', r, 0x16)[0],
                        stat_pct=list(r[0x19:0x1e]),
                        feast_div=r[0x1f] & 0xf, feast_div_alt=r[0x1f] >> 4,
                        breed_lots=(w0 & 0x1f) >> 1))
    return out


def level_status(t):
    rows = recs(t)
    return [[list(struct.unpack_from('<6H', r, 12 * k)) for r in rows if struct.unpack_from('<H', r, 12 * k)[0] != 999]
            for k in range(3)]


def level_exp(t):
    return [struct.unpack_from('<I', r, 0)[0] for r in recs(t)]


def items(t):
    return {str(r['id']): r['name'] for r in export(t[0], t[1], 2)}


def voice_map(t):
    """Learn kana -> voice bytes from the name pool: align each name with its
    voice string (0x27 = accent mark, 0xDE/0xDF = (han)dakuten suffix)."""
    h, d = t
    m = collections.defaultdict(collections.Counter)
    for r in recs(t):
        o1, o2 = struct.unpack_from('<II', r, 0)
        name, v = cstr16(d, o1), cstr8(d, o2).replace(b"'", b'')
        i, pairs = 0, []
        for ch in name:
            if i >= len(v):
                pairs = None
                break
            b = v[i]
            i += 1
            if i < len(v) and v[i] in (0xde, 0xdf):
                pairs.append((ch, bytes([b, v[i]])))
                i += 1
            else:
                pairs.append((ch, bytes([b])))
        if pairs and i == len(v):
            for ch, b in pairs:
                m[ch][b] += 1
    return {ch: c.most_common(1)[0][0].hex() for ch, c in sorted(m.items())}


def build(romfs):
    T = load(romfs)
    sk = skills(T['SkillData'])
    return dict(
        version=2,
        elements=ELEMENTS,
        skills_by_id=sk,
        antenna_groups=antenna_groups(T['AntennaGroup'], sk),
        heads=heads(T['HeadData']),
        body_types=body_types(T['BodyData']),
        color_data=color_data(T['ColorData']),
        body_color_effects=body_color_effects(T['BodyColorData']),
        color_genetics=color_genetics(T['BodyColorGenetic']),
        parameter_cap=parameter_cap(T['ParameterCap']),
        level_status=level_status(T['LevelStatusData']),
        level_exp=level_exp(T['LevelData']),
        items_by_id=items(T['ItemData']),
        voice_map=voice_map(T['MessageDenpaName']),
    )


def main():
    romfs, out = sys.argv[1], sys.argv[2]
    d = build(romfs)
    json.dump(d, open(out, 'w'), ensure_ascii=False, indent=0, separators=(',', ':'))
    for k, v in d.items():
        print(f'  {k:20s} {len(v) if hasattr(v, "__len__") else v}')
    print(f'-> {out}')


if __name__ == '__main__':
    main()
