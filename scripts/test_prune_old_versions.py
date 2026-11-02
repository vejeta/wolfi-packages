# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Tests for prune-old-versions.py: python3 -m unittest discover -s scripts"""

import gzip
import importlib.util
import io
import os
import tarfile
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("prune_old_versions", os.path.join(HERE, "prune-old-versions.py"))
po = importlib.util.module_from_spec(spec)
spec.loader.exec_module(po)


def apk(path, pkgname, pkgver):
    """A minimal .apk: a gzipped tar stream whose first member is .PKGINFO."""
    data = "pkgname = {}\npkgver = {}\n".format(pkgname, pkgver).encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(".PKGINFO")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    with open(path, "wb") as fh:
        fh.write(gzip.compress(buf.getvalue()))


class VersionKeyTest(unittest.TestCase):
    def test_order(self):
        ordered = ["1.0_rc1-r0", "1.0-r0", "1.0-r1", "1.0_p1-r0", "1.9-r0", "1.10-r0", "2.13_beta171-r0", "2.13-r0"]
        self.assertEqual(sorted(ordered, key=po.version_key), ordered)

    def test_git_snapshot_after_release(self):
        self.assertLess(po.version_key("0-r0"), po.version_key("0_git20170330-r0"))


class PruneTest(unittest.TestCase):
    def test_keeps_the_newest(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ver in ("1.9-r0", "1.10-r0", "1.10-r1", "1.8-r0"):
                apk(os.path.join(tmp, "foo-{}.apk".format(ver)), "foo", ver)
            # a package whose name looks like a version of another
            apk(os.path.join(tmp, "foo-doc-1.8-r0.apk"), "foo-doc", "1.8-r0")
            po.main(["--keep", "2", tmp])
            self.assertEqual(sorted(os.listdir(tmp)),
                             ["foo-1.10-r0.apk", "foo-1.10-r1.apk", "foo-doc-1.8-r0.apk"])

    def test_dry_run_deletes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            for ver in ("1-r0", "2-r0"):
                apk(os.path.join(tmp, "bar-{}.apk".format(ver)), "bar", ver)
            po.main(["--keep", "1", "--dry-run", tmp])
            self.assertEqual(len(os.listdir(tmp)), 2)


if __name__ == "__main__":
    unittest.main()
