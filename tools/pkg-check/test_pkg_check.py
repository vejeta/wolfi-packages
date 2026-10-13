#!/usr/bin/env python3
"""Offline tests for pkg-check.

    python3 -m unittest discover -s tools/pkg-check -v
"""

import importlib.util
import io
import os
import tarfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("pkg_check", os.path.join(HERE, "pkg-check.py"))
pc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pc)


def apkindex(text):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = text.encode()
        info = tarfile.TarInfo("APKINDEX")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class VersionTest(unittest.TestCase):

    def test_compare(self):
        self.assertEqual(pc.compare_versions("1.0", "1.0"), 0)
        self.assertEqual(pc.compare_versions("1.0", "1.0.1"), -1)
        self.assertEqual(pc.compare_versions("0.17.10", "0.17.4"), 1)
        self.assertEqual(pc.compare_versions("1.0rc1", "1.0"), -1)
        self.assertEqual(pc.compare_versions("2025.4", "2025.10"), -1)

    def test_upstream_version(self):
        self.assertEqual(pc.upstream_version("1:0.17.3-1+deb13u1", "debian"), "0.17.3")
        self.assertEqual(pc.upstream_version("1.2+dfsg-1", "debian"), "1.2")
        self.assertEqual(pc.upstream_version("0.17.5-r0", "alpine"), "0.17.5")


class ApkindexTest(unittest.TestCase):

    def test_parse_and_lookup(self):
        blob = apkindex("P:libass\nV:0.17.5-r0\no:libass\n\nP:libass-dev\nV:0.17.5-r0\no:libass\n\n"
                        "P:py3-foo\nV:1.0-r1\no:foo\n\n")
        entries = list(pc.parse_apkindex(blob))
        self.assertEqual([e["P"] for e in entries], ["libass", "libass-dev", "py3-foo"])

        pc.fetch = lambda url, cache=True: blob
        res = pc.lookup_apkindex("wolfi", "libass", [("os", "x")], False)
        self.assertTrue(res.found)
        self.assertEqual(res.version, "0.17.5-r0")
        self.assertIn("subpackages: libass-dev", res.extra)

        res = pc.lookup_apkindex("wolfi", "foo", [("os", "x")], False)
        self.assertTrue(res.found)
        self.assertIn("only as subpackage(s) of origin 'foo'", res.extra)

        self.assertFalse(pc.lookup_apkindex("wolfi", "nope", [("os", "x")], False).found)

    def test_report_exit_codes(self):
        with io.StringIO() as out:
            import contextlib
            with contextlib.redirect_stdout(out):
                self.assertEqual(pc.report("x", pc.Result("wolfi", False), None, False), pc.EXIT_ABSENT)
                self.assertEqual(pc.report("x", pc.Result("wolfi", True, "1.0-r0", "os"), "1.0", False), pc.EXIT_PRESENT)
                self.assertEqual(pc.report("x", pc.Result("wolfi", True, "0.9-r0", "os"), "1.0", False), pc.EXIT_OLDER)
                self.assertEqual(pc.report("x", pc.Result("wolfi", False, error="boom"), None, False), pc.EXIT_ERROR)


if __name__ == "__main__":
    unittest.main()
