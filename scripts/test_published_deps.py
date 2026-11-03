# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Tests for published-deps.py: python3 -m unittest discover -s scripts"""

import importlib.util
import io
import os
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("published_deps", os.path.join(HERE, "published-deps.py"))
pd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pd)

INDEX = """P:libfoo
V:1.0-r0
p:so:libfoo.so.1=1.0

P:libfoo
V:1.2-r0
p:so:libfoo.so.1=1.2

P:libfoo-dev
V:1.2-r0
D:libfoo=1.2-r0 pc:zlib

P:bar
V:2.0-r1
D:so:libfoo.so.1 glibc
p:cmd:bar=2.0-r1

P:unused
V:9-r0
"""


def write_index(path):
    data = INDEX.encode()
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("APKINDEX")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


class PublishedDepsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.index = os.path.join(self.tmp.name, "APKINDEX.tar.gz")
        write_index(self.index)

    def tearDown(self):
        self.tmp.cleanup()

    def test_closure_by_names_and_provides(self):
        entries = pd.read_index(self.index)
        # bar needs so:libfoo.so.1 (the newest libfoo); Wolfi's glibc and zlib are not listed
        self.assertEqual(pd.needed(entries, ["bar"]), ["bar-2.0-r1.apk", "libfoo-1.2-r0.apk"])
        self.assertEqual(pd.needed(entries, ["libfoo-dev>=1"]), ["libfoo-1.2-r0.apk", "libfoo-dev-1.2-r0.apk"])
        self.assertEqual(pd.needed(entries, ["cmd:bar"]), ["bar-2.0-r1.apk", "libfoo-1.2-r0.apk"])
        self.assertEqual(pd.needed(entries, ["busybox", "build-base"]), [])

    def test_recipe(self):
        recipe = os.path.join(self.tmp.name, "r.yaml")
        with open(recipe, "w") as fh:
            fh.write("package:\n  name: r\nenvironment:\n  contents:\n    packages:\n"
                     "      - busybox\n      - bar  # comment\n")
        self.assertEqual(pd.build_packages(recipe), ["busybox", "bar"])


if __name__ == "__main__":
    unittest.main()
