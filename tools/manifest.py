#!/usr/bin/env python3
"""Emit a TSV manifest of every file inside the hex-named romfs archives."""
import glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tdmarc import Archive, table_header

def rows(romfs):
    for p in sorted(glob.glob(os.path.join(romfs, '*'))):
        b = os.path.basename(p)
        if not os.path.isfile(p) or len(b) != 8 or any(c not in '0123456789ABCDEF' for c in b):
            continue
        a = Archive(p)
        for s in a.sections:
            z = a.zip(s)
            if z is not None:
                for i in z.infolist():
                    yield (f'{a.id:08X}', s['i'], s['kind'], 'zip', i.filename,
                           i.file_size, i.compress_size, '', '', '')
            else:
                data, _ = a.payload(s)
                try:
                    h = table_header(data)
                    yield (f'{a.id:08X}', s['i'], s['kind'], 'lz10/table',
                           h["name"].replace("\t"," "), len(data), s["size"],
                           h['type'], h['count'], h['rec_size'])
                except Exception:
                    yield (f'{a.id:08X}', s['i'], s['kind'], 'lz10/?',
                           '', len(data), s['size'], '', '', '')

if __name__ == '__main__':
    print('archive\tsection\tkind\tencoding\tname\tsize\tstored\ttable_type\trecords\trec_size')
    for r in rows(sys.argv[1]):
        print('\t'.join(str(x) for x in r))
