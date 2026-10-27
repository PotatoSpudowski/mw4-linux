import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import mw4

class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'game'
        (self.root / 'sp26').mkdir(parents=True)
        self.graphics = Path(self.temp.name) / 'graphics'
        self.graphics.mkdir()
        self.exe = b'fixture exe'
        self.rex = b'header' + b'original' + b'tail'
        self.prepared = self.rex[:6] + b'12345' + self.rex[11:]
        (self.root / 'sp26/sp26-cod.exe').write_bytes(self.exe)
        (self.root / 'sp26/rex_sp.dll').write_bytes(self.rex)
        (self.graphics / 'd3d12.dll').write_bytes(b'graphics')
        self.patch = patch.multiple(mw4.build, EXE_SHA256=mw4.digest(self.exe),
            REX_ORIGINAL_SHA256=mw4.digest(self.rex), REX_PREPARED_SHA256=mw4.digest(self.prepared),
            GATE_FILE_OFFSET=6, GATE_PREPARED=b'12345', GRAPHICS={'d3d12.dll':mw4.digest(b'graphics')})
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_install_and_restore_preserves_existing_files(self):
        (self.root / 'sp26/d3d12.dll').write_bytes(b'previous')
        mw4.install(self.root, self.graphics)
        self.assertEqual(mw4.validate(self.root), 'prepared')
        mw4.restore(self.root)
        self.assertEqual((self.root / 'sp26/rex_sp.dll').read_bytes(), self.rex)
        self.assertEqual((self.root / 'sp26/d3d12.dll').read_bytes(), b'previous')

    def test_absent_file_removed_on_restore(self):
        mw4.install(self.root, self.graphics)
        mw4.restore(self.root)
        self.assertFalse((self.root / 'sp26/d3d12.dll').exists())

    def test_unknown_build_has_no_side_effects(self):
        (self.root / 'sp26/sp26-cod.exe').write_bytes(b'other build')
        with self.assertRaises(RuntimeError): mw4.install(self.root, self.graphics)
        self.assertFalse((self.root / '.mw4-linux').exists())
        self.assertEqual((self.root / 'sp26/rex_sp.dll').read_bytes(), self.rex)

    def test_bad_graphics_has_no_side_effects(self):
        (self.graphics / 'd3d12.dll').write_bytes(b'wrong')
        with self.assertRaises(RuntimeError): mw4.install(self.root, self.graphics)
        self.assertFalse((self.root / '.mw4-linux').exists())

    def test_changed_destination_prevents_entire_restore(self):
        mw4.install(self.root, self.graphics)
        (self.root / 'sp26/d3d12.dll').write_bytes(b'user modification')
        with self.assertRaises(RuntimeError): mw4.restore(self.root)
        self.assertEqual((self.root / 'sp26/rex_sp.dll').read_bytes(), self.prepared)

    def test_damaged_backup_prevents_entire_restore(self):
        mw4.install(self.root, self.graphics)
        (self.root / '.mw4-linux/rex_sp.dll.backup').write_bytes(b'broken')
        with self.assertRaises(RuntimeError): mw4.restore(self.root)
        self.assertEqual((self.root / 'sp26/rex_sp.dll').read_bytes(), self.prepared)

if __name__ == '__main__': unittest.main()
