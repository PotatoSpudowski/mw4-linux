"""Test the exact Windows OBJECT_ATTRIBUTES / UNICODE_STRING frame layout."""
from pathlib import Path
import struct
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tracer import Regs, repair_device
import build_profile as build

class FakeMemory:
    def __init__(self): self.data = bytearray(0x10000)
    def read(self, address, length): return bytes(self.data[address:address+length])
    def write(self, address, data): self.data[address:address+len(data)] = data

class DeviceTests(unittest.TestCase):
    def fixture(self, name=build.SOURCE_DEVICE, capacity=100):
        memory, regs = FakeMemory(), Regs()
        regs.rbp = 0x1000
        # ObjectName is the pointer at OBJECT_ATTRIBUTES + 16, not + 8.
        memory.write(regs.rbp + build.OBJECT_SLOT + 16, struct.pack('<Q', 0x2000))
        memory.write(0x2000, struct.pack('<HHIQ', len(name), capacity, 0, 0x3000))
        memory.write(0x3000, name)
        return memory, regs
    def test_exact_match_repairs_name_and_call_arguments(self):
        memory, regs = self.fixture()
        self.assertTrue(repair_device(memory, regs, 0x9999))
        self.assertEqual(memory.read(0x3000, len(build.TARGET_DEVICE)+2), build.TARGET_DEVICE+b'\0\0')
        self.assertEqual(regs.rax, 0x9999)
        self.assertEqual(regs.rcx, regs.rbp+build.HANDLE_SLOT)
        self.assertEqual(regs.r8, regs.rbp+build.OBJECT_SLOT)
        self.assertEqual(regs.r9, regs.rbp+build.IO_STATUS_SLOT)
        self.assertEqual(regs.rdx, build.ACCESS_MASK)
    def test_other_device_is_untouched(self):
        memory, regs = self.fixture('\\??\\Otherdev'.encode('utf-16-le'))
        before = bytes(memory.data)
        self.assertFalse(repair_device(memory, regs, 0x9999))
        self.assertEqual(bytes(memory.data), before)
    def test_small_buffer_is_untouched(self):
        memory, regs = self.fixture(capacity=2)
        before = bytes(memory.data)
        self.assertFalse(repair_device(memory, regs, 0x9999))
        self.assertEqual(bytes(memory.data), before)
if __name__ == '__main__': unittest.main()
