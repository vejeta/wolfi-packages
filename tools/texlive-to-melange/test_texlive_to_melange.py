# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Tests for texlive-to-melange."""

import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("t2m", os.path.join(HERE, "texlive-to-melange.py"))
t2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t2m)

TLPDB = """\
name collection-basic
category Collection
shortdesc Essential programs and files
depend amsfonts

name collection-latex
category Collection
shortdesc LaTeX fundamental packages
depend collection-basic
depend latex

name collection-langgerman
category Collection
shortdesc German
depend collection-basic
depend hyphen-german

name latex
category Package
runfiles size=1
 texmf-dist/tex/latex/base/latex.ltx
docfiles size=1
 texmf-dist/doc/latex/base/README.md

name collection-wintools
category Collection
shortdesc Windows-only support programs
"""


class TexliveTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tlpdb = os.path.join(self.tmp.name, "texlive.tlpdb")
        with open(self.tlpdb, "w") as fh:
            fh.write(TLPDB)

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse_tlpdb(self):
        db = t2m.parse_tlpdb(self.tlpdb)
        self.assertEqual(db["collection-latex"]["depend"], ["collection-basic", "latex"])
        self.assertEqual(db["latex"]["run"], ["texmf-dist/tex/latex/base/latex.ltx"])
        self.assertEqual(db["latex"]["doc"], ["texmf-dist/doc/latex/base/README.md"])

    def test_recipe(self):
        out = os.path.join(self.tmp.name, "texmf-dist.yaml")
        import sys
        argv = sys.argv
        sys.argv = ["texlive-to-melange", "--release", "20260301", "--tlpdb", self.tlpdb,
                    "--texmf-sha512", "a" * 128, "--extra-sha512", "b" * 128, "--out", out]
        try:
            t2m.main()
        finally:
            sys.argv = argv
        with open(out) as fh:
            text = fh.read()
        self.assertIn("  - name: texmf-dist-latex\n", text)
        self.assertIn("  - name: texmf-dist-latex-doc\n", text)
        self.assertNotIn("texmf-dist-wintools", text)  # Windows only
        # language collections bring their hyphenation files
        self.assertIn("10-langgerman.$ext", text)
        # every collection needs the basic one
        self.assertIn("      runtime:\n        - texmf-dist\n", text)
        try:
            import yaml
        except ImportError:
            return
        data = yaml.safe_load(text.replace("${{", "x").replace("}}", "x"))
        self.assertEqual(data["package"]["name"], "texmf-dist")


if __name__ == "__main__":
    unittest.main()
