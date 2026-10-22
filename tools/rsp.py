#!/usr/bin/env python3
"""Minimal GDB Remote Serial Protocol client.

Enough of the protocol to attach to the Azahar / Citra GDB stub (default port
24689; Citra used 4000) and read and write the running game's memory without
needing a gdb binary or an ARM toolchain on this machine.

Packet framing: `$<payload>#<2 hex checksum>`, each packet acknowledged with
`+` (or `-` to ask for a resend) unless no-ack mode has been negotiated.
"""
import socket, time


class RspError(RuntimeError):
    pass


class Rsp:
    def __init__(self, host='127.0.0.1', port=24689, timeout=10.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = b''
        self.no_ack = False
        self.features = ''

    # -- framing ---------------------------------------------------------
    def close(self):
        self.sock.close()

    def _recv(self, n=4096):
        data = self.sock.recv(n)
        if not data:
            raise RspError('connection closed by the stub')
        self.buf += data

    @staticmethod
    def _checksum(payload):
        return sum(payload) & 0xFF

    def send(self, payload):
        if isinstance(payload, str):
            payload = payload.encode()
        pkt = b'$' + payload + b'#%02x' % self._checksum(payload)
        for attempt in range(5):
            self.sock.sendall(pkt)
            if self.no_ack:
                return
            while not self.buf:
                self._recv()
            ack, self.buf = self.buf[:1], self.buf[1:]
            if ack == b'+':
                return
            if ack == b'$':            # stub skipped the ack and replied
                self.buf = b'$' + self.buf
                return
            time.sleep(0.05)
        raise RspError('stub kept NAKing the packet')

    def recv(self):
        while True:
            start = self.buf.find(b'$')
            end = self.buf.find(b'#', start + 1) if start >= 0 else -1
            if start >= 0 and end >= 0 and len(self.buf) >= end + 3:
                payload = self.buf[start + 1:end]
                got = int(self.buf[end + 1:end + 3], 16)
                self.buf = self.buf[end + 3:]
                if self._checksum(payload) != got:
                    if not self.no_ack:
                        self.sock.sendall(b'-')
                    raise RspError('bad checksum from the stub')
                if not self.no_ack:
                    self.sock.sendall(b'+')
                return self._unescape(payload)
            self._recv()

    @staticmethod
    def _unescape(p):
        if b'}' not in p:
            return p
        out, esc = bytearray(), False
        for b in p:
            if esc:
                out.append(b ^ 0x20); esc = False
            elif b == 0x7D:
                esc = True
            else:
                out.append(b)
        return bytes(out)

    def cmd(self, payload):
        self.send(payload)
        return self.recv()

    # -- handshake -------------------------------------------------------
    def connect(self):
        self.features = self.cmd(
            'qSupported:swbreak+;hwbreak+;xmlRegisters=arm').decode('latin1')
        if 'QStartNoAckMode+' in self.features:
            if self.cmd('QStartNoAckMode') == b'OK':
                self.no_ack = True
        return self.features

    def halt_reason(self):
        return self.cmd('?').decode('latin1')

    # -- memory ----------------------------------------------------------
    def read_mem(self, addr, length, chunk=0x200):
        out = bytearray()
        while length:
            n = min(chunk, length)
            r = self.cmd(f'm{addr + len(out):x},{n:x}')
            if r.startswith(b'E') and len(r) == 3:
                raise RspError(f'read of {n:#x} bytes at {addr + len(out):#010x} '
                               f'refused: {r.decode()}')
            out += bytes.fromhex(r.decode())
            length -= n
        return bytes(out)

    def write_mem(self, addr, data, chunk=0x200):
        for i in range(0, len(data), chunk):
            part = data[i:i + chunk]
            r = self.cmd(f'M{addr + i:x},{len(part):x}:' + part.hex())
            if r != b'OK':
                raise RspError(f'write at {addr + i:#010x} refused: {r.decode()}')
        return len(data)

    def read_u32(self, addr):
        return int.from_bytes(self.read_mem(addr, 4), 'little')

    def write_u32(self, addr, value):
        return self.write_mem(addr, int(value & 0xFFFFFFFF).to_bytes(4, 'little'))

    # -- execution -------------------------------------------------------
    def interrupt(self):
        self.sock.sendall(b'\x03')
        return self.recv().decode('latin1')

    def cont(self):
        self.send('c')

    def regs(self):
        r = self.cmd('g').decode()
        return [int.from_bytes(bytes.fromhex(r[i:i + 8]), 'little')
                for i in range(0, min(len(r), 17 * 8), 8)]
