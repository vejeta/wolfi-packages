# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Tests for remove-retired.py: python3 -m unittest discover -s scripts"""

import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("remove_retired", os.path.join(HERE, "remove-retired.py"))
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)


class RetiredListTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "RETIRED")
        with open(path, "w") as fh:
            fh.write("# comment\nzlib\nstremio>=4\nold<2.0  # note\n"
                     "qt5-qtwebengine aarch64\nboth>=1 aarch64 riscv64\n")
        self.retired = rr.read_list(path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_whole_origin(self):
        self.assertTrue(rr.is_retired(self.retired, "zlib", "1.3-r0", "x86_64"))
        self.assertFalse(rr.is_retired(self.retired, "mpv", "0.40.0-r0", "x86_64"))

    def test_version_range(self):
        self.assertTrue(rr.is_retired(self.retired, "stremio", "4.4.169-r1", "x86_64"))
        self.assertFalse(rr.is_retired(self.retired, "stremio", "1.2.0-r0", "x86_64"))
        self.assertTrue(rr.is_retired(self.retired, "old", "1.9-r3", "aarch64"))
        self.assertFalse(rr.is_retired(self.retired, "old", "2.0-r0", "aarch64"))

    def test_architecture(self):
        self.assertTrue(rr.is_retired(self.retired, "qt5-qtwebengine", "5.15.17-r0", "aarch64"))
        self.assertFalse(rr.is_retired(self.retired, "qt5-qtwebengine", "5.15.17-r1", "x86_64"))
        self.assertTrue(rr.is_retired(self.retired, "both", "1.1-r0", "riscv64"))
        self.assertFalse(rr.is_retired(self.retired, "both", "0.9-r0", "aarch64"))
        self.assertFalse(rr.is_retired(self.retired, "both", "1.1-r0", "x86_64"))

    def test_repository_list(self):
        retired = rr.read_list(os.path.join(HERE, "..", "packages", "RETIRED"))
        self.assertEqual(retired["stremio-qt5"], (None, {"aarch64"}))


if __name__ == "__main__":
    unittest.main()
