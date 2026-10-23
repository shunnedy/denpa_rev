#!/usr/bin/env python3
"""Complete denpa (電波人間) editor for 電波人間のRPG FREE! v1.17.0 saves.

Every denpa is one 252-byte (0xFC) record; the save's section directory at
0x14 gives the party (16 slots), the box (1050 slots) and a spare 8-slot area.
The record layout, the appearance genetics, the stat formula and the inventory
variables are all decoded from the game code (docs/19), so this edits every
field by name and shows the derived values (stats, antenna skill, element
affinities) the way the game computes them.

Slots:  p0..p15 = party, b0..b1049 = box, x0..x7 = spare area.

    python3 tools/denpaedit.py save.bin list
    python3 tools/denpaedit.py save.bin show p1
    python3 tools/denpaedit.py save.bin set p1 level=50 antenna=すこしわざアップ --out new.bin
    python3 tools/denpaedit.py save.bin set p0 colora=むらさき colorb=きん mix=3 head=12 --out new.bin
    python3 tools/denpaedit.py save.bin set p0 name=たろう --out new.bin      # voice string is generated too
    python3 tools/denpaedit.py save.bin set p0 equip1=ちからのうでわ --out new.bin
    python3 tools/denpaedit.py save.bin new b5 --from p1 name=コピー level=30 --out new.bin
    python3 tools/denpaedit.py save.bin copy b0 p2 --out new.bin
    python3 tools/denpaedit.py save.bin delete b3 --out new.bin
    python3 tools/denpaedit.py save.bin export p0 taro.bin / import taro.bin b7 --out new.bin
    python3 tools/denpaedit.py save.bin items                 # inventory
    python3 tools/denpaedit.py save.bin item キズぐすり 99 --out new.bin
    python3 tools/denpaedit.py save.bin fields                # every editable field

The dictionary (names, tables) is data/denpa-dict.json, built from the ROM by
tools/denpadict.py.
"""
import argparse, json, os, struct, sys, hashlib, time

REC = 0xFC
DIR = 0x14                       # (offset, size) pairs; [5]=party [6]=box [7]=spare
VAR_BASE = 0x965FF               # bit-packed variable store (v1.17.0), docs/16
ITEM_VAR_BIT = 65918             # var 0x1d: item counts, 7 bits x 3000 (docs/19)
ITEM_VAR2_BIT = 86918            # var 0x1e: second item count array
ITEM_MAX = 99
KINDS = {0x3: 'レア(ROM定義)', 0x4: 'モンスター', 0x6: '外部データ', 0x8: '初期メンバー',
         0x9: 'NPC', 0xa: '子(通常)', 0xb: 'ゲット', 0xc: '子(ゲット系)'}
FACE_PARTS = [('brow', 0x67, 32), ('eye', 0x68, 64), ('nose', 0x69, 64),
              ('mouth', 0x6a, 64), ('cheek', 0x6b, 32), ('skin', 0x65, 16),
              ('hair', 0x66, 51)]
STAT_NAMES = ['HP', 'AP', 'こうげき', 'ぼうぎょ', 'すばやさ', 'かいひ']
HASH_KINDS = (0, 1, 2, 5, 6, 8, 10, 12)


def idiv(a, b):
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


# ---------------------------------------------------------------- dictionary
class Dict:
    def __init__(self, path):
        self.d = json.load(open(path))
        self.items = self.d['items_by_id']
        self.item_by_name = {}
        for k, v in self.items.items():
            self.item_by_name.setdefault(v, int(k))
        self.groups = self.d['antenna_groups']
        self.group_by_name = {}
        for g in self.groups:
            if g['display']:
                self.group_by_name.setdefault(g['display'], g['index'])
        self.colors = self.d['color_data']
        self.color_by_name = {c['name']: c['index'] for c in self.colors if c['name']}

    def item_name(self, iid):
        return self.items.get(str(iid), f'item#{iid}')

    def skill_name(self, sid):
        return self.d['skills_by_id'].get(str(sid), {}).get('name', f'skill#{sid}')

    def resolve_item(self, s):
        if s.lower() in ('none', '0', 'なし'):
            return 0
        if s.isdigit():
            return int(s)
        if s in self.item_by_name:
            return self.item_by_name[s]
        raise SystemExit(f'unknown item: {s}')

    def resolve_group(self, s):
        if s.isdigit():
            return int(s)
        if s in self.group_by_name:
            return self.group_by_name[s]
        raise SystemExit(f'unknown antenna group: {s}')

    def resolve_color(self, s):
        if s.isdigit():
            return int(s)
        if s in self.color_by_name:
            return self.color_by_name[s]
        raise SystemExit(f'unknown colour: {s}')

    def body_color(self, a, b):
        """BodyColorData row for colours (a, b) - FUN_00246648 / FUN_0040a898."""
        ma, mb = self.colors[a]['mask'], self.colors[b]['mask']
        m = (ma | 0x2000) if (ma == mb and a != b) else (ma | mb)
        for r in self.d['body_color_effects']:
            if (r['mask_a'] | r['mask_b']) == m:
                return r
        return self.d['body_color_effects'][0]

    def voice(self, name):
        vm = self.d['voice_map']
        out = b''
        for ch in name:
            if ch in vm:
                out += bytes.fromhex(vm[ch])
            elif 'ァ' <= ch <= 'ヶ':          # katakana -> hiragana row
                h = chr(ord(ch) - 0x60)
                if h in vm:
                    out += bytes.fromhex(vm[h])
        return out


# ---------------------------------------------------------------- record access
class Denpa:
    """View over one 252-byte record inside a save buffer."""

    def __init__(self, buf, base, dic):
        self.buf, self.base, self.dic = buf, base, dic

    # raw helpers
    def u8(self, o): return self.buf[self.base + o]
    def u16(self, o): return struct.unpack_from('<H', self.buf, self.base + o)[0]
    def u32(self, o): return struct.unpack_from('<I', self.buf, self.base + o)[0]
    def w8(self, o, v): self.buf[self.base + o] = v & 0xff
    def w16(self, o, v): struct.pack_into('<H', self.buf, self.base + o, v & 0xffff)
    def w32(self, o, v): struct.pack_into('<I', self.buf, self.base + o, v & 0xffffffff)
    def raw(self): return bytes(self.buf[self.base:self.base + REC])

    @property
    def empty(self): return self.u32(0) == 0
    @property
    def kind(self): return (self.u16(6) & 0xff) >> 4
    @property
    def level(self): return self.u16(0x96)
    @property
    def gen(self): return self.u8(0x82)

    # name + voice: UTF-16 NUL-terminated at +0x14, then the voice bytes, 24 bytes total
    def name(self):
        raw = self.buf[self.base + 0x14:self.base + 0x2c]
        end = 0
        while end + 1 < len(raw) and raw[end:end + 2] != b'\0\0':
            end += 2
        return raw[:end].decode('utf-16-le', 'ignore')

    def voice(self):
        raw = self.buf[self.base + 0x14:self.base + 0x2c]
        n = len(self.name().encode('utf-16-le')) + 2
        v = raw[n:]
        return v[:v.index(b'\0')] if b'\0' in v else v

    def set_name(self, name, voice=None):
        enc = name.encode('utf-16-le')
        if voice is None:
            voice = self.dic.voice(name)
        if len(enc) + 2 + len(voice) + 1 > 24:
            raise SystemExit('name too long: name(UTF-16)+voice must fit in 24 bytes')
        blob = (enc + b'\0\0' + voice + b'\0').ljust(24, b'\0')
        self.buf[self.base + 0x14:self.base + 0x2c] = blob

    def owner(self):
        raw = self.buf[self.base + 0x4c:self.base + 0x60]
        end = 0
        while end + 1 < len(raw) and raw[end:end + 2] != b'\0\0':
            end += 2
        return raw[:end].decode('utf-16-le', 'ignore')

    # antenna
    def antenna_tier(self, group=None, level=None):
        g = self.dic.groups[self.u8(0x94) if group is None else group]
        lv = self.level if level is None else level
        return sum(1 for t in g['tiers'] if t['level'] <= lv)

    def refresh_antenna(self):
        """FUN_0028f564: tier and current skill follow level and group."""
        g = self.dic.groups[self.u8(0x94)]
        tier = self.antenna_tier()
        self.w8(0x95, tier)
        self.w16(0x62, g['tiers'][tier - 1]['skill_id'] if tier else 1)

    def set_level(self, lv, keep_exp=False):
        lv = max(1, min(999, lv))
        self.w16(0x96, lv)
        if not keep_exp:
            self.w32(0x98, self.dic.d['level_exp'][lv - 1])
        self.refresh_antenna()

    # appearance hash (FUN_0027f2f0): sha256 of 12 appearance bytes, folded to 16 bits
    def appearance_hash(self):
        a = self.buf[self.base + 0x60:self.base + 0x76]
        data = bytes([a[0xd], a[4], a[5], a[6]]) + a[7:0xb] + bytes([a[0xb], a[0x10], a[0x13], a[0x14]])
        dg = hashlib.sha256(data).digest()
        s = sum(struct.unpack_from('<4I', dg, 0)) & 0xffffffff
        s = (s + (s // 0xffff) * -0xffff + (s >> 16)) & 0xffffffff
        return (s & 0xffff) or 1

    def refresh_hash(self):
        if self.kind in HASH_KINDS:
            self.w16(0x60, self.appearance_hash())

    # computed stats (FUN_0028fd88), without equipment effects
    def stats(self):
        D = self.dic.d
        gt = self.u8(0x9e) & 0xf
        rows = D['level_status'][min(gt, 2)]
        lv = self.level
        i = 0
        while i < len(rows) - 1 and rows[i + 1][0] <= lv:
            i += 1
        v = list(rows[i])
        if i < len(rows) - 1 and rows[i][0] != lv:
            nx, f, dd = rows[i + 1], lv - v[0], rows[i + 1][0] - v[0]
            for k in range(1, 6):
                v[k] += idiv((nx[k] - v[k]) * f, dd)
        g = D['antenna_groups'][self.u8(0x94)]
        pc = D['parameter_cap'][min(self.gen, 9)]
        bd = D['body_types'][self.u8(0x6d)]
        hd = D['heads'][self.u8(0x64)]
        bc = self.dic.body_color(self.u8(0x71), self.u8(0x72))
        s = []
        for k in range(5):
            x = idiv((g['stat_mult'][k] * 2 + 0x2ec) * v[k + 1], 1000)
            s.append(idiv((pc['stat_pct'][k] + 1000) * x, 1000))
        hp = idiv(bd['stat_pct'][0] * s[0], 100)
        ap = s[1] + (hd['ap_bonus'] if s[1] else 0)
        atk = idiv(bd['stat_pct'][1] * s[2], 100)
        de = idiv(bc['def_pct'] * idiv(bd['stat_pct'][2] * s[3], 100), 100)
        spd = idiv(bd['stat_pct'][3] * s[4], 100)
        b = g['stat_bonus']
        out = [self.u8(0xa6) + hp + pc['hp_bonus'] + b[0] + self.u8(0xa0),
               self.u8(0xa7) + ap + pc['ap_bonus'] + b[1] + self.u8(0xa1),
               self.u8(0xa8) + atk + pc['atk_bonus'] + b[2] + self.u8(0xa2),
               self.u8(0xa9) + pc['def_bonus'] + de + b[3] + self.u8(0xa3),
               self.u8(0xaa) + spd + pc['spd_bonus'] + b[4] + self.u8(0xa4),
               bd['eva'] + self.u8(0xab) + self.u8(0xa5)]
        if self.u8(0x84) >> 2:                     # child: attack/defence halved
            out[2], out[3] = (out[2] + 1) // 2, (out[3] + 1) // 2
        for k in range(5):
            out[k] = max(1, min(9999, out[k]))
        if g['stat_mult'][1] == 0:
            out[1] = 0
        out[5] = max(0, min(50, out[5]))
        return out

    # ------------------------------------------------------------ display
    def summary(self):
        if self.empty:
            return '(empty)'
        g = self.dic.groups[self.u8(0x94)]
        return (f"{self.name():　<6} Lv{self.level:<3} {self.gen + 1}代目/{self.u8(0x83) + 1}代 "
                f"HP{self.u16(0x78)} AP{self.u8(0x7a)} 幸福{self.u16(0x80)} "
                f"{g['display'] or '(なし)'} [{KINDS.get(self.kind, hex(self.kind))}] id{self.u32(0)}")

    def show(self):
        D = self.dic.d
        if self.empty:
            print('(empty)')
            return
        g = self.dic.groups[self.u8(0x94)]
        pc = D['parameter_cap'][min(self.gen, 9)]
        st = self.stats()
        ca, cb, mix = self.u8(0x71), self.u8(0x72), self.u8(0x70)
        bc = self.dic.body_color(ca, cb)
        L = []
        L.append(f"名前      {self.name()}  (voice {self.voice().hex(' ')})  owner {self.owner()!r}")
        L.append(f"id        {self.u32(0)}  kind {KINDS.get(self.kind, hex(self.kind))}(0x{self.kind:x})  "
                 f"source/hash 0x{self.u16(0x60):04x}  名前番号 {self.u32(0x10)}")
        L.append(f"レベル    Lv{self.level}  exp {self.u32(0x98)}  (この世代の上限 Lv{pc['level_cap']})")
        L.append(f"世代      {self.gen + 1}代目 / {self.u8(0x83) + 1}代まで  転生回数 {self.u8(0x85)}  "
                 f"子作り残り {self.u8(0x84) & 3}  こども残り日数 {self.u8(0x84) >> 2}")
        L.append(f"HP/AP     {self.u16(0x78)}/{self.u8(0x7a)}  幸福 {self.u16(0x80)}/{pc['happy_max']}")
        tier = self.u8(0x95)
        L.append(f"アンテナ  [{self.u8(0x94)}] {g['display'] or '(なし)'}  段階 {tier}  "
                 f"現在のとくぎ {self.dic.skill_name(self.u16(0x62))}  成長タイプ {self.u8(0x9e) & 0xf}")
        L.append(f"両親のアンテナ  {self.u8(0x86)} / {self.u8(0x87)}")
        L.append(f"計算ステータス  " + '  '.join(f'{n}{v}' for n, v in zip(STAT_NAMES, st)) + '  (装備効果は含まず)')
        L.append(f"永続ボーナス(+0xa6) {list(self.buf[self.base + 0xa6:self.base + 0xac])}  "
                 f"今世代ボーナス(+0xa0) {list(self.buf[self.base + 0xa0:self.base + 0xa6])}")
        L.append(f"頭 {self.u8(0x64)}  体型 {self.u8(0x6d)}  " +
                 '  '.join(f'{n} {self.u8(o)}' for n, o, _ in FACE_PARTS) +
                 f"  はだ色 {self.u8(0x73)}  かみ色 {self.u8(0x74)}")
        cname = lambda i: self.dic.colors[i]['name'] if i < len(self.dic.colors) else str(i)
        single = self.u8(0x75)
        L.append(f"体色      A {ca}:{cname(ca)}  B {cb}:{cname(cb)}  まだら {mix}" +
                 (f"  単色フラグ {single >> 1}:{cname(single >> 1)}" if single & 1 else ''))
        aff = '  '.join(f'{e}{v:+d}' for e, v in zip(D['elements'], bc['elements']) if v)
        L.append(f"属性耐性  {aff or 'なし'}  (ぼうぎょ{bc['def_pct']}%)")
        eq = [self.u32(0xac + 4 * k) for k in range(8)]
        L.append('装備      ' + '  '.join(f'{k}:{self.dic.item_name(e & 0x7fffffff)}' for k, e in enumerate(eq) if e))
        L.append(f"性別/声   sex {self.u8(0x76) & 0xf} namegrp {self.u8(0x76) >> 4}  voicetype {self.u8(0x77)}  "
                 f"timestamps {self.u32(8):#x} {self.u32(0x88):#x}  days {self.u16(0x8c)}/{self.u16(0x8e)}/{self.u16(0x90)}  "
                 f"form {self.u16(0x9c)}  f9f {self.u8(0x9f)}")
        if self.kind in HASH_KINDS and self.u16(0x60) != self.appearance_hash():
            L.append(f"  ! 外見ハッシュ不一致 (期待 0x{self.appearance_hash():04x})")
        print('\n'.join('  ' + l for l in L))


# ---------------------------------------------------------------- fields
def set_field(dn, key, val):
    D = dn.dic
    k = key.lower()
    simple = {'hp': (0x78, 2), 'ap': (0x7a, 1), 'happy': (0x80, 2), 'gen': (0x82, 1),
              'maxgen': (0x83, 1), 'rebirths': (0x85, 1), 'head': (0x64, 1), 'body': (0x6d, 1),
              'facecolor': (0x73, 1), 'haircolor': (0x74, 1), 'mix': (0x70, 1),
              'growth': None, 'exp': (0x98, 4), 'voicetype': (0x77, 1), 'form': (0x9c, 2),
              'parenta': (0x86, 1), 'parentb': (0x87, 1), 'instance': (0x00, 4),
              'source': (0x60, 2), 'f9f': (0x9f, 1)}
    if k == 'name':
        dn.set_name(val)
    elif k == 'voice':
        dn.set_name(dn.name(), bytes.fromhex(val))
    elif k == 'level':
        dn.set_level(int(val))
    elif k == 'exp':
        dn.w32(0x98, int(val))
    elif k == 'gen':
        g = int(val) - 1 if not val.startswith('0') else int(val)
        dn.w8(0x82, max(0, min(9, g)))
        if dn.u8(0x83) < dn.u8(0x82):
            dn.w8(0x83, dn.u8(0x82))
    elif k == 'maxgen':
        dn.w8(0x83, max(dn.u8(0x82), int(val) - 1))
    elif k == 'antenna':
        dn.w8(0x94, D.resolve_group(val))
        dn.w8(0x9e, (dn.u8(0x9e) & 0xf0) | D.groups[dn.u8(0x94)]['growth_type'])
        dn.refresh_antenna()
    elif k == 'growth':
        dn.w8(0x9e, (dn.u8(0x9e) & 0xf0) | (int(val) & 0xf))
    elif k == 'kind':
        kv = int(val, 0)
        dn.w16(6, (dn.u16(6) & 0xff0f) | ((kv & 0xf) << 4))
    elif k in ('colora', 'colorb'):
        c = D.resolve_color(val)
        dn.w8(0x71 if k == 'colora' else 0x72, c)
        if dn.u8(0x71) == dn.u8(0x72) or dn.u8(0x72) == 0:
            dn.w8(0x70, 0)
            if dn.u8(0x71) == dn.u8(0x72):
                dn.w8(0x72, 0)
        elif dn.u8(0x70) == 0:
            dn.w8(0x70, 1)
    elif k == 'breed':
        dn.w8(0x84, (dn.u8(0x84) & 0xfc) | (int(val) & 3))
    elif k == 'childdays':
        dn.w8(0x84, (dn.u8(0x84) & 3) | ((int(val) & 0x3f) << 2))
    elif k == 'sex':
        dn.w8(0x76, (dn.u8(0x76) & 0xf0) | (int(val) & 0xf))
    elif k == 'namegrp':
        dn.w8(0x76, (dn.u8(0x76) & 0x0f) | ((int(val) & 0xf) << 4))
    elif k.startswith('equip') and k[5:].isdigit():
        slot = int(k[5:])
        iid = D.resolve_item(val)
        dn.w32(0xac + 4 * slot, (0x80000000 | iid) if iid else 0)
    elif k.startswith('bonus_') or k.startswith('feast_'):
        idx = STAT_NAMES.index(key[6:]) if key[6:] in STAT_NAMES else ['hp', 'ap', 'atk', 'def', 'spd', 'eva'].index(k[6:])
        dn.w8((0xa6 if k.startswith('bonus_') else 0xa0) + idx, int(val))
    elif k in dict(FACE_PARTS[0:0]) or any(k == n for n, _, _ in FACE_PARTS):
        off, mx = next((o, m) for n, o, m in FACE_PARTS if n == k)
        v = int(val)
        if not 0 <= v < mx:
            raise SystemExit(f'{k}: 0..{mx - 1}')
        dn.w8(off, v)
    elif k in simple and simple[k]:
        off, w = simple[k]
        v = int(val, 0)
        if w == 1: dn.w8(off, v)
        elif w == 2: dn.w16(off, v)
        else: dn.w32(off, v)
    elif k.startswith('raw@'):
        dn.w8(int(k[4:], 16), int(val, 0))
    else:
        raise SystemExit(f'unknown field: {key} (see "fields")')
    # keep derived fields consistent
    dn.refresh_antenna()
    dn.refresh_hash()


FIELDS_HELP = """\
name=<かな/カナ>        名前（音声合成用の読みも自動生成）     voice=<hex>  読みを直接指定
level=N                 レベル（expも対応値に）               exp=N
hp=N ap=N happy=N       現在HP / AP / 幸福度
gen=N maxgen=N          N代目 / 何代まで                      rebirths=N  転生回数
antenna=<名前|番号>     アンテナ群（段階・とくぎ・成長タイプを再計算） growth=0..2
head=0..70 body=0..29   頭 / 体型
brow eye nose mouth cheek skin hair   顔パーツ (=N)
facecolor=0..5 haircolor=0..11
colora=<色名|番号> colorb=<色名|番号> mix=N   体色A/B とまだら模様（Bなし = none相当は colorb=0）
equip0..equip7=<アイテム名|ID|none>  装備
bonus_hp.. bonus_eva    永続ステータスボーナス(+0xa6)   feast_hp.. 今世代ボーナス(+0xa0)
breed=0..3 childdays=N  子作り残り回数 / こども残り日数
kind=0x..  sex=N namegrp=N voicetype=N form=N parenta=N parentb=N instance=N source=N
raw@<hex offset>=N      任意バイト
"""


# ---------------------------------------------------------------- save
class Save:
    def __init__(self, path, dic):
        self.buf = bytearray(open(path, 'rb').read())
        self.dic = dic
        self.sections = [struct.unpack_from('<II', self.buf, DIR + 8 * i) for i in range(8)]
        self.areas = {'p': self.sections[5], 'b': self.sections[6], 'x': self.sections[7]}

    def slot(self, spec):
        k, i = spec[0].lower(), int(spec[1:])
        off, size = self.areas[k]
        if not 0 <= i < size // REC:
            raise SystemExit(f'{spec}: {k} has {size // REC} slots')
        return Denpa(self.buf, off + i * REC, self.dic)

    def all_slots(self):
        for k in 'pbx':
            off, size = self.areas[k]
            for i in range(size // REC):
                yield f'{k}{i}', Denpa(self.buf, off + i * REC, self.dic)

    def next_instance(self):
        return max((d.u32(0) for _, d in self.all_slots()), default=0) + 1

    # inventory: var 0x1d, 7 bits per item index
    def getbits(self, bit, w):
        p = VAR_BASE * 8 + bit
        return (int.from_bytes(self.buf[p >> 3:(p >> 3) + 8], 'little') >> (p & 7)) & ((1 << w) - 1)

    def setbits(self, bit, w, val):
        p = VAR_BASE * 8 + bit
        for k in range(w):
            q = p + k
            b = (val >> k) & 1
            self.buf[q >> 3] = (self.buf[q >> 3] & ~(1 << (q & 7))) | (b << (q & 7))

    def item_count(self, iid):
        return self.getbits(ITEM_VAR_BIT + 7 * iid, 7)

    def set_item(self, iid, n):
        self.setbits(ITEM_VAR_BIT + 7 * iid, 7, max(0, min(ITEM_MAX, n)))

    def items(self):
        return [(i, self.item_count(i)) for i in range(3000) if self.item_count(i)]


def write_out(save, path):
    open(path, 'wb').write(save.buf)
    print(f'-> {path}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('save')
    ap.add_argument('cmd', choices=['list', 'show', 'set', 'new', 'copy', 'move', 'swap', 'delete',
                                    'export', 'import', 'items', 'item', 'fields'])
    ap.add_argument('args', nargs='*')
    ap.add_argument('--out', help='write the result here (otherwise nothing is written)')
    ap.add_argument('--from', dest='frm', help='new: template slot (default: built-in blank)')
    ap.add_argument('--dict', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'denpa-dict.json'))
    ap.add_argument('--all', action='store_true', help='list: include empty slots')
    a = ap.parse_intermixed_args()
    if a.cmd == 'fields':
        print(FIELDS_HELP)
        return
    dic = Dict(a.dict)
    sv = Save(a.save, dic)
    changed = False

    if a.cmd == 'list':
        for k, label in (('p', 'party'), ('b', 'box'), ('x', 'spare')):
            print(f'{label}:')
            off, size = sv.areas[k]
            for i in range(size // REC):
                d = Denpa(sv.buf, off + i * REC, dic)
                if a.all or not d.empty:
                    print(f'  {k}{i:<5} {d.summary()}')
    elif a.cmd == 'show':
        for s in a.args:
            print(f'{s}:')
            sv.slot(s).show()
    elif a.cmd == 'set':
        d = sv.slot(a.args[0])
        if d.empty:
            raise SystemExit('empty slot (use new)')
        for kv in a.args[1:]:
            k, v = kv.split('=', 1)
            set_field(d, k, v)
        d.show()
        changed = True
    elif a.cmd == 'new':
        dst = sv.slot(a.args[0])
        if not dst.empty:
            raise SystemExit('slot occupied (delete first)')
        if a.frm:
            dst.buf[dst.base:dst.base + REC] = sv.slot(a.frm).raw()
        else:
            dst.buf[dst.base:dst.base + REC] = bytes(REC)
            dst.w16(4, 1); dst.w16(6, 0x00b4); dst.w8(0xc, 1)     # kind 0xb "ゲット"
            dst.w8(0x64, 0); dst.w8(0x6d, 15); dst.w8(0x71, 3); dst.w8(0x83, 6)
            dst.w8(0x84, 1); dst.w8(0x9f, 3); dst.w8(0x76, 0x10)
            dst.w16(0x78, 1)
            dst.set_name('でんぱ')
            dst.set_level(1)
        dst.w32(0, sv.next_instance())
        for kv in a.args[1:]:
            k, v = kv.split('=', 1)
            set_field(dst, k, v)
        dst.refresh_antenna(); dst.refresh_hash()
        st = dst.stats()
        dst.w16(0x78, st[0]); dst.w8(0x7a, st[1])
        dst.show()
        changed = True
    elif a.cmd in ('copy', 'move', 'swap'):
        s, d = sv.slot(a.args[0]), sv.slot(a.args[1])
        sr, dr = s.raw(), d.raw()
        if a.cmd == 'swap':
            d.buf[d.base:d.base + REC] = sr
            s.buf[s.base:s.base + REC] = dr
        else:
            if not d.empty:
                raise SystemExit('destination occupied')
            d.buf[d.base:d.base + REC] = sr
            if a.cmd == 'move':
                s.buf[s.base:s.base + REC] = bytes(REC)
            else:
                d.w32(0, sv.next_instance())
        print(f'{a.cmd} {a.args[0]} -> {a.args[1]}')
        print(f'  {d.summary()}')
        changed = True
    elif a.cmd == 'delete':
        for s in a.args:
            d = sv.slot(s)
            d.buf[d.base:d.base + REC] = bytes(REC)
            print(f'deleted {s}')
        changed = True
    elif a.cmd == 'export':
        d = sv.slot(a.args[0])
        open(a.args[1], 'wb').write(d.raw())
        print(f'{a.args[0]} -> {a.args[1]} ({REC} bytes)')
    elif a.cmd == 'import':
        rec = open(a.args[0], 'rb').read()
        if len(rec) != REC:
            raise SystemExit(f'record must be {REC} bytes')
        d = sv.slot(a.args[1])
        d.buf[d.base:d.base + REC] = rec
        d.w32(0, sv.next_instance())
        print(f'  {d.summary()}')
        changed = True
    elif a.cmd == 'items':
        for i, n in sv.items():
            print(f'  {i:5d} x{n:<3} {dic.item_name(i)}')
    elif a.cmd == 'item':
        iid = dic.resolve_item(a.args[0])
        sv.set_item(iid, int(a.args[1]))
        print(f'  {iid} {dic.item_name(iid)} x{sv.item_count(iid)}')
        changed = True

    if changed:
        if a.out:
            write_out(sv, a.out)
        else:
            print('(--out 未指定: 保存していません)')


if __name__ == '__main__':
    main()
