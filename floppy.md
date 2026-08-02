# Floppy Copy Agent Prompt

Use this prompt with a coding agent that has access to this repository and the
mounted floppy disk.

```text
You are preparing a single Acorn Archimedes demo floppy from the acorn-filer
repository.

Goal:
- Put the real serial client from the canonical main branch on the floppy as ACORN.
- Put the Desktop/TaskWindow ACORNUI client from the canonical main branch on the
  same floppy as ACORNUI.
- Do not create pull requests.
- Do not rewrite history.
- Do not modify branches unless explicitly asked.

Repository:
- Path: /Users/borpol01/Library/CloudStorage/OneDrive-Arm/Documents/GitHub/acorn-filer
- Source branch for ACORN: main
- Source branch for ACORNUI: main

Steps:
1. Confirm the repository worktree is clean:
   git status --short --branch

2. Create a temporary staging directory:
   mkdir -p /tmp/acorn-floppy
   rm -f /tmp/acorn-floppy/ACORN /tmp/acorn-floppy/ACORNUI

3. Switch to the main branch and copy the real client as a CR-only text
   listing so Acorn `*EXEC` can import it reliably:
   git switch main
   perl -pe 's/\n/\r/g' ACORN > /tmp/acorn-floppy/ACORN

4. Copy the Desktop/TaskWindow ACORNUI client as a CR-only text listing:
   perl -pe 's/\n/\r/g' ACORNUI > /tmp/acorn-floppy/ACORNUI

5. Ask the user for the mounted floppy path if it is not obvious. On macOS, it
   may be under /Volumes/<disk-name>. Do not guess if multiple removable disks
   are mounted.

6. Copy the two staged files to the floppy:
   cp /tmp/acorn-floppy/ACORN /Volumes/<disk-name>/ACORN
   cp /tmp/acorn-floppy/ACORNUI /Volumes/<disk-name>/ACORNUI

7. List the floppy contents and confirm both files are present:
   ls -la /Volumes/<disk-name>

8. Tell the user to set the text filetype on the Acorn after copying, unless
   the transfer path already preserves filetypes:
   *SETTYPE ACORN &FFF
   *SETTYPE ACORNUI &FFF

9. On the Acorn, the user can run:
    *SETTYPE ACORN &FFF
    BASIC
    NEW
    *EXEC ACORN
    SAVE "ACORNRUN"
    CHAIN "ACORNRUN"

    Or for the ACORNUI Desktop/TaskWindow build:
    *SETTYPE ACORNUI &FFF
    BASIC
    NEW
    *EXEC ACORNUI
    SAVE "ACORNUIR"
    CHAIN "ACORNUIR"

Expected files on the floppy:
- ACORN    from branch main
- ACORNUI  from branch main

ACORN talks to the host-side hybrid server using plain newline-terminated text.
It supports `/mode local`, `/mode cloud`, `/local <prompt>`, `/cloud <prompt>`,
`/status`, and `/help`; `Ctrl-L` toggles local/cloud mode by sending `/mode ...`
to the server. If the host still expects older codex command names, ACORN maps
cloud commands to the codex protocol names on the serial wire. `/quit` exits
locally and is not sent.

ACORNUI uses the same serial protocol, but it avoids full-screen MODE 12 drawing
so it can be run from a RISC OS Desktop TaskWindow or command window.
```
