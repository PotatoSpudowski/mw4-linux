"""Linux-only integration test: modify only our own tiny child process."""
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tracer import Tracer, WALL, getregs, setregs

def main():
    executable = Path(__file__).with_name('trace_fixture')
    child = subprocess.Popen([str(executable)], stdout=subprocess.PIPE, text=True)
    tracer = Tracer(child.pid)
    try:
        gate, checkpoint = map(lambda value: int(value, 16), child.stdout.readline().split())
        tracer.attach()
        tracer.arm(checkpoint)
        tracer.memory.write(gate, struct.pack('<I', 0))
        tracer.resume(child.pid)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            tid, status = os.waitpid(child.pid, WALL | os.WNOHANG)
            if tid:
                assert os.WIFSTOPPED(status) and os.WSTOPSIG(status) == signal.SIGTRAP, status
                tracer.stopped.add(tid)
                assert getregs(tid).rip == checkpoint + 1
                tracer.detach()
                assert child.communicate(timeout=5)[0].strip() == 'completed'
                assert child.returncode == 0
                print('PASS: seize, interrupt, memory write, INT3, RIP rewind, detach and normal child exit')
                return
            time.sleep(.01)
        raise RuntimeError('fixture timeout')
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
        if tracer.memory:
            tracer.memory.close()
if __name__ == '__main__':
    main()
