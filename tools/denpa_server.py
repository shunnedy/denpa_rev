#!/usr/bin/env python3
"""Prototype re-implementation of 電波人間のRPG FREE! の la1.denpamen.com.

Everything here was derived from the game's own code (see docs/13):
the client sends a plain HTTP GET, requires status 200, and parses the body as
comma separated text whose first field is `SUCCESS` or `ERROR`. Payloads that
carry a data table are base64 in the field after `SUCCESS,`, and the decoded
bytes go straight into the table loader - so serving a table means serving
base64 of exactly the blob format in docs/04.

  python3 tools/denpa_server.py --port 8080 \
      --table extracted/update_romfs/A9DF0000:CheckinData

The game talks HTTPS and pins a certificate, so in front of this you need
either a patched game (docs/07: swap the two words at 0x00288E04 / 0x00288E10)
or a TLS terminator holding a certificate the console accepts. `--cert` wraps
this server in TLS directly for the patched case.
"""
import argparse, base64, datetime, os, ssl, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TABLES = {}          # name -> raw table blob to hand out
LOG = []


def csv_ok(*fields):
    return 'SUCCESS' + (',' + ','.join(str(f) for f in fields) if fields else '')


def csv_err(code=10):
    return f'ERROR,{code}'


def now_stamp(when=None):
    """The 15-character form the client parses: YYYYMMDD<sep>HHMMSS."""
    w = when or datetime.datetime.now()
    return w.strftime('%Y%m%d %H%M%S')


# The client gives each request a fixed response buffer, so a payload cannot
# exceed it: 0x40 for the small status calls, 0x1000 for `bonus_tbl` and
# `player_data`, 0xA000 for the big `rand3`/`rank` listing. A 48 KB table
# therefore cannot arrive in one `bonus_tbl` response, which is why the query
# carries `tbl=` and `t_num=` - almost certainly table id and chunk index.
# That split is inferred, not yet confirmed in the code.
CHUNK = 3000

# Wi-Fi Colosseum opponent list (`req=rand3` / `rank`, 40 KB response buffer):
#   SUCCESS,<base64 A1>,<base64 B1>,<base64 A2>,<base64 B2>,...
# two fields per opponent, each base64, decoded straight into a fixed slot:
#   A = 0x20 bytes  (32)   -> entry + 8      most likely the team/player name
#   B = 0x4E8 bytes (1256) -> entry + 40     the party blob
# entry stride is 0x142 u32 = 1288 bytes. Sizes are read from the code
# (0x003EA2B0 holds 0x4E8); what the two blobs CONTAIN is not decoded yet.
OPP_NAME_LEN = 0x20
OPP_PARTY_LEN = 0x4E8
OPPONENTS = []


def opponent_fields(limit=3):
    """Two base64 fields per opponent: a 32-byte UTF-16 name and the 1256-byte
    party blob (tools/colosseum.py). The battle wants three."""
    out = []
    for name, party in OPPONENTS[:limit]:
        n = (name.encode('utf-16-le')[:OPP_NAME_LEN]).ljust(OPP_NAME_LEN, b'\0')
        p = party[:OPP_PARTY_LEN].ljust(OPP_PARTY_LEN, b'\0')
        out.append(base64.b64encode(n).decode('ascii'))
        out.append(base64.b64encode(p).decode('ascii'))
    return out


def table_payload(name, t_num=0, limit=None):
    blob = TABLES.get(name)
    if blob is None:
        return None
    b64 = base64.b64encode(blob).decode('ascii')
    if limit is None:
        return b64
    chunks = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)] or ['']
    if t_num >= len(chunks):
        return None
    return chunks[t_num]


def handle(path, q):
    """Return the response body for one request."""
    req = (q.get('req') or [''])[0]
    tbl = (q.get('tbl') or [''])[0]
    try:
        t_num = int((q.get('t_num') or ['0'])[0])
    except ValueError:
        t_num = 0

    if path.startswith('/ctr_state/'):
        # server-state probe; the game only needs a 200 with a SUCCESS line
        return csv_ok()

    if path == '/checkinserver':
        if req == 'time':
            return csv_ok(now_stamp())
        if req == 'bonus_tbl':
            payload = (table_payload('CheckinData', t_num, 0x1000)
                       or table_payload(tbl, t_num, 0x1000))
            return csv_ok(payload) if payload else csv_err(10)
        if req == 'check':
            # support_id is echoed back by the real server's check call
            return csv_ok(1, (q.get('support_id') or [''])[0])
        return csv_err(10)

    if path == '/gameserver':
        if req == 'res_ver':
            return csv_ok(1)
        if req == 'check':
            return csv_ok(1)
        if req == 'check_party':
            return csv_ok(1)
        if req in ('total', 'rank'):
            return csv_ok(0)
        if req == 'player_data':
            return csv_ok(0, 0, 0)
        if req in ('rand3', 'rand', 'top10', 'top'):
            fields = opponent_fields()
            return csv_ok(*fields) if fields else csv_ok()
        if req in ('current_party', 'prize_tbl'):
            payload = table_payload(req, t_num, 0xA000) or table_payload(tbl, t_num, 0xA000)
            return csv_ok(payload) if payload else csv_ok()
        return csv_err(10)

    if path == '/campaigncodeserver':
        return csv_err(10)          # no code is valid until the table is known

    return csv_err(10)


ACCESS_LOG = None        # path; every request line is appended here


def _log(line):
    print(line, file=sys.stderr, flush=True)
    if ACCESS_LOG:
        try:
            with open(ACCESS_LOG, 'a') as f:
                f.write(line + '\n')
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = 'denpamen-proto'

    def _serve(self, method):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        body = handle(u.path, q)
        LOG.append((u.path, q.get('req', [''])[0], len(body)))
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        hdr = {k: self.headers.get(k) for k in ('101', '103', '104', '105') if self.headers.get(k)}
        _log(f'{ts} {method} {self.path}  -> {body[:48]!r}  hdr={hdr}')
        raw = body.encode('ascii')
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        if method != 'HEAD':
            self.wfile.write(raw)

    def do_GET(self):
        self._serve('GET')

    def do_HEAD(self):
        self._serve('HEAD')

    def do_POST(self):
        # the retail game never POSTs, but log one if it appears
        n = int(self.headers.get('Content-Length') or 0)
        data = self.rfile.read(n) if n else b''
        _log(f'POST {self.path}  body[{len(data)}]={data[:64].hex()}')
        self._serve('POST')

    def log_message(self, fmt, *a):
        pass


def load_tables(specs):
    """--table <archive>:<TableName> pulls a table blob straight out of a romfs archive."""
    from tdmarc import Archive, table_header
    for spec in specs or []:
        arc, _, want = spec.partition(':')
        a = Archive(arc)
        for s in a.sections:
            z = a.zip(s)
            blobs = ([z.read(i) for i in z.infolist()
                      if i.filename.endswith(('.bin', '.dat'))] if z
                     else [a.payload(s)[0]])
            for d in blobs:
                if len(d) < 0x44:
                    continue
                h = table_header(d)
                if h['valid'] and (not want or h['name'] == want):
                    TABLES[h['name']] = d
                    print(f'table {h["name"]}: {h["count"]} records, {len(d)} bytes')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--table', action='append',
                    help='<archive path>:<TableName> to serve as a payload')
    ap.add_argument('--opponent', action='append', default=[],
                    help='NAME:party.blob  (party.blob from tools/colosseum.py)')
    ap.add_argument('--opponent-save', action='append', default=[],
                    help='NAME:save.bin  serve that save\'s party as an opponent')
    ap.add_argument('--opponents', type=int, default=0,
                    help='pad with N random-filler opponents (the game would '
                         'generate these locally anyway)')
    ap.add_argument('--log', help='append every request to this file')
    ap.add_argument('--cert', help='PEM certificate to wrap the socket in TLS')
    ap.add_argument('--key', help='its private key')
    a = ap.parse_args()
    global ACCESS_LOG
    ACCESS_LOG = a.log
    load_tables(a.table)
    for spec in a.opponent:
        name, _, path = spec.partition(':')
        OPPONENTS.append((name or 'CPU', open(path, 'rb').read()))
    for spec in a.opponent_save:
        import colosseum
        name, _, path = spec.partition(':')
        OPPONENTS.append((name or 'CPU', colosseum.pack_party(colosseum.records_from_save(path))))
    for i in range(a.opponents):
        OPPONENTS.append((f'CPU{i:02d}', bytes(OPP_PARTY_LEN)))
    if OPPONENTS:
        print(f'opponents: {len(OPPONENTS)} ' + ', '.join(n for n, _ in OPPONENTS))
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    if a.cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(a.cert, a.key)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    print(f'listening on {"https" if a.cert else "http"}://{a.host}:{a.port}')
    srv.serve_forever()


if __name__ == '__main__':
    main()
