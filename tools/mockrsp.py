#!/usr/bin/env python3
"""A stand-in GDB stub, so the injection tooling can be tested without Azahar.

Serves one connection, keeps a sparse memory image, and answers the subset of
the protocol that tools/inject.py uses.
"""
import socket, sys


class Mock:
    def __init__(self, regions):
        self.mem = {}
        for base, data in regions:
            for i, b in enumerate(data):
                self.mem[base + i] = b

    def read(self, addr, n):
        return bytes(self.mem.get(addr + i, 0) for i in range(n))

    def write(self, addr, data):
        for i, b in enumerate(data):
            self.mem[addr + i] = b

    def handle(self, p):
        if p.startswith(b'qSupported'):
            return b'PacketSize=1000;QStartNoAckMode+;swbreak+'
        if p == b'QStartNoAckMode':
            return b'OK'
        if p == b'?':
            return b'S05'
        if p == b'g':
            return (b'00' * 4) * 17
        if p.startswith(b'm'):
            a, n = p[1:].split(b',')
            return self.read(int(a, 16), int(n, 16)).hex().encode()
        if p.startswith(b'M'):
            head, hexdata = p[1:].split(b':')
            a, n = head.split(b',')
            self.write(int(a, 16), bytes.fromhex(hexdata.decode()))
            return b'OK'
        return b''


def serve(port, regions, once=True):
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', port))
    srv.listen(1)
    print(f'mock stub on {port}', flush=True)
    m = Mock(regions)
    while True:
        c, _ = srv.accept()
        buf = b''
        no_ack = False
        try:
            while True:
                d = c.recv(4096)
                if not d:
                    break
                buf += d
                while True:
                    if buf[:1] in (b'+', b'-', b'\x03'):
                        buf = buf[1:]; continue
                    s, e = buf.find(b'$'), buf.find(b'#')
                    if s < 0 or e < 0 or len(buf) < e + 3:
                        break
                    payload = buf[s + 1:e]
                    buf = buf[e + 3:]
                    if not no_ack:
                        c.sendall(b'+')
                    resp = m.handle(payload)
                    if payload == b'QStartNoAckMode':
                        no_ack = True
                    c.sendall(b'$' + resp + b'#%02x' % (sum(resp) & 0xFF))
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass            # a client that walks away must not kill the stub
        finally:
            c.close()
        if once:
            return


if __name__ == '__main__':
    # a toy image: a vtable in .data and a function in .text
    regions = [(0x0047DC48, bytes.fromhex('01105000' '11105000' '21105000' '31105000')),
               (0x0012DB88, bytes.fromhex('80b500af' '0346fff7' '00f880bd'))]
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 24689, regions)
