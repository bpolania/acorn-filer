#!/usr/bin/env python3
"""
acorn_sim.py - a terminal stand-in for the ACORN RISC OS chat client.

Reproduces ACORN's look and feel on a normal terminal so you can exercise the
flow without an emulator:

  * the full-screen "armGPT" splash (press RETURN to continue),
  * the Sierra-style black-on-white status bar pinned to the top with the
    conversation scrolling beneath it,
  * colour-coded  you >  (yellow) and  arm >  (cyan) prompts, with the reply
    streamed back character by character as if it were arriving over serial.

Reply sources mirror serial_bridge.py:

  --mock            canned/echoed replies (default). No Ollama, no server.
  --server          talk to arm_gpt_server.py through a pseudo-terminal:
                    prints a /dev/ttys### to pass to  arm_gpt_server.py --port

This mirrors ACORN's layout maths and colours, but it is NOT the RISC OS
renderer - it's a design/flow stand-in. Pure standard library.

Examples
    python3 acorn_sim.py                 # mock replies
    python3 acorn_sim.py --delay 3       # fake 3s of think time
    python3 acorn_sim.py --server        # -> prints a pty for arm_gpt_server
"""

import argparse
import os
import select
import sys
import time

# ---- ANSI ----
ESC = "\033["
RESET = ESC + "0m"
CYAN = ESC + "36m"
YELLOW = ESC + "33m"
WHITE = ESC + "37m"
RED = ESC + "31m"
BAR = ESC + "30;47m"          # black text on white -> the status strip
CLEAR = ESC + "2J" + ESC + "H"
HIDE = ESC + "?25l"
SHOW = ESC + "?25h"


def sz():
    import shutil
    c = shutil.get_terminal_size((80, 24))
    return c.columns, c.lines


# The "armGPT" wordmark: lowercase "arm" in Arm's rounded logo style
# (figlet "puffy") fused with a capitalised GPT - identical to ACORN's.
ART = [
    r"                         ___    ___   _____",
    r"                        (  _`\ (  _`\(_   _)",
    r"   _ _  _ __   ___ ___  | ( (_)| |_) ) | |",
    r" /'_` )( '__)/' _ ` _ `\| |___ | ,__/' | |",
    r"( (_| || |   | ( ) ( ) || (_, )| |     | |",
    r"`\__,_)(_)   (_) (_) (_)(____/'(_)     (_)",
]
ARTW = 44

CANNED = [
    "Hello from 1987. I am ArmGPT, running on your Archimedes.",
    "Every one of these words is squeezing down an RS-423 wire at 9600 baud.",
    "The Acorn RISC Machine was born in this very box. Ask me anything.",
    "Slower than a modern GPU by a few million times, but far more stylish.",
]


def w(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def centre(cols, text):
    return " " * max(0, (cols - len(text)) // 2) + text


def splash():
    cols, rows = sz()
    w(CLEAR + HIDE)
    x = max(0, (cols - ARTW) // 2)
    y = max(2, (rows - len(ART)) // 2 - 2)
    w(CYAN + centre(cols, "=" * (cols - 2)) + "\n")
    w("\n" * (y - 1))
    for line in ART:
        w(CYAN + " " * x + line + "\n")
    w("\n")
    w(WHITE + centre(cols, "ChatGPT on a 1987 Acorn Archimedes") + "\n")
    w(CYAN + centre(cols, "the machine that named ARM  .  now it talks back") + "\n")
    w("\n" * 2)
    w(WHITE + centre(cols, "Press RETURN to continue") + RESET)
    w(SHOW)
    sys.stdin.readline()


def status_bar():
    cols, rows = sz()
    left, right = " ArmGPT", "a 1987 original "
    pad = max(1, cols - len(left) - len(right))
    w(CLEAR)
    w(BAR + left + " " * pad + right + RESET + "\n")
    w(ESC + "2;%dr" % rows)     # scroll region = row 2..bottom (bar stays put)
    w(ESC + "2;1H")            # cursor into the region
    w(CYAN + "ArmGPT is online. The serial link is open.\n")
    w(WHITE + "Say something and press RETURN.  An empty line closes the link.\n\n")


def teardown():
    w(ESC + "r")               # release the scroll region
    w(RESET + SHOW + "\n")


def stream(text, cps):
    """Print a reply the way ACORN sees it arrive - char by char."""
    w(WHITE)
    delay = 1.0 / cps if cps else 0
    for ch in text:
        w(ch)
        if delay:
            time.sleep(delay)
    w("\n\n")


class Mock:
    def __init__(self, delay):
        self.delay = delay
        self.n = 0

    def ask(self, prompt):
        if self.delay:
            time.sleep(self.delay)
        p = prompt.strip()
        if not p:
            return "Say something and I will answer."
        r = CANNED[self.n % len(CANNED)]
        self.n += 1
        return r


class Server:
    """Relay to arm_gpt_server.py over a pseudo-terminal."""
    def __init__(self):
        self.master, slave = os.openpty()
        self.path = os.ttyname(slave)

    def banner(self):
        return ("server port: %s\n  -> in the ArmGPT repo:  "
                "python3 arm_gpt_server.py --port %s" % (self.path, self.path))

    def ask(self, prompt):
        os.write(self.master, (prompt + "\r\n").encode("latin-1"))
        buf = bytearray()
        # read until the reply's trailing newline, then a short idle gap
        while True:
            r, _, _ = select.select([self.master], [], [], 30 if not buf else 3)
            if not r:
                break
            try:
                chunk = os.read(self.master, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if buf.rstrip().endswith(b"\n") and select.select([self.master], [], [], 0.3)[0] == []:
                break
        return buf.decode("latin-1", "replace").strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="canned replies (default)")
    mode.add_argument("--server", action="store_true",
                      help="relay to arm_gpt_server.py via a pty")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="mock: think-time seconds before replying (default 1)")
    ap.add_argument("--cps", type=float, default=220.0,
                    help="reply stream speed in chars/sec (0 = instant)")
    args = ap.parse_args()

    backend = Server() if args.server else Mock(args.delay)

    if args.server:
        # Print the pty path FIRST so you can start the server, then continue.
        sys.stdout.write("\n" + backend.banner() + "\n\n")
        sys.stdout.write("In another terminal, start that server (Ollama must be\n"
                         "running). Then press RETURN here to open the chat.\n")
        sys.stdout.flush()
        sys.stdin.readline()

    splash()
    status_bar()

    try:
        while True:
            try:
                line = input(YELLOW + "you > ")
            except EOFError:
                break
            finally:
                w(RESET)
            if line.strip() == "":
                break
            w(CYAN + "arm > " + RESET)
            reply = backend.ask(line)
            if reply:
                stream(reply, args.cps)
            else:
                w(RED + "...the line stays silent...\n\n" + RESET)
    except KeyboardInterrupt:
        pass
    finally:
        teardown()
        w("Link closed. Bye.\n")


if __name__ == "__main__":
    main()
