"""Observed binary interface for the one supported offline campaign build.
Derived from static analysis, not copied from the reference helper's source.
Offsets are RVAs unless explicitly named file_offset. Never apply to other builds.
"""
EXE_SHA256 = '69bca6d6e9dd874d0e9b194a300f1ddf9ffc264b1081f78e0e4e7d7ff4c0408e'
REX_PREPARED_SHA256 = '335bab4e3d41353c777d8757b112e1d8778f1d0ebafeae7997e98e75173fcbc7'
# Unprepared hash is filled from a read-only reversal of the verified 5-byte edit.
REX_ORIGINAL_SHA256 = '3f745a446fd1242f0303c2220acc931136acdef1200090eb783a09dec1457a29'
GRAPHICS = {
    'd3d12.dll': '633de512245b2b93728a283751f27bb44d199659830ec6fd9c78053f1feda2fe',
    'd3d12core.dll': '3822f59b19f18458762a7f680ce4395bb4bd98b6e873bd645d0c83ee20d3cb24',
}
GATE_FILE_OFFSET = 0x43db
GATE_RVA = 0x4fdb
GATE_ORIGINAL = bytes.fromhex('e830f2ffff')
GATE_PREPARED = bytes.fromhex('ebfe909090')
DEVICE_BREAKPOINT = 0x0b58c7c6
GAME_BREAKPOINT = 0x0b5a7163
FLAGS = (0x0d7ec3f4, 0x0d7d7691)
OBJECT_SLOT = 0x3e0
HANDLE_SLOT = 0x3b0
IO_STATUS_SLOT = 0x380
ACCESS_MASK = 0x12019f
SOURCE_DEVICE = '\\??\\Randgrid'.encode('utf-16-le')
TARGET_DEVICE = '\\??\\NUL'.encode('utf-16-le')
PATCHES = [
    (0x001d4d6b, '2a', '26'),
    (0x001d4d73, '2e', '2a'),
    (0x001e677b, '2a', '26'),
    (0x001e6783, '2e', '2a'),
    (0x0947b16a, 'e8012403f80fb6d0', 'ba01000000909090'),
    (0x09a43eb0, '4883ec288b05', 'b801000000c3'),
    (0x0a47600e, '75', 'eb'),
    (0x0a4a8134, '31d2', 'b201'),
    (0x0b8f447e, '7449', '9090'),
    (0x003524bf, '204e0000', 'ffffff7f'),
]
PATCHES = [(rva, bytes.fromhex(before), bytes.fromhex(after)) for rva, before, after in PATCHES]
