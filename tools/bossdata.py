#!/usr/bin/env python3
"""Build SpotPass (BOSS) NsData files so 電波人間のRPG FREE! check-in works on
Azahar without Nintendo's CDN.

Check-in's "更新データ" is not fetched by the game's own HTTP code: the game
registers BOSS tasks (URLs in romfs boss.bin -> npdl.cdn.nintendowifi.net,
long dead) and then reads the result through nn::boss ReadNsData (docs/21).
Azahar's HLE BOSS never downloads anything; it enumerates NsData files that
already sit in the title's extdata and serves them. So we create those files:

    <BossHeader 0x34 bytes, big-endian>  +  <payload>

    0x00 u8   header_length (0x18)        0x18 u64 program id
    0x01 11B  zero                        0x20 4B  zero
    0x0C u32  unknown                     0x24 u32 datatype   (0x10001)
    0x10 u32  download date               0x28 u32 payload size
    0x14 4B   zero                        0x2C u32 NsDataId
                                          0x30 u32 version

The game asks for two NsDataIds (boss.bin record field +8):
    2  FGONLYT/checkin.dat   -> a GS data table with 84-byte records, i.e. the
                               same format as the ROM's CheckinData table
    3  FGONLYT/resource.dat  -> small version blob; u16 at +0xC is compared
                               with the save's stored version (0 = nothing new)

    python3 tools/bossdata.py build extracted/update_romfs -o out/boss
    python3 tools/bossdata.py build extracted/update_romfs -o out/boss --table Checkin_Rom
    python3 tools/bossdata.py inspect out/boss/00000002
"""
import argparse, glob, os, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmarc import Archive, table_header

PROGRAM_ID = 0x0004000000125D00
DATATYPE = 0x10001
HEADER_LEN = 0x34


def boss_header(ns_data_id, payload, version=1, download_date=None):
    if download_date is None:
        download_date = int(time.time())
    h = bytearray(HEADER_LEN)
    h[0] = 0x18
    struct.pack_into('>I', h, 0x0C, 0)
    struct.pack_into('>I', h, 0x10, download_date & 0xffffffff)
    struct.pack_into('>Q', h, 0x18, PROGRAM_ID)
    struct.pack_into('>I', h, 0x24, DATATYPE)
    struct.pack_into('>I', h, 0x28, len(payload))
    struct.pack_into('>I', h, 0x2C, ns_data_id)
    struct.pack_into('>I', h, 0x30, version)
    return bytes(h)


def nsdata(ns_data_id, payload, version=1):
    return boss_header(ns_data_id, payload, version) + payload


def parse(blob):
    f = {}
    f['header_length'] = blob[0]
    f['unknown'], f['download_date'] = struct.unpack_from('>II', blob, 0x0C)
    f['program_id'] = struct.unpack_from('>Q', blob, 0x18)[0]
    f['datatype'], f['payload_size'], f['ns_data_id'], f['version'] = struct.unpack_from('>IIII', blob, 0x24)
    f['payload'] = blob[HEADER_LEN:]
    return f


def find_table(romfs, name):
    for p in sorted(glob.glob(os.path.join(romfs, '*'))):
        b = os.path.basename(p)
        if len(b) != 8 or any(c not in '0123456789ABCDEF' for c in b):
            continue
        a = Archive(p)
        for s in a.sections:
            z = a.zip(s)
            blobs = ([z.read(i) for i in z.infolist()
                      if i.filename.endswith(('.bin', '.dat'))] if z
                     else [a.payload(s)[0]])
            for d in blobs:
                if len(d) >= 0x44:
                    h = table_header(d)
                    if h['valid'] and h['name'] == name:
                        return d
    raise SystemExit(f'table {name} not found under {romfs}')


def build(romfs, out, table='CheckinData', version=1):
    os.makedirs(out, exist_ok=True)
    checkin = find_table(romfs, table)
    h = table_header(checkin)
    files = {}
    # 2: the check-in delivery table
    files['00000002'] = nsdata(2, checkin, version)
    # 3: "resource" version blob; u16@0xC = 0 means the save is up to date
    files['00000003'] = nsdata(3, bytes(0x40), version)
    for fn, blob in files.items():
        open(os.path.join(out, fn), 'wb').write(blob)
        print(f'  {fn}: NsDataId {parse(blob)["ns_data_id"]}  payload {len(blob) - HEADER_LEN} bytes'
              + (f'  ({table}: {h["count"]} records x {h["rec_size"]}B)' if fn == '00000002' else ''))
    print(f'-> {out}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build'); b.add_argument('romfs'); b.add_argument('-o', required=True)
    b.add_argument('--table', default='CheckinData'); b.add_argument('--version', type=int, default=1)
    i = sub.add_parser('inspect'); i.add_argument('file')
    a = ap.parse_args()
    if a.cmd == 'build':
        build(a.romfs, a.o, a.table, a.version)
    else:
        f = parse(open(a.file, 'rb').read())
        for k, v in f.items():
            if k == 'payload':
                h = table_header(v) if len(v) >= 0x44 else {'valid': False}
                print(f'payload: {len(v)} bytes' + (f'  table {h["name"]} {h["count"]}x{h["rec_size"]}' if h.get('valid') else ''))
            else:
                print(f'{k}: {v:#x}' if isinstance(v, int) else f'{k}: {v}')


if __name__ == '__main__':
    main()
