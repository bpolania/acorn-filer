# Floppy Copy Agent Prompt

Use this prompt with a coding agent that has access to this repository and the
mounted floppy disk.

```text
You are preparing a single Acorn Archimedes demo floppy from the acorn-filer
repository.

Goal:
- Put the real serial client from the APM branch on the floppy as ACORN.
- Put the UI-only emulator/test client from the wimp-application branch on the
  same floppy as ACORNUI.
- Do not create pull requests.
- Do not rewrite history.
- Do not modify either branch unless explicitly asked.

Repository:
- Path: /Users/borpol01/Library/CloudStorage/OneDrive-Arm/Documents/GitHub/acorn-filer
- Source branch for ACORN: APM
- Source branch for ACORNUI: wimp-application

Steps:
1. Confirm the repository worktree is clean:
   git status --short --branch

2. Create a temporary staging directory:
   mkdir -p /tmp/acorn-floppy
   rm -f /tmp/acorn-floppy/ACORN /tmp/acorn-floppy/ACORNUI

3. Switch to the APM branch and copy the real client:
   git switch APM
   cp ACORN /tmp/acorn-floppy/ACORN

4. Switch to the wimp-application branch and copy the UI-only test client:
   git switch wimp-application
   cp ACORNUI /tmp/acorn-floppy/ACORNUI

5. Switch back to APM when done:
   git switch APM

6. Ask the user for the mounted floppy path if it is not obvious. On macOS, it
   may be under /Volumes/<disk-name>. Do not guess if multiple removable disks
   are mounted.

7. Copy the two staged files to the floppy:
   cp /tmp/acorn-floppy/ACORN /Volumes/<disk-name>/ACORN
   cp /tmp/acorn-floppy/ACORNUI /Volumes/<disk-name>/ACORNUI

8. List the floppy contents and confirm both files are present:
   ls -la /Volumes/<disk-name>

9. Tell the user to set the BASIC filetype on the Acorn after copying, unless
   the transfer path already preserves filetypes:
   *SETTYPE ACORN &FFB
   *SETTYPE ACORNUI &FFB

10. On the Acorn, the user can run:
    BASIC
    CHAIN "ACORN"

    Or for UI-only visual testing:
    BASIC
    CHAIN "ACORNUI"

Expected files on the floppy:
- ACORN    from branch APM
- ACORNUI  from branch wimp-application
```
