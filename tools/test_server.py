#!/usr/bin/env python3
"""Check the prototype server against the parsing rules taken from the game.

The game's own code decides what a valid response is, so the test mirrors it:
status 200, a comma separated body, first field `SUCCESS`, and for a table
payload the bytes after `SUCCESS,` must base64-decode into something the table
loader accepts. `req=time` is checked against the fixed-width date parse
(4+2+2, skip one, 2+2+2) the client performs.
"""
import base64, os, sys, threading, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import denpa_server
from tdmarc import table_header

PORT = 18923
fails = []


def check(name, got, want):
    ok = got == want
    print(f'  {"ok  " if ok else "FAIL"} {name}: {got}' + ('' if ok else f' != {want}'))
    if not ok:
        fails.append(name)


def get(path):
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}{path}', timeout=10) as r:
        return r.status, r.read().decode('ascii')


def split_csv(body):
    """What the game does: count commas, then slice between them."""
    return body.split(',')


def main(archive, want_table):
    denpa_server.load_tables([f'{archive}:{want_table}'])
    srv_cls = denpa_server.ThreadingHTTPServer
    srv = srv_cls(('127.0.0.1', PORT), denpa_server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)

    print('req=time:')
    st, body = get('/checkinserver?req=time&tbl=checkin&prod=checkin_dev')
    f = split_csv(body)
    check('status 200', st, 200)
    check('field0 is SUCCESS', f[0], 'SUCCESS')
    stamp = f[1]
    check('date field is at least 15 chars', len(stamp) >= 15, True)
    year, month, day = int(stamp[0:4]), int(stamp[4:6]), int(stamp[6:8])
    hour, minute, second = int(stamp[9:11]), int(stamp[11:13]), int(stamp[13:15])
    check('fixed-width parse gives a sane date',
          1 <= month <= 12 and 1 <= day <= 31 and hour < 24
          and minute < 60 and second < 60 and year > 2000, True)

    print('req=bonus_tbl:')
    st, body = get('/checkinserver?req=bonus_tbl&tbl=checkin&prod=checkin_dev')
    check('status 200', st, 200)
    check('starts with "SUCCESS,"', body.startswith('SUCCESS,'), True)
    check('fits the client response buffer (0x1000)', len(body) <= 0x1000, True)
    # reassemble every chunk the way a chunked client would
    parts, n = [], 0
    while True:
        st, b = get(f'/checkinserver?req=bonus_tbl&tbl=checkin&t_num={n}')
        if b.startswith('ERROR'):
            break
        parts.append(b[len('SUCCESS,'):])
        n += 1
        if n > 200:
            break
    blob = base64.b64decode(''.join(parts))
    h = table_header(blob)
    orig = denpa_server.TABLES[want_table]
    check(f'{n} chunks reassemble byte exact', blob == orig, True)
    check('decoded blob is a valid table', h['valid'], True)
    check('table name survives', h['name'], want_table)
    check('record count survives', h['count'], table_header(orig)['count'])

    print('req=rand3 (Wi-Fi Colosseum opponent list):')
    denpa_server.OPPONENTS.clear()
    for i in range(3):
        denpa_server.OPPONENTS.append(
            (f'あいて{i}', bytes((i + j) & 0xFF for j in range(denpa_server.OPP_PARTY_LEN))))
    st, body = get('/gameserver?req=rand3&prod=ranking_dev&reg=0')
    f = split_csv(body)
    check('field0 is SUCCESS', f[0], 'SUCCESS')
    check('two fields per opponent', len(f) - 1, 6)
    check('fits the 0xA000 response buffer', len(body) <= 0xA000, True)
    names = [base64.b64decode(f[1 + i * 2]) for i in range(3)]
    parties = [base64.b64decode(f[2 + i * 2]) for i in range(3)]
    check('name blob is 0x20 bytes', {len(n) for n in names}, {0x20})
    check('party blob is 0x4E8 bytes', {len(p) for p in parties}, {0x4E8})
    check('name decodes as UTF-16LE',
          names[0].decode('utf-16-le').rstrip('\0'), 'あいて0')

    print('errors and the rest:')
    st, body = get('/checkinserver?req=nonsense')
    check('unknown req -> ERROR,<code>', body.split(',')[0], 'ERROR')
    check('error carries a numeric code', body.split(',')[1].isdigit(), True)
    st, body = get('/gameserver?req=res_ver&tbl=1')
    check('gameserver res_ver', body, 'SUCCESS,1')
    st, body = get('/ctr_state/gs_j')
    check('server-state probe', body, 'SUCCESS')
    st, body = get('/gameserver?req=check_party&pid=12345')
    check('check_party', body.split(',')[0], 'SUCCESS')

    srv.shutdown()
    print('\nFAILED:' if fails else '\nall checks passed', *fails)
    return 1 if fails else 0


if __name__ == '__main__':
    arc = sys.argv[1] if len(sys.argv) > 1 else 'extracted/update_romfs/A9DF0000'
    tbl = sys.argv[2] if len(sys.argv) > 2 else 'CheckinData'
    sys.exit(main(arc, tbl))
