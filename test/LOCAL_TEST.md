# Testing ACORN locally on a Mac

The goal here is to exercise ACORN's **flow and look-and-feel** — the splash,
the Sierra-style status bar, the coloured `you >` / `arm >` prompts, and the
send → stream-reply → back-to-prompt cycle — by running the *real, unmodified*
`ACORN` BASIC program inside a RISC OS emulator. The serial link itself is
already tested on hardware, so here it's just a means to feed replies back.

```
  RISC OS guest (emulator)                 macOS host
  ┌───────────────────────┐        TCP     ┌──────────────────────────────┐
  │ DIAL  ── dials ─────────────────────────▶ serial_bridge.py            │
  │  └ CHAIN "ACORN"       │  127.0.0.1:5623 │   ├─ --mock  canned replies │
  │     type at "you >"    │◀──── reply ─────┤   └─ --server ⇄ pty ⇄        │
  └───────────────────────┘                 │        acorn_server.py        │
                                             └──────────────────────────────┘
```

## Most faithful — browser MODE 12 mockup (`acorn_mode12.html`)

`acorn_mode12.html` renders ACORN the way it looks on a real Acorn Archimedes:
a true white MODE 12 screen (80x32) drawn pixel-by-pixel in an 8x12 system font,
with the inverted black status bar, blue `you >` / red `arm >` prompts, and the
reply streamed back — inside a beige monitor with a subtle CRT glow. Open it in
any browser, click the screen, press RETURN, and chat (canned replies). This is
the closest reproduction of the real look-and-feel without hardware.

## Terminal stand-in — quick, no emulator (`acorn_sim.py`)

If you just want to see ACORN's flow and look-and-feel immediately, skip the
emulator entirely:

```bash
cd acorn-filer/test
python3 acorn_sim.py            # mock replies; --delay 3 fakes think-time
python3 acorn_sim.py --server   # drive the real ArmGPT server via a pty
```

This reproduces ACORN's full UI in your terminal — the solid `armGPT` splash,
the black-on-white status bar, the **DOS conversation menu** down the left, and
colour-coded `you >` / `arm >` prompts. Type and press RETURN to send; **TAB**
or **up/down** switch conversation, **Ctrl-N** starts a new one, **Ctrl-L**
switches local/codex server mode, and **ESC** quits.
Each conversation keeps its own history. It mirrors ACORN's layout, menu and
colours, but a terminal can't be a true white MODE 12 screen — for the real
pixels, use the emulator path below.

### Real replies via the hybrid ArmGPT server

The `ArmGPT` repo's host server is `acorn_server.py`. It reads one
newline-terminated prompt from serial and sends back one newline-terminated
response. It can route requests to either a local model or Codex/ChatGPT.

ACORN sends plain text only. These commands are preserved exactly:

```
/mode local
/mode codex
/local <prompt>
/codex <prompt>
/status
/help
```

Plain prompts are sent unchanged and the server routes them using its current
mode. `Ctrl-L` in ACORN toggles local/codex by sending `/mode local` or
`/mode codex`. `/quit` exits ACORN locally and is not sent to the server.

**Easiest — one command** (the sim launches the server against its own pty, so
there's no second terminal and no pty-path copying):

```bash
cd acorn-filer/test
python3 acorn_sim.py --codex
#   (assumes the ArmGPT repo at ~/Documents/GitHub/ArmGPT on its main branch;
#    override with --armgpt-dir <path>. Server log: /tmp/acorn_hybrid_server.log)
```

Press RETURN past the splash and chat. Use `/status`, `/mode local`,
`/mode codex`, or `Ctrl-L` to verify server mode switching.

**Manual (two terminals)** — the same thing wired by hand, verified on this
machine:

1. **Terminal A** — start the sim; it prints a pty device path, then waits:
   ```bash
   cd acorn-filer/test
   python3 acorn_sim.py --server
   #  -> server port: /dev/ttysNNN
   ```
2. **Terminal B** — point the server at that pty, **using the ArmGPT venv's
   Python** (system `python3` may lack `pyserial` and crash on startup).
   Codex mode needs Codex/ChatGPT credentials configured on the host:
   ```bash
   cd ~/Documents/GitHub/ArmGPT      # on the main branch
   ./venv/bin/python acorn_server.py --port /dev/ttysNNN
   ```
3. Back in **Terminal A**, press RETURN → RETURN, then chat. Codex/ChatGPT
   replies may take tens of seconds and send nothing until complete, so ACORN
   waits up to `waitmax%` for the first byte.

---

Two ways `acorn_sim.py` supplies replies:

* **`--mock`** — canned replies, no server. Fast path for iterating on the UI.
* **`--server`** — bridges to the real hybrid ArmGPT server
  (`acorn_server.py`) via a pty for genuine replies.

> **What is verified:** the host-side `serial_bridge.py` (telnet handling, mock
> replies, and the pty relay) was tested on this machine. The emulator/RISC OS
> steps below could not be run here — treat them as a recipe to follow on your
> Mac, and expect to nudge a setting or two (noted inline).

---

## Path A — RPCEmu + RISC OS 5 (recommended)

RISC OS 5 has a **free, legal** ROM, and RPCEmu's *extended* fork is the only
emulator here with real serial redirection.

### 1. Build RPCEmu (extended fork, for serial)

The **rpcemu-extended** fork has the serial redirection we need:
<https://github.com/andrewtimmins/rpcemu-extended>

```bash
git clone https://github.com/andrewtimmins/rpcemu-extended
cd rpcemu-extended
brew install cmake ninja pkg-config wxwidgets sdl2 libvncserver
./build-macos.sh --arch arm64      # Apple Silicon: interpreter slice only
```

The build stages a runnable folder at `releases/macos/arm64/` containing the
`rpcemu` binary plus its resource dirs. Run it from inside that folder
(`./rpcemu`) so it finds its resources. (The `x86_64` recompiler slice needs a
second, Rosetta Homebrew prefix and isn't necessary just to run.)

### 2. RISC OS 5 ROM — already included

This fork **bundles RISC OS 5.30** (`roms/ROM530`) and a hard-disc image, and
its default config (`configs/Default.cfg`) already sets `rom_dir=ROM530` and
`serial_com1_mode=2` (TCP modem). So there's no separate ROM to source, and the
serial step (below) is pre-configured.

### 3. Get ACORN into the emulator

RPCEmu shares a host folder as **HostFS** (it appears as a disc icon on the
RISC OS icon bar), located at `machines/Default/hostfs/` inside the staged
folder. Copy `ACORN` and `test/DIAL` there. To have RISC OS see them as text
(so `*EXEC` works), give each a `,fff` filetype suffix on the host side:

```bash
perl -pe 's/\n/\r/g' ACORN     > <rpcemu>/machines/Default/hostfs/ACORN,fff
perl -pe 's/\n/\r/g' test/DIAL > <rpcemu>/machines/Default/hostfs/DIAL,fff
```

Then, in RISC OS, turn each listing into a runnable BASIC program (same `*EXEC`
trick as the main README):

```
*BASIC
NEW
*EXEC ACORN
SAVE "ACORN"
NEW
*EXEC DIAL
SAVE "DIAL"
QUIT
```

### 4. Point the emulated serial at the bridge

The bundled default config already has COM1 in **TCP modem** mode
(`serial_com1_mode=2`). If you use a different config, set it via
**Settings → Serial → TCP modem**. (This mode dials outbound over TCP; there is
no auto-answer, which is why `DIAL` exists.)

### 5. Start the bridge on the Mac

```bash
cd acorn-filer/test
python3 serial_bridge.py --mock            # add --delay 3 to fake "think time"
```

It prints `waiting for the emulator to dial in on 127.0.0.1:5623 ...`.

### 6. Run it

In RISC OS: `*BASIC` then `CHAIN "DIAL"` (or double-click `DIAL`). It dials the
bridge, discards the modem's `CONNECT` chatter, and `CHAIN`s the unmodified
`ACORN`. You should get the full-screen splash → RETURN → status bar → type at
`you >` → a reply streams back under `arm >` → back to `you >`. An empty line
quits and restores the entry screen mode.

### 7. Swap in the real hybrid ArmGPT server

Instead of `--mock`:

```bash
python3 serial_bridge.py --server
# prints e.g.  server port: /dev/ttys012
```

Then, in the `ArmGPT` repo, start the hybrid serial server. Local mode needs
the configured local model runtime; codex mode needs Codex/ChatGPT credentials
configured on the host:

```bash
python3 acorn_server.py --port /dev/ttys012
```

Re-run `DIAL` in the emulator. Now `you >` prompts reach the server and the
real answer streams back. Try `/status`, `/mode local`, `/mode codex`, and
`Ctrl-L`. The server ends each reply with a newline, and ACORN also has an
idle-gap guard so it returns to the prompt after each response.

---

## Path B — Arculator (most authentic A310 look, UI only)

Arculator emulates the actual **A310** hardware, so the RISC OS 3.1 rendering of
the splash, MODE 12, and the status bar looks exactly as it does on your
machine. macOS port: <https://github.com/richstokes/arculator-mac>

Two caveats:

* The RISC OS 2/3 ROM is **copyrighted** — you must supply it (e.g. dumped from
  your own machine).
* Arculator has no usable host serial redirection here, so **replies won't
  stream** — typing a prompt will just wait and then show
  `...the line stays silent...`. Use this path to eyeball the look-and-feel on
  the authentic A310; use Path A to test the full conversational flow.

---

## Bridge reference

```
python3 serial_bridge.py --mock              # canned replies (default)
python3 serial_bridge.py --mock --delay 2.5  # simulate LLM latency
python3 serial_bridge.py --server            # relay to acorn_server.py via a pty
python3 serial_bridge.py --port 5623         # change the TCP port (match DIAL)
```

If you change the port, update `host$` at the top of `test/DIAL` to match.
