# Validation — 2026-10-27

Environment: Bazzite Linux x86-64, RX 7900 XTX, i5-12400F; UMU 1.4.4, GE-Proton11-9. Original working game and Steam shortcut preserved.

## Test input

A Btrfs reflink copy of the already working community offline campaign package. In the copy only, restored the five known Rex bytes in memory before writing the DLL, removed the two graphics overrides, and moved the reference binary helper outside the test tree. Kept a cloned working Wine prefix, caches and saves.

This is a reconstructed unprepared offline build. It is **not** an independently obtained clean retail installation, a fresh prefix test or a proof of complete game-file integrity.

## Results

- Nine unit/regression tests passed: exact device-frame handling, nonmatching-device refusal, buffer-capacity refusal, install/restore, unknown executable rejection, unknown graphics rejection, changed-file protection and damaged-backup protection.
- Live ptrace fixture passed: seize, interrupt, process-memory write, software breakpoint, instruction-pointer rewind, detach and normal child exit.
- First game test failed because the initial implementation incorrectly armed the exported NtCreateFile function. Reviewing the reference call sites corrected both the trap location and OBJECT_ATTRIBUTES layout.
- Corrected run reported ten validated patches, exact Randgrid-to-NUL substitution, startup checkpoint repair and successful detach.
- Captured the rendered campaign menu from the isolated game's X window. Reference helper was absent from its expected path. The new helper was the only startup tracer launched.
- Synthetic input did not advance the menu during this test. Gameplay, controller operation, save writes, a full campaign and repeated launches are not certified by this run.

The original setup had separately rendered gameplay and cutscenes; that is not substituted for testing this new implementation.

Successful trace (addresses are run-specific):

```json
{"event":"ready","patches":10,"threads":1,"game":"0x6fffd1a20000","rex":"0x6ffffc090000","export":"0x6fffffeff4a0","checkpoint":"0x6fffdcfc7163"}
{"event":"device_redirected","source":"Randgrid","target":"NUL"}
{"event":"startup_checkpoint_repaired"}
{"event":"detached","result":"both startup repairs observed"}
```

After the menu check, the isolated process was stopped and real-file restore succeeded. Doctor reported the original unprepared Rex fingerprint again. The working installation was not modified.

## Follow-up gameplay confirmation

The author subsequently confirmed playing the patched campaign, beyond the menu. This is a hands-on gameplay report, separate from the isolated tracing test above. Test duration, missions completed, controller coverage and full campaign completion were not specified.

## Outstanding release gates

- Repeated launches, longer gameplay sessions and full campaign completion.
- Fresh prefix provisioning and Steam/controller focus integration.
- Thread-race and signal-handling stress tests on synthetic fixtures.
- Reproducible source build/provenance for the tested graphics overrides, then an ablation against stock GE libraries.
- Independently validate other executable builds before adding profiles; never loosen hash checks to force compatibility.
