# MW4 Linux Patcher

**Patch a supported Windows MW4 campaign installation to run on Linux through Proton.**

`mw4-linux` checks your game build, applies the startup compatibility patch, launches the campaign and lets you restore the original files. The patch handles the Windows device request and startup checks that block this build under Wine; Proton and VKD3D handle execution and rendering.

```text
Windows campaign files → apply patch → launch through Proton → Linux
```

**Alpha · Linux x86-64 · offline campaign.** Campaign gameplay tested by the author on Bazzite with an RX 7900 XTX and i5-12400F. Includes backup/restore, nine regression tests and a live ptrace test.

### Supported build

Windows campaign download page: [FitGirl — Call of Duty: Modern Warfare 4](https://fitgirl-repacks.site/call-of-duty-modern-warfare-4/). Run `doctor` on the installed files before patching: this link alone does not establish that its current download matches the supported fingerprints.

The current profile requires the exact offline campaign executable and `rex_sp.dll` fingerprints in [build_profile.py](../build_profile.py). `doctor` checks these before you install. Other builds, untouched retail installations, multiplayer and macOS are currently unsupported. Full campaign completion and broader controller testing remain open; see the [validation record](../research/validation.md).

## Requirements

- Linux x86-64 and Python 3.10+; no pip dependencies.
- Your existing supported campaign installation, with `sp26/sp26-cod.exe` and `sp26/rex_sp.dll`.
- Working [UMU](https://github.com/Open-Wine-Components/umu-launcher) and Proton. The tested setup used UMU 1.4.4, GE-Proton11-9 and steamrt4 `4.0.20261021.265997`.
- The two already-obtained VKD3D DLLs matching `GRAPHICS` in `build_profile.py`. Their exact source/build provenance has not been reproduced, so this repo does not offer a fresh-build graphics download. The tested runtime identifies itself as VKD3D-Proton 3.1.0, `0bb64c56c8f0dcc+`.
- A dedicated Wine prefix; keep existing saves and offline identity configuration. The test used a cloned working prefix, not a new empty one.
- Permission to trace the launched process. The tool refuses restrictive Yama settings; it never changes host policy or uses sudo.

Provide these dependencies before installing; the patcher does not download them.

## Install the patch

Close MW4. Make a separate copy of your installation and Wine prefix. On the same Btrfs filesystem, `cp -a --reflink=always SOURCE TEST_COPY` shares unchanged data blocks while keeping subsequent writes separate. Do not copy a prefix while its Wine processes are running.

`GAME` below is the directory containing `sp26/`, not the executable directory. Use real absolute paths in place of the examples.

```bash
git clone https://github.com/PotatoSpudowski/mw4-linux.git
cd mw4-linux
python3 mw4.py doctor --game /path/to/test-game
python3 mw4.py install --game /path/to/test-game \
  --graphics /path/to/already-verified-vkd3d-dlls
```

`doctor` reads files only. `install` verifies the complete input set first, backs up affected files under `GAME/.mw4-linux`, writes a receipt, then prepares the DLL and installs the graphics overrides. It does not alter saves, offline identity configuration, Steam shortcuts or host settings.

Launch from your graphical desktop terminal first:

```bash
python3 mw4.py launch --game /path/to/test-game \
  --umu /absolute/path/to/umu-run \
  --proton /absolute/path/to/GE-Proton11-9 \
  --prefix /absolute/path/to/dedicated-test-prefix \
  --game-argument 'ARGUMENT_FROM_YOUR_EXISTING_CAMPAIGN_LAUNCHER'
```

For a portable installation whose UMU runtime is stored beneath a private HOME, also pass `--home /path/to/portable-home`. The launch argument comes from your existing supported offline installation; this tool neither supplies nor installs that component.

Successful startup logs include:

```json
{"event": "device_redirected", "source": "Randgrid", "target": "NUL"}
{"event": "startup_checkpoint_repaired"}
{"event": "detached", "result": "both startup repairs observed"}
```

Logs are saved in `GAME/.mw4-linux/run-TIMESTAMP/`. A `ready` event alone is not success. Confirm the actual menu. The command waits for the game to exit after the tracer detaches.

For Steam, add a shell wrapper containing this **complete launch command**, not the prepared EXE. Do not select another Proton compatibility tool for the Linux wrapper. Steam/controller integration for this new helper is not yet validated; the previously working shortcut was deliberately left unchanged.

## Restore

Close the test game, then:

```bash
python3 mw4.py restore --game /path/to/test-game
```

Restore checks all backups and destinations before writing. If another tool changed an installed file, it refuses to overwrite it. Files absent before installation are removed; existing files are restored exactly. Backups and the receipt remain for inspection. To repeat installation after restoring, use a new test copy or archive the restored `.mw4-linux` directory first.

Never launch a prepared DLL without the helper: its short jump intentionally waits for attachment. A failed trace terminates the test process rather than leaving a partial repair running. Use only a dedicated test copy and prefix while this remains alpha.

## How it works

1. Full-file SHA-256 checks pin the executable and Rex DLL to a known layout.
2. At Rex file offset `0x43db`, a five-byte call becomes `jmp self` plus padding. Its loaded RVA is `0x4fdb`.
3. After the image maps, the tracer uses `PTRACE_SEIZE` and `PTRACE_INTERRUPT` to stop its threads. It checks and applies ten game-image edits, arms two **game call-site** breakpoints, then releases the Rex gate.
4. At game RVA `0x0b58c7c6`, it reads the caller's `OBJECT_ATTRIBUTES` and `UNICODE_STRING`. Only an exact UTF-16 `\??\Randgrid` match is changed to `\??\NUL`. The handler reconstructs the call registers and points RAX at the loaded `ntdll!NtCreateFile` export. It does **not** breakpoint the export itself.
5. At RVA `0x0b5a7163`, it verifies the patched bytes, clears ZF and sets two build-specific startup flags.
6. Once both repairs occurred, it restores breakpoint bytes, detaches every traced thread and lets the game continue normally.

Opening NUL is not a Randgrid driver implementation. The surrounding branch/return-value edits are part of the same modified startup path. The original source-level names of all ten checks have not been recovered. This does not make Windows kernel anti-cheat work on Linux.

See [validation](../research/validation.md), [mechanism and provenance](../research/mechanism.md), and the source. The tracer still has experimental multithread/signal edge cases; particularly, other threads can run during breakpoint single-stepping. Do not generalize it to unrelated processes.

## Tests

On Linux x86-64:

```bash
python3 -m unittest discover -s tests
gcc -O0 -Wall -Wextra -o tests/trace_fixture tests/trace_fixture.c
python3 tests/test_trace.py
```

The fixture traces only its own tiny child. Installer tests use synthetic byte strings and temporary directories, not game files. `research/decode_reference.py` is a read-only decoder for the exact reference helper hash; it never executes that binary.

## Credits

Based on the community `codpatch` startup repair, implemented here in Python. [Technical provenance and reference fingerprints](../research/mechanism.md).

Built around [UMU](https://github.com/Open-Wine-Components/umu-launcher), [Proton](https://github.com/ValveSoftware/Proton) and [VKD3D-Proton](https://github.com/HansKristian-Work/vkd3d-proton). The separate [mac-fixer project](https://github.com/mac-fixer/cod-mw4-fix) informed the platform comparison; no code from that project is included.

This repository distributes patcher source and documentation, not game files or dependency binaries.
