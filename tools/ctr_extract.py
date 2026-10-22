#!/usr/bin/env python3
"""Minimal 3DS container extractor: NCSD(.cci) / CIA -> NCCH -> ExeFS + RomFS.

Works on already-decrypted dumps (GodMode9 "decrypted" output). No keys involved.
"""
import os, struct, sys

MU = 0x200

def u16(b, o): return struct.unpack_from('<H', b, o)[0]
def u32(b, o): return struct.unpack_from('<I', b, o)[0]
def u64(b, o): return struct.unpack_from('<Q', b, o)[0]
def be16(b, o): return struct.unpack_from('>H', b, o)[0]
def be32(b, o): return struct.unpack_from('>I', b, o)[0]
def be64(b, o): return struct.unpack_from('>Q', b, o)[0]
def align(v, a): return (v + a - 1) // a * a


# ---------- LZ77 backwards (3DS .code) ----------
def decompress_code(data):
    data = bytearray(data)
    n = len(data)
    top_bottom = u32(data, n - 8)
    orig_bottom = u32(data, n - 4)
    extra = top_bottom >> 24 & 0xFF          # footer size
    cmp_len = top_bottom & 0xFFFFFF           # length of compressed area
    out = data + bytearray(orig_bottom)
    dest = n + orig_bottom                    # write pointer (exclusive, from end)
    src = n - extra                           # read pointer (exclusive, from end)
    stop = n - cmp_len
    while src > stop:
        src -= 1
        flags = out[src]
        for bit in range(8):
            if src <= stop:
                break
            if flags & (0x80 >> bit) == 0:
                src -= 1
                dest -= 1
                out[dest] = out[src]
            else:
                src -= 2
                # inverted stream: high byte sits at the higher address
                seg = out[src] | (out[src + 1] << 8)
                size = (seg >> 12) + 3
                disp = (seg & 0xFFF) + 3
                for _ in range(size):
                    dest -= 1
                    out[dest] = out[dest + disp]
    return bytes(out)


# ---------- RomFS (IVFC level 3) ----------
def romfs_extract(buf, outdir):
    assert buf[0:4] == b'IVFC', 'not a romfs'
    master_hash_size = u32(buf, 0x08)
    lvl3_block = 1 << u32(buf, 0x4C)
    base = align(0x60 + master_hash_size, lvl3_block)

    hdr_len   = u32(buf, base + 0x00)
    dir_meta  = u32(buf, base + 0x0C); 
    file_meta = u32(buf, base + 0x1C)
    file_data = u32(buf, base + 0x24)
    assert hdr_len == 0x28, hdr_len

    count = [0, 0]

    def name_at(off, nlen):
        return buf[off:off + nlen].decode('utf-16-le', 'replace')

    def walk_dir(doff, path):
        d = base + dir_meta + doff
        first_file = u32(buf, d + 0x0C)
        first_child = u32(buf, d + 0x08)
        os.makedirs(path, exist_ok=True)
        count[1] += 1
        f = first_file
        while f != 0xFFFFFFFF:
            fo = base + file_meta + f
            doffset = u64(buf, fo + 0x08)
            dsize = u64(buf, fo + 0x10)
            nlen = u32(buf, fo + 0x1C)
            nm = name_at(fo + 0x20, nlen) or 'unnamed'
            start = base + file_data + doffset
            with open(os.path.join(path, nm), 'wb') as fh:
                fh.write(buf[start:start + dsize])
            count[0] += 1
            f = u32(buf, fo + 0x04)
        c = first_child
        while c != 0xFFFFFFFF:
            co = base + dir_meta + c
            nlen = u32(buf, co + 0x14)
            nm = name_at(co + 0x18, nlen) or 'unnamed'
            walk_dir(c, os.path.join(path, nm))
            c = u32(buf, co + 0x04)

    walk_dir(0, outdir)
    return count


# ---------- NCCH ----------
def ncch_extract(buf, outdir, label):
    assert buf[0x100:0x104] == b'NCCH', 'not an NCCH at ' + label
    os.makedirs(outdir, exist_ok=True)
    exh_size = u32(buf, 0x180)
    flags = buf[0x188:0x190]
    nocrypto = bool(flags[7] & 0x04)
    exefs_off = u32(buf, 0x1A0) * MU; exefs_size = u32(buf, 0x1A4) * MU
    romfs_off = u32(buf, 0x1B0) * MU; romfs_size = u32(buf, 0x1B4) * MU
    prod = buf[0x150:0x160].rstrip(b'\0').decode('ascii', 'replace')
    tid = u64(buf, 0x108)
    print(f'[{label}] product={prod} titleID={tid:016X} nocrypto={nocrypto} '
          f'exefs={exefs_size:#x} romfs={romfs_size:#x}')
    if not nocrypto:
        print(f'[{label}] WARNING: crypto flag set - data may still be encrypted')

    compressed = False
    if exh_size:
        exh = buf[0x200:0x200 + exh_size]
        open(os.path.join(outdir, 'exheader.bin'), 'wb').write(exh)
        compressed = bool(exh[0x0D] & 0x01)

    if exefs_size:
        ex = buf[exefs_off:exefs_off + exefs_size]
        open(os.path.join(outdir, 'exefs.bin'), 'wb').write(ex)
        for i in range(10):
            e = i * 0x10
            nm = ex[e:e + 8].rstrip(b'\0').decode('ascii', 'replace')
            if not nm:
                continue
            off = u32(ex, e + 8) + 0x200
            size = u32(ex, e + 12)
            blob = ex[off:off + size]
            fn = {'.code': 'code.bin'}.get(nm, nm + '.bin')
            open(os.path.join(outdir, fn), 'wb').write(blob)
            print(f'[{label}]   exefs: {nm} {size:#x} -> {fn}')
            if nm == '.code':
                dec = decompress_code(blob) if compressed else blob
                open(os.path.join(outdir, 'code_dec.bin'), 'wb').write(dec)
                print(f'[{label}]   .code compressed={compressed} '
                      f'decompressed={len(dec):#x}')

    if romfs_size:
        rf = buf[romfs_off:romfs_off + romfs_size]
        open(os.path.join(outdir, 'romfs.bin'), 'wb').write(rf)
    return romfs_size


def extract_ncsd(path, outbase):
    data = open(path, 'rb').read()
    assert data[0x100:0x104] == b'NCSD', 'not NCSD'
    names = {0: 'base', 1: 'manual', 2: 'dlp', 6: 'update_n3ds', 7: 'update_o3ds'}
    for i in range(8):
        off = u32(data, 0x120 + i * 8) * MU
        size = u32(data, 0x124 + i * 8) * MU
        if not size:
            continue
        lbl = names.get(i, f'part{i}')
        ncch_extract(data[off:off + size], os.path.join(outbase, lbl), lbl)


def extract_cia(path, outbase, label='update'):
    data = open(path, 'rb').read()
    hdr = u32(data, 0)
    cert_s, tik_s, tmd_s = u32(data, 0x08), u32(data, 0x0C), u32(data, 0x10)
    meta_s = u32(data, 0x14)
    off = align(hdr, 0x40)
    off = align(off + cert_s, 0x40)
    tik = off
    off = align(off + tik_s, 0x40)
    tmd = off
    off = align(off + tmd_s, 0x40)
    # content count from TMD (offset 0x1DE in signed TMD body for RSA-2048 sha256)
    sigtype = be32(data, tmd)
    siglen = {0x10000: 0x200, 0x10001: 0x100, 0x10002: 0x3C,
              0x10003: 0x200, 0x10004: 0x100, 0x10005: 0x3C}[sigtype]
    body = tmd + align(4 + siglen, 0x40)
    ncontents = be16(data, body + 0x9E)
    chunk = body + 0x9C4
    pos = off
    for i in range(ncontents):
        c = chunk + i * 0x30
        cid = be32(data, c)
        idx = be16(data, c + 4)
        ctype = be16(data, c + 6)
        csize = be64(data, c + 8)
        enc = bool(ctype & 0x01)
        lbl = f'{label}_c{idx}'
        print(f'[cia] content {idx} id={cid:08X} size={csize:#x} encrypted={enc}')
        if not enc and data[pos + 0x100:pos + 0x104] == b'NCCH':
            ncch_extract(data[pos:pos + csize], os.path.join(outbase, lbl), lbl)
        pos += csize


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'ncsd':
        extract_ncsd(sys.argv[2], sys.argv[3])
    elif cmd == 'cia':
        extract_cia(sys.argv[2], sys.argv[3])
    elif cmd == 'romfs':
        buf = open(sys.argv[2], 'rb').read()
        print(romfs_extract(buf, sys.argv[3]), 'files/dirs')
    elif cmd == 'lzss':
        open(sys.argv[3], 'wb').write(decompress_code(open(sys.argv[2], 'rb').read()))
