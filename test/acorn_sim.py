#!/usr/bin/env python3
"""
acorn_sim.py - terminal reproduction of the ACORN / ArmGPT chat client.

Mirrors the real ACORN MODE 12 UI in your terminal: the solid "armGPT"
wordmark splash, a DOS-style conversation menu down the left (bordered blue
panel, CHATS title, white selection bar), a scrolling white chat area, and
colour-coded you> / arm> prompts. Multiple conversations, each with its own
history.

Controls:  type + RETURN to send   TAB or up/down = switch chat
           Ctrl-N = new chat        ESC = quit

Reply sources:
  --mock             canned replies (default), no server.
  --server           relay to the ArmGPT server via a pseudo-terminal;
                     prints a /dev/ttys### to give to serial_codex_interface.py
                     (Codex CLI) or arm_gpt_server.py (Ollama).

Not pixel-authentic (a terminal can't be a real MODE 12 screen), but the
wordmark, menu, multi-chat, colours and flow all match. Pure standard library.
"""

import argparse
import os
import select
import shutil
import sys
import termios
import time
import tty

# ---- palette (SGR codes) ----
FG = {'k': 30, 'r': 31, 'g': 32, 'y': 33, 'b': 34, 'w': 37}
BG = {'k': 40, 'r': 41, 'b': 44, 'w': 47}

ART = [
 "                                   ######     ######   ##########",
 "                                  ########   ########  ##########",
 "                                 ###    ###  ###   ###     ##",
 "   ####    #  ##  #  ###  ###   ###      ##  ###    ##     ##",
 " #######   ###### ############  ##           ###    ##     ##",
 " ##   ###  ###    ###  ###  ##  ##           #########     ##",
 "      ###  ##     ##   ##   ##  ##    #####  ########      ##",
 "  #######  ##     ##   ##   ##  ##      ###  ###           ##",
 " ##   ###  ##     ##   ##   ##  ###      ##  ###           ##",
 " ##   ###  ##     ##   ##   ##   ###     ##  ###           ##",
 " ########  ##     ##   ##   ##    #########  ###           ##",
 "  #### ##  ##     ##   ##   ##     ######     #            ##"]
ARTW = 65

# double-line box drawing
TL, TR, BL, BR, HZ, VT, ML, MR = "╔╗╚╝═║╠╣"


# ---------------------------------------------------------------- backends
CANNED = [
 "Every word of this is arriving down an RS-423 wire at 9600 baud.",
 "I am ArmGPT, a small model running on the machine that named ARM.",
 "In my day we had 512K of RAM and we were grateful. Ask me anything.",
 "Slower than a modern GPU by a few million times, but far more stylish.",
 "A fine question for a computer from 1987. Let me ponder it a moment."]


class Mock:
    def __init__(self, delay):
        self.delay = delay
        self.n = 0

    def ask(self, prompt):
        if self.delay:
            time.sleep(self.delay)
        p = prompt.strip().lower()
        if p in ("bye", "quit", "exit"):
            return "Until next boot. 73!"
        if "year" in p:
            return "Out there it is 2026; in here it is forever 1987."
        if "who" in p or "name" in p:
            return "I am ArmGPT - the machine that named ARM, now with opinions."
        r = CANNED[self.n % len(CANNED)]
        self.n += 1
        return r


class Server:
    """Relay to the ArmGPT server over a pseudo-terminal."""
    def __init__(self):
        self.master, self.slave = os.openpty()
        self.path = os.ttyname(self.slave)
        # Turn off the pty's line-discipline echo, or our own prompt bounces
        # straight back and gets read as the "reply". (The server side opens
        # this same pty in raw mode too, but we must not depend on its timing.)
        a = termios.tcgetattr(self.slave)
        a[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON)   # lflag
        a[1] &= ~termios.ONLCR                                      # oflag
        termios.tcsetattr(self.slave, termios.TCSANOW, a)

    def banner(self):
        return ("server port: %s\n"
                "  -> in the ArmGPT repo (main branch), using ITS venv python\n"
                "     (system python3 lacks pyserial):\n"
                "       ./venv/bin/python serial_codex_interface.py --port %s"
                % (self.path, self.path))

    def ask(self, prompt):
        os.write(self.master, (prompt + "\r\n").encode("latin-1"))
        buf = bytearray()
        # Codex sends nothing until finished (~20-60s); wait generously for the
        # first byte, then a short idle gap once the reply starts arriving.
        while True:
            r, _, _ = select.select([self.master], [], [], 120 if not buf else 3)
            if not r:
                break
            try:
                chunk = os.read(self.master, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            if buf.rstrip().endswith(b"\n") and \
               select.select([self.master], [], [], 0.4)[0] == []:
                break
        return buf.decode("utf-8", "replace").strip()


# ---------------------------------------------------------------- the TUI
SBW = 24  # sidebar width


class App:
    def __init__(self, backend, cols=None, rows=None):
        self.backend = backend
        sz = shutil.get_terminal_size((80, 32))
        self.cols = cols or max(60, sz.columns)
        self.rows = rows or max(20, sz.lines)
        self.cells = None
        self.convs = []
        self.active = 0
        self.text = ""
        self.thinking = False
        self.quit = False
        self.cursor = None
        self.menu_rows = {}   # screen row -> ('new'|index)

    # ---- cell buffer ----
    def blank(self):
        self.cells = [[(" ", "k", "w") for _ in range(self.cols)]
                      for _ in range(self.rows)]

    def put(self, c, r, s, fg="k", bg="w"):
        if not (0 <= r < self.rows):
            return
        for i, ch in enumerate(s):
            if 0 <= c + i < self.cols:
                self.cells[r][c + i] = (ch, fg, bg)

    def fillrow(self, r, c0, c1, bg):
        for c in range(c0, c1 + 1):
            if 0 <= c < self.cols and 0 <= r < self.rows:
                ch, fg, _ = self.cells[r][c]
                self.cells[r][c] = (ch, fg, bg)

    def render(self):
        out = ["\x1b[?25l\x1b[H"]
        cur = None
        for r in range(self.rows):
            out.append("\x1b[%d;1H" % (r + 1))
            last = self.cols - (1 if r == self.rows - 1 else 0)
            for c in range(last):
                ch, fg, bg = self.cells[r][c]
                key = (fg, bg)
                if key != cur:
                    out.append("\x1b[%d;%dm" % (FG[fg], BG[bg]))
                    cur = key
                out.append(ch)
        out.append("\x1b[0m")
        if self.cursor:
            out.append("\x1b[%d;%dH\x1b[?25h" % (self.cursor[1] + 1, self.cursor[0] + 1))
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    # ---- conversations ----
    def new_conv(self):
        self.convs.append({"name": "Chat %d" % (len(self.convs) + 1),
                           "lines": [], "named": False})
        self.active = len(self.convs) - 1
        self.paint()

    def switch(self, i):
        if 0 <= i < len(self.convs) and i != self.active:
            self.active = i
            self.paint()

    def wrap(self, text, width):
        out, line = [], ""
        for word in text.split(" "):
            while len(word) > width:                 # very long token
                if line:
                    out.append(line); line = ""
                out.append(word[:width]); word = word[width:]
            if not line:
                line = word
            elif len(line) + 1 + len(word) <= width:
                line += " " + word
            else:
                out.append(line); line = word
        out.append(line)
        return out or [""]

    def add_msg(self, who, text):
        conv = self.convs[self.active]
        width = self.cols - (SBW + 1) - 1
        prefix = "you > " if who == 1 else "arm > "
        lines = self.wrap(prefix + text, width)
        for i, ln in enumerate(lines):
            kind = 1 if (who == 2 and i == 0) else 0    # red "arm > " on line 0
            conv["lines"].append((ln, kind))
        if who == 1 and not conv["named"]:
            conv["name"] = text[:SBW - 4]
            conv["named"] = True

    # ---- drawing ----
    def draw_status(self):
        right = "a 1987 original "
        bar = (" ArmGPT").ljust(self.cols - len(right)) + right
        self.put(0, 0, bar[:self.cols], "w", "k")

    def draw_sidebar(self):
        self.menu_rows = {}
        for r in range(1, self.rows):
            self.put(0, r, " " * SBW, "w", "b")
        self.put(0, 1, TL + HZ * (SBW - 2) + TR, "w", "b")
        for r in range(2, self.rows - 1):
            self.put(0, r, VT, "w", "b")
            self.put(SBW - 1, r, VT, "w", "b")
        self.put(0, self.rows - 1, BL + HZ * (SBW - 2) + BR, "w", "b")
        self.put((SBW - 5) // 2, 2, "CHATS", "y", "b")
        self.put(0, 3, ML + HZ * (SBW - 2) + MR, "w", "b")
        self.put(2, 5, "+ New chat", "w", "b")
        self.menu_rows[5] = "new"
        row = 7
        for i, conv in enumerate(self.convs):
            if row >= self.rows - 5:
                break
            name = conv["name"]
            if len(name) > SBW - 5:
                name = name[:SBW - 7] + ".."
            if i == self.active:
                self.fillrow(row, 1, SBW - 2, "w")
                self.put(2, row, name, "k", "w")
            else:
                self.put(2, row, name, "w", "b")
            self.menu_rows[row] = i
            row += 1
        self.put(2, self.rows - 5, "TAB / arrows", "w", "b")
        self.put(2, self.rows - 4, "  switch chat", "w", "b")
        self.put(2, self.rows - 3, "^N  new chat", "w", "b")
        self.put(2, self.rows - 2, "ESC quit", "w", "b")

    def draw_chat(self):
        left = SBW + 1
        top, bot = 1, self.rows - 1
        for r in range(top, bot + 1):
            self.fillrow(r, SBW, self.cols - 1, "w")
        conv = self.convs[self.active]
        lines = list(conv["lines"])
        if not lines:
            lines = [("ArmGPT is online. The serial link is open.", 0),
                     ("Say something and press RETURN.", 0), ("", 0)]
        if self.thinking:
            lines.append(("arm > thinking (Codex can take up to a minute)...", 1))
            input_line = None
        else:
            input_line = "you > " + self.text
        display = list(lines)
        if input_line is not None:
            display.append((input_line, 0))
        height = bot - top + 1
        start = max(0, len(display) - height)
        view = display[start:]
        for i, (txt, kind) in enumerate(view):
            r = top + i
            if kind == 1:
                self.put(left, r, txt[:6], "r", "w")
                self.put(left + 6, r, txt[6:], "k", "w")
            else:
                self.put(left, r, txt, "k", "w")
        if input_line is not None:
            r = top + len(view) - 1
            self.cursor = (left + len("you > ") + len(self.text), r)
        else:
            self.cursor = None

    def paint(self):
        self.blank()
        self.draw_status()
        self.draw_sidebar()
        self.draw_chat()
        self.render()

    # ---- splash ----
    def splash(self):
        self.blank()
        rule = "=" * (self.cols - 2)
        self.put(0, 1, rule, "k", "w")
        self.put(0, self.rows - 2, rule, "k", "w")
        ax = max(0, (self.cols - ARTW) // 2)
        ay = max(3, (self.rows - len(ART)) // 2 - 2)
        for i, line in enumerate(ART):
            for j, ch in enumerate(line):
                if ch == "#":
                    self.cells[ay + i][ax + j] = (" ", "k", "k")   # solid block
        def ctr(row, s, fg="k"):
            self.put((self.cols - len(s)) // 2, row, s, fg, "w")
        ctr(ay + len(ART) + 1, "ChatGPT on a 1987 Acorn Archimedes")
        ctr(ay + len(ART) + 2, "the machine that named ARM  .  now it talks back")
        ctr(self.rows - 5, "Press RETURN to continue")
        self.cursor = None
        self.render()
        while True:                       # wait for RETURN
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):
                return
            if ch == "\x1b" or ch == "\x03":
                self.quit = True
                return

    # ---- input ----
    def submit(self):
        line = self.text.strip()
        self.text = ""
        if not line:
            self.paint()
            return
        self.add_msg(1, line)
        self.thinking = True
        self.paint()
        reply = self.backend.ask(line)
        self.thinking = False
        self.add_msg(2, reply or "(no reply)")
        self.paint()

    def type_char(self, ch):
        if len(self.text) < self.cols - SBW - 10:
            self.text += ch
            self.paint()

    def backspace(self):
        if self.text:
            self.text = self.text[:-1]
            self.paint()

    def handle_esc(self):
        r, _, _ = select.select([sys.stdin], [], [], 0.03)
        if not r:
            self.quit = True
            return
        if sys.stdin.read(1) == "[":
            code = sys.stdin.read(1)
            if code == "A":
                self.switch(self.active - 1)
            elif code == "B":
                self.switch((self.active + 1) % max(1, len(self.convs)))

    def run(self):
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            sys.stdout.write("\x1b[2J")
            self.splash()
            if self.quit:
                return
            self.new_conv()
            while not self.quit:
                ch = sys.stdin.read(1)
                o = ord(ch)
                if o in (13, 10):
                    self.submit()
                elif o in (127, 8):
                    self.backspace()
                elif o == 9:
                    self.switch((self.active + 1) % max(1, len(self.convs)))
                elif o == 14:
                    self.new_conv()
                elif o == 3:
                    self.quit = True
                elif o == 27:
                    self.handle_esc()
                elif 32 <= o < 127:
                    self.type_char(ch)
        except KeyboardInterrupt:
            pass
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            sys.stdout.write("\x1b[0m\x1b[?25h\x1b[2J\x1b[H")
            sys.stdout.flush()
            print("Link closed. Bye.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true", help="canned replies (default)")
    mode.add_argument("--server", action="store_true",
                      help="relay to the ArmGPT server via a pty")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="mock: think-time seconds before replying (default 1)")
    args = ap.parse_args()

    backend = Server() if args.server else Mock(args.delay)

    if args.server:
        sys.stdout.write("\n" + backend.banner() + "\n\n")
        sys.stdout.write("Start that server in another terminal, then press "
                         "RETURN here to open the chat.\n")
        sys.stdout.flush()
        sys.stdin.readline()

    App(backend).run()


if __name__ == "__main__":
    main()
