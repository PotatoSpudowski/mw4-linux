# Mechanism and provenance

Reference ELF SHA-256: `cd2bec4f40cbdf8aacdbc7917634d3600eca64b82018baea49aacf06c52ce915`.
Build ID: `c1f17202e2c6fd454dbe9d35bcf74c43c860ee4d`.
Inspected locally from the previously installed community launcher. Original repair authorship belongs to that community; precise authorship has not been independently established. No reference executable or proprietary game data is redistributed.

The standalone read-only decoder reproduces the embedded CPW1 record stream: version 1, 557 bytes, 32 typed records. It checks the input binary's full hash before decoding. The record table supplies ten game-image edits, two Rex gate edits, UTF-16 device names and frame/RVA constants.

Reference disassembly evidence (addresses belong only to the above ELF):

- `0x43b64e`: ptrace wrapper; syscall 101 at `0x43b6a9`.
- `0x405490`: save original byte / write INT3.
- `0x4049d0`: process-memory write with ptrace fallback.
- `0x405678–0x4056a4`: derive second trap from game base plus field 7.
- `0x405bdf–0x405c00`: arm field-5 game call site and field-7 checkpoint. Neither is the NtCreateFile export.
- `0x405e9e–0x405f43`: read pointer at `RBP + OBJECT_SLOT + 16`; this is the ObjectName member of OBJECT_ATTRIBUTES.
- `0x4061e2–0x406218`: exact UTF-16 source name match.
- `0x40621e–0x4062b7`: capacity check, replacement length and name writes.
- `0x4062bd–0x406323`: reconstruct Windows x64 arguments, RAX pointing at resolved NtCreateFile.
- `0x405f7d–0x4060d2`: checkpoint patch verification, clear ZF, set two flag bytes.
- `0x4039c0`: reference thread stopping / detach / resume cleanup.

The Python tracer uses SEIZE/INTERRUPT rather than copying the reference's ATTACH/SIGSTOP implementation. No source from the macOS project was copied.

## Authoritative interface references

- [Linux ptrace manual](https://man7.org/linux/man-pages/man2/ptrace.2.html)
- [Linux x86 ptrace ABI](https://github.com/torvalds/linux/blob/master/arch/x86/include/uapi/asm/ptrace-abi.h)
- [Microsoft OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes)
- [Microsoft UNICODE_STRING](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_unicode_string)
- [UMU](https://github.com/Open-Wine-Components/umu-launcher)
- [VKD3D-Proton](https://github.com/HansKristian-Work/vkd3d-proton)
- [Separate macOS research revision](https://github.com/mac-fixer/cod-mw4-fix/tree/d9a1a63feacdb765524db1f5ce1f76de03a406ba)
