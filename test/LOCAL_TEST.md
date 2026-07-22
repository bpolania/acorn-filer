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
  └───────────────────────┘                 │        arm_gpt_server.py ⇄ Ollama
                                             └──────────────────────────────┘
```

Two ways to supply replies:

* **`--mock`** — canned/echoed replies, no Ollama, no ArmGPT server. This is the
  fast path for iterating on the UI: you see a prompt leave and a reply stream
  back, and ACORN returns to `you >`.
* **`--server`** — bridges to the real `arm_gpt_server.py` (macOS branch of the
  `ArmGPT` repo) for genuine qwen2.5 replies. Needs Ollama running.

> **What is verified:** the host-side `serial_bridge.py` (telnet handling, mock
> replies, and the pty relay) was tested on this machine. The emulator/RISC OS
> steps below could not be run here — treat them as a recipe to follow on your
> Mac, and expect to nudge a setting or two (noted inline).

---

## Path A — RPCEmu + RISC OS 5 (recommended)

RISC OS 5 has a **free, legal** ROM, and RPCEmu's *extended* fork is the only
emulator here with real serial redirection.

### 1. Install RPCEmu (extended fork, for serial)

Build/download **rpcemu-extended** (has parallel/serial redirection and a
universal macOS binary; Apple Silicon runs the interpreter core):
<https://github.com/andrewtimmins/rpcemu-extended>

### 2. Get the RISC OS 5 ROM (free)

From RISC OS Open, download the **IOMD softload ROM** and copy the `riscos`
file from `soft/!Boot/Resources/SoftLoad/` into RPCEmu's `roms/` directory.
Walkthrough: <https://www.riscosopen.org/wiki/documentation/show/RPCEmu%20and%20RISC%20OS%205%20on%20Mac%20OS%20X>

### 3. Get ACORN into the emulator

RPCEmu shares a host folder as **HostFS** (it appears as a disc icon on the
RISC OS icon bar). Copy `ACORN` and `test/DIAL` from this repo into that shared
folder. Then, in RISC OS, turn each text listing into a runnable BASIC program
(same `*EXEC` trick as the main README):

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

In RPCEmu: **Settings → Serial → TCP modem**. (This mode dials outbound over
TCP; there is no auto-answer, which is why `DIAL` exists.) Leave the baud at
9600 if asked.

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

### 7. Swap in the real ArmGPT server

Instead of `--mock`:

```bash
python3 serial_bridge.py --server
# prints e.g.  server port: /dev/ttys012
```

Then, in the `ArmGPT` repo (on the `macos` branch, with Ollama running and the
`qwen2.5:1.5b` + `nomic-embed-text` models pulled and the index built):

```bash
python3 arm_gpt_server.py --port /dev/ttys012
```

Re-run `DIAL` in the emulator. Now `you >` prompts reach qwen2.5 and the real
answer streams back. (The server ignores anything sent while it's generating,
and ends its reply with a newline — which is exactly what ACORN's idle-gap
detection expects, so no protocol changes are needed.)

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
python3 serial_bridge.py --server            # relay to arm_gpt_server via a pty
python3 serial_bridge.py --port 5623         # change the TCP port (match DIAL)
```

If you change the port, update `host$` at the top of `test/DIAL` to match.
