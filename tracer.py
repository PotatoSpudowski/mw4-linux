"""Linux/x86-64 startup interposition. No kernel modules or system configuration changes.
Only used on the child launched by mw4.py after a complete build hash check.
"""
import ctypes as C
import errno
import json
import os
from pathlib import Path
import signal
import struct
import time
import build_profile as build

P_CONT, P_STEP, P_GETREGS, P_SETREGS = 7, 9, 12, 13
P_DETACH, P_OPTIONS, P_EVENTMSG = 17, 0x4200, 0x4201
P_SEIZE, P_INTERRUPT = 0x4206, 0x4207
OPTIONS = 0x8 | 0x40 | 0x100000  # TRACECLONE, TRACEEXIT, EXITKILL while attached
WALL = 0x40000000
libc = C.CDLL(None, use_errno=True)
libc.ptrace.restype = C.c_long
libc.ptrace.argtypes = [C.c_uint, C.c_int, C.c_void_p, C.c_void_p]

class Regs(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in
                'r15 r14 r13 r12 rbp rbx r11 r10 r9 r8 rax rcx rdx rsi rdi orig_rax rip cs eflags rsp ss fs_base gs_base ds es fs gs'.split()]

def ptrace(request, tid, address=0, data=0):
    C.set_errno(0)
    result = libc.ptrace(request, tid, address, data)
    if result == -1 and C.get_errno():
        raise OSError(C.get_errno(), f'ptrace request {request:#x} tid {tid}: {os.strerror(C.get_errno())}')
    return result

def getregs(tid):
    regs = Regs()
    ptrace(P_GETREGS, tid, 0, C.byref(regs))
    return regs

def setregs(tid, regs):
    ptrace(P_SETREGS, tid, 0, C.byref(regs))

class Memory:
    def __init__(self, pid):
        self.fd = os.open(f'/proc/{pid}/mem', os.O_RDWR)
    def read(self, address, length):
        result = os.pread(self.fd, length, address)
        if len(result) != length:
            raise RuntimeError(f'Short process read at {address:#x}')
        return result
    def write(self, address, data):
        if os.pwrite(self.fd, data, address) != len(data):
            raise RuntimeError(f'Short process write at {address:#x}')
    def close(self):
        os.close(self.fd)


def mapped_module(pid, name):
    matches = []
    for line in Path(f'/proc/{pid}/maps').read_text().splitlines():
        fields = line.split(maxsplit=5)
        if len(fields) == 6 and Path(fields[5]).name == name and fields[2] == '00000000':
            matches.append(int(fields[0].split('-')[0], 16))
    if len(matches) != 1:
        raise RuntimeError(f'Expected one mapping for {name}, found {len(matches)}')
    return matches[0]


def pe_export(memory, base, wanted):
    """Resolve an export from the loaded PE image, rejecting forwarded exports."""
    header = memory.read(base, 64)
    if header[:2] != b'MZ':
        raise RuntimeError('Missing MZ header')
    pe = base + struct.unpack_from('<I', header, 60)[0]
    nt = memory.read(pe, 264)
    if nt[:4] != b'PE\0\0' or struct.unpack_from('<H', nt, 24)[0] != 0x20b:
        raise RuntimeError('Expected PE32+ image')
    export_rva, export_size = struct.unpack_from('<II', nt, 24 + 112)
    directory = memory.read(base + export_rva, 40)
    functions, names, funcs_rva, names_rva, ords_rva = struct.unpack_from('<IIIII', directory, 20)
    if not 0 < names <= 100000 or functions > 100000:
        raise RuntimeError('Invalid export table')
    for index in range(names):
        name_rva = struct.unpack('<I', memory.read(base + names_rva + 4 * index, 4))[0]
        if memory.read(base + name_rva, len(wanted) + 1) != wanted.encode() + b'\0':
            continue
        ordinal = struct.unpack('<H', memory.read(base + ords_rva + 2 * index, 2))[0]
        if ordinal >= functions:
            raise RuntimeError('Invalid export ordinal')
        rva = struct.unpack('<I', memory.read(base + funcs_rva + 4 * ordinal, 4))[0]
        if export_rva <= rva < export_rva + export_size:
            raise RuntimeError('Forwarded export is unsupported')
        return base + rva
    raise RuntimeError(f'Missing export {wanted}')


def repair_device(memory, regs, export):
    """Known-build caller frame. Exact name match; no generic file redirection."""
    slot = regs.rbp + build.OBJECT_SLOT
    try:
        name_struct = struct.unpack('<Q', memory.read(slot + 16, 8))[0]
        if not name_struct:
            return False
        raw = memory.read(name_struct, 16)
        length, capacity = struct.unpack_from('<HH', raw)
        buffer = struct.unpack_from('<Q', raw, 8)[0]
        if length != len(build.SOURCE_DEVICE) or capacity < len(build.TARGET_DEVICE) + 2 or not buffer:
            return False
        if memory.read(buffer, length) != build.SOURCE_DEVICE:
            return False
    except (OSError, RuntimeError):
        return False
    memory.write(buffer, build.TARGET_DEVICE + b'\0\0')
    memory.write(name_struct, struct.pack('<H', len(build.TARGET_DEVICE)))
    regs.rax = export
    regs.rcx = regs.rbp + build.HANDLE_SLOT
    regs.rdx = build.ACCESS_MASK
    regs.r8 = slot
    regs.r9 = regs.rbp + build.IO_STATUS_SLOT
    return True


class Tracer:
    def __init__(self, pid, log=print, timeout=180):
        self.pid, self.log, self.timeout = pid, log, timeout
        self.tids = set()
        self.stopped = set()
        self.breakpoints = {}
        self.stepping = {}
        self.memory = None
        self.device_done = self.game_done = False

    def emit(self, event, **fields):
        self.log(json.dumps({'event': event, **fields}), flush=True)

    def wait_stopped(self, targets, deadline):
        while not targets.issubset(self.stopped):
            if time.monotonic() > deadline:
                raise RuntimeError('Timed out stopping traced threads')
            try:
                tid, status = os.waitpid(-1, WALL | os.WNOHANG)
            except ChildProcessError:
                raise RuntimeError('Tracee exited during attach')
            if not tid:
                time.sleep(0.01)
                continue
            if os.WIFSTOPPED(status):
                self.stopped.add(tid)
                self.tids.add(tid)
                if status >> 16 == 3:
                    child = C.c_ulonglong()
                    ptrace(P_EVENTMSG, tid, 0, C.byref(child))
                    self.tids.add(child.value)
                    targets.add(child.value)
            else:
                self.tids.discard(tid)
                targets.discard(tid)

    def attach(self):
        # Seize + interrupt allows a bounded, non-SIGSTOP detach later.
        for entry in Path(f'/proc/{self.pid}/task').iterdir():
            tid = int(entry.name)
            try:
                ptrace(P_SEIZE, tid, 0, OPTIONS)
                self.tids.add(tid)
                ptrace(P_INTERRUPT, tid)
            except OSError as error:
                if error.errno != errno.ESRCH:
                    raise
        if not self.tids:
            raise RuntimeError('No traceable game threads')
        self.wait_stopped(set(self.tids), time.monotonic() + 10)
        self.memory = Memory(self.pid)

    def arm(self, address):
        self.breakpoints[address] = self.memory.read(address, 1)
        if self.breakpoints[address] == b'\xcc':
            raise RuntimeError('Target already contains an unexpected breakpoint')
        self.memory.write(address, b'\xcc')

    def resume(self, tid, sig=0, step=False):
        ptrace(P_STEP if step else P_CONT, tid, 0, sig)
        self.stopped.discard(tid)

    def setup(self):
        self.game = mapped_module(self.pid, 'sp26-cod.exe')
        rex = mapped_module(self.pid, 'rex_sp.dll')
        ntdll = mapped_module(self.pid, 'ntdll.dll')
        self.export = pe_export(self.memory, ntdll, 'NtCreateFile')
        self.game_trap = self.game + build.GAME_BREAKPOINT
        changes = [(self.game + rva, before, after) for rva, before, after in build.PATCHES]
        # Validate the complete write set before the first edit.
        for address, before, after in changes:
            if self.memory.read(address, len(before)) not in (before, after):
                raise RuntimeError(f'Unexpected game instruction at RVA {address - self.game:#x}')
        if self.memory.read(rex + build.GATE_RVA, 5) != build.GATE_PREPARED:
            raise RuntimeError('Rex gate is not in its prepared state')
        for address, before, after in changes:
            self.memory.write(address, after)
        self.device_trap = self.game + build.DEVICE_BREAKPOINT
        self.arm(self.device_trap)
        self.arm(self.game_trap)
        # Release only after our hooks exist, while every attached thread is stopped.
        self.memory.write(rex + build.GATE_RVA, b'\x90\x90')
        self.emit('ready', patches=len(changes), threads=len(self.tids), game=hex(self.game), rex=hex(rex), export=hex(self.export), checkpoint=hex(self.game_trap))

    def detach(self):
        for tid in list(self.tids - self.stopped):
            try:
                ptrace(P_INTERRUPT, tid)
            except OSError as error:
                if error.errno == errno.ESRCH:
                    self.tids.discard(tid)
                elif error.errno != errno.EIO:
                    raise
        self.wait_stopped(set(self.tids), time.monotonic() + 10)
        if self.memory:
            for address, original in self.breakpoints.items():
                self.memory.write(address, original)
            for tid in list(self.tids):
                try:
                    regs = getregs(tid)
                    if regs.rip - 1 in self.breakpoints:
                        regs.rip -= 1
                        setregs(tid, regs)
                except OSError as error:
                    if error.errno != errno.ESRCH:
                        raise
        for tid in list(self.tids):
            try:
                ptrace(P_DETACH, tid)
            except OSError as error:
                if error.errno != errno.ESRCH:
                    raise
        self.tids.clear()
        self.stopped.clear()

    def run(self):
        deadline = time.monotonic() + self.timeout
        try:
            self.attach()
            self.setup()
            for tid in list(self.stopped):
                self.resume(tid)
            while self.tids and not (self.device_done and self.game_done):
                if time.monotonic() > deadline:
                    raise RuntimeError('Startup repair timed out before both milestones')
                tid, status = os.waitpid(-1, WALL | os.WNOHANG)
                if not tid:
                    time.sleep(0.005)
                    continue
                if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                    self.emit('thread_exit', tid=tid, status=status)
                    self.tids.discard(tid)
                    self.stopped.discard(tid)
                    continue
                if not os.WIFSTOPPED(status):
                    continue
                self.tids.add(tid)
                self.stopped.add(tid)
                sig, event = os.WSTOPSIG(status), status >> 16
                if event == 3:
                    child = C.c_ulonglong()
                    ptrace(P_EVENTMSG, tid, 0, C.byref(child))
                    self.tids.add(child.value)
                    self.resume(tid)
                    continue
                if event:
                    self.resume(tid)
                    continue
                if sig != signal.SIGTRAP:
                    if sig != signal.SIGSYS:
                        self.emit('signal_stop', tid=tid, signal=sig)
                    self.resume(tid, sig)
                    continue
                regs = getregs(tid)
                if tid in self.stepping:
                    address = self.stepping.pop(tid)
                    self.memory.write(address, b'\xcc')
                    self.resume(tid)
                    continue
                address = regs.rip - 1
                if address not in self.breakpoints:
                    self.emit('other_trap', tid=tid, rip=hex(regs.rip))
                    self.resume(tid, sig)
                    continue
                self.memory.write(address, self.breakpoints[address])
                regs.rip = address
                if address == self.device_trap:
                    matched = repair_device(self.memory, regs, self.export)
                    if matched:
                        self.device_done = True
                        self.emit('device_redirected', source='Randgrid', target='NUL')
                else:
                    if not all(self.memory.read(self.game + rva, len(after)) == after for rva, _, after in build.PATCHES):
                        raise RuntimeError('Patched image changed before the startup checkpoint')
                    regs.eflags &= ~0x40
                    for rva in build.FLAGS:
                        self.memory.write(self.game + rva, b'\x01')
                    self.game_done = True
                    self.emit('startup_checkpoint_repaired')
                setregs(tid, regs)
                if self.device_done and self.game_done:
                    break
                self.stepping[tid] = address
                self.resume(tid, step=True)
            if not (self.device_done and self.game_done):
                raise RuntimeError('Game exited before both repair milestones')
            self.detach()
            self.emit('detached', result='both startup repairs observed')
        finally:
            # Caller terminates its own child on failure; do not detach a partial repair.
            if self.memory:
                self.memory.close()
