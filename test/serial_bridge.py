#!/usr/bin/env python3
"""
serial_bridge.py - host-side bridge for testing ACORN in an emulator.

RPCEmu's serial port ("TCP modem" mode) lets the RISC OS guest dial out with
    ATDT 127.0.0.1:5623
and then passes bytes transparently (it negotiates telnet BINARY mode, so the
link is 8-bit clean). This script sits on the other end of that TCP connection
and gives ACORN something to talk to, in one of two modes:

  --mock            Reply with canned/echoed text. No Ollama, no server, no
                    dependencies. Best for iterating on ACORN's flow and
                    look-and-feel: you see the prompt go out and a reply stream
                    back, and ACORN returns to the "you >" prompt.

  --server          Create a pseudo-terminal (pty) and print its device path.
                    You point arm_gpt_server.py at that path with --port, and
                    this bridge relays raw bytes between the emulator and the
                    real ArmGPT server (which needs Ollama running).

Both modes handle the minimal telnet negotiation RPCEmu performs, so the guest
sees a clean binary stream.

Examples
    python3 serial_bridge.py --mock
    python3 serial_bridge.py --mock --delay 2.0
    python3 serial_bridge.py --server
        -> prints e.g. "server port: /dev/ttys012"
        then in the ArmGPT repo:  python3 arm_gpt_server.py --port /dev/ttys012

This file is pure standard library (no pyserial / socat needed).
"""

import argparse
import os
import select
import socket
import sys
import time

# ---- telnet ----------------------------------------------------------------
IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
BINARY, SGA = 0, 3


class Telnet:
    """Minimal telnet parser: strips IAC commands from the data stream and
    answers option negotiation so the peer will run in 8-bit binary mode."""

    def __init__(self):
        self.buf = b""

    def hello(self):
        # Proactively ask for a clean binary, no-go-ahead link.
        return bytes([IAC, WILL, BINARY, IAC, DO, BINARY,
                      IAC, WILL, SGA, IAC, DO, SGA])

    def feed(self, data):
        """Return (clean_data, reply_to_send)."""
        self.buf += data
        out, reply = bytearray(), bytearray()
        i, n = 0, len(self.buf)
        while i < n:
            b = self.buf[i]
            if b != IAC:
                out.append(b)
                i += 1
                continue
            if i + 1 >= n:
                break  # incomplete IAC, wait for more
            cmd = self.buf[i + 1]
            if cmd == IAC:                      # escaped 0xFF -> literal byte
                out.append(IAC)
                i += 2
            elif cmd in (DO, DONT, WILL, WONT):
                if i + 2 >= n:
                    break                       # incomplete, wait
                opt = self.buf[i + 2]
                reply += self._negotiate(cmd, opt)
                i += 3
            elif cmd == SB:                     # skip subnegotiation to IAC SE
                j = self.buf.find(bytes([IAC, SE]), i + 2)
                if j == -1:
                    break
                i = j + 2
            else:                               # other 2-byte command, drop it
                i += 2
        self.buf = self.buf[i:]
        return bytes(out), bytes(reply)

    @staticmethod
    def _negotiate(cmd, opt):
        if cmd == DO:
            return bytes([IAC, WILL if opt in (BINARY, SGA) else WONT, opt])
        if cmd == WILL:
            return bytes([IAC, DO if opt in (BINARY, SGA) else DONT, opt])
        return b""  # DONT / WONT need no reply


def esc(data):
    """Escape IAC bytes for sending payload back to a telnet peer."""
    return data.replace(bytes([IAC]), bytes([IAC, IAC]))


# ---- mock replies ----------------------------------------------------------
CANNED = [
    "Hello from 1987. I am ArmGPT, running on your Archimedes.",
    "Every one of these words is squeezing down an RS-423 wire at 9600 baud.",
    "The Acorn RISC Machine was born in this very box. Ask me anything.",
    "Slower than a modern GPU by a few million times, but far more stylish.",
]


def mock_reply(prompt, count):
    p = prompt.strip()
    if not p:
        return "Say something and I will answer."
    if p.lower() in ("bye", "quit", "exit"):
        return "Until next boot. 73!"
    base = CANNED[count % len(CANNED)]
    return base


# ---- connection handling ---------------------------------------------------
def accept(listener):
    print("waiting for the emulator to dial in on %s:%d ..."
          % listener.getsockname(), flush=True)
    conn, addr = listener.accept()
    print("connected from %s:%d" % addr, flush=True)
    return conn


def run_mock(listener, delay):
    count = 0
    while True:
        conn = accept(listener)
        tn = Telnet()
        conn.sendall(tn.hello())
        line = bytearray()
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                clean, reply = tn.feed(data)
                if reply:
                    conn.sendall(reply)
                for b in clean:
                    if b in (10, 13):           # end of a prompt line
                        if line:
                            prompt = bytes(line).decode("latin-1")
                            line.clear()
                            print("  prompt: %r" % prompt, flush=True)
                            if delay:
                                time.sleep(delay)
                            r = mock_reply(prompt, count)
                            count += 1
                            print("  reply : %r" % r, flush=True)
                            conn.sendall(esc((r + "\n").encode("latin-1")))
                    else:
                        line.append(b)
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            conn.close()
            print("emulator disconnected; waiting for a new call", flush=True)


def run_server(listener):
    master, slave = os.openpty()
    print("server port: %s" % os.ttyname(slave), flush=True)
    print("  -> in the ArmGPT repo:  python3 arm_gpt_server.py --port %s"
          % os.ttyname(slave), flush=True)
    while True:
        conn = accept(listener)
        tn = Telnet()
        conn.sendall(tn.hello())
        conn.setblocking(False)
        try:
            while True:
                r, _, _ = select.select([conn, master], [], [])
                if conn in r:
                    data = conn.recv(4096)
                    if not data:
                        break
                    clean, reply = tn.feed(data)
                    if reply:
                        conn.sendall(reply)
                    if clean:
                        os.write(master, clean)   # -> arm_gpt_server (readline)
                if master in r:
                    out = os.read(master, 4096)    # reply from arm_gpt_server
                    if out:
                        conn.sendall(esc(out))
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            conn.close()
            print("emulator disconnected; waiting for a new call", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5623,
                    help="TCP port the emulator dials (default 5623)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true",
                      help="answer with canned replies (default)")
    mode.add_argument("--server", action="store_true",
                      help="relay to arm_gpt_server.py via a pseudo-terminal")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="mock: seconds to wait before replying (fakes think time)")
    args = ap.parse_args()

    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((args.host, args.port))
    listener.listen(1)

    try:
        if args.server:
            run_server(listener)
        else:
            run_mock(listener, args.delay)
    except KeyboardInterrupt:
        print("\nbye", flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
