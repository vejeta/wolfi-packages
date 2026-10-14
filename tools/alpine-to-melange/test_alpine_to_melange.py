#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Tests for alpine-to-melange.

    python3 -m unittest discover -s tools/alpine-to-melange -v

Snapshot tests convert every testdata/<case>/aport/ and compare the result
with testdata/<case>/expected/. Regenerate after an intended change with:

    UPDATE_SNAPSHOTS=1 python3 -m unittest discover -s tools/alpine-to-melange
"""

import filecmp
import importlib.util
import io
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
TESTDATA = os.path.join(HERE, "testdata")

spec = importlib.util.spec_from_file_location("a2m", os.path.join(HERE, "alpine-to-melange.py"))
a2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2m)

# Wolfi runs build steps with busybox ash; dash lacks ${var/x/y}.
SHELL = ["busybox", "sh"] if shutil.which("busybox") else ["bash", "--posix"]

try:
    import yaml
except ImportError:
    yaml = None


def cases():
    for name in sorted(os.listdir(TESTDATA)):
        if os.path.isdir(os.path.join(TESTDATA, name, "aport")):
            yield name


def convert(name, out):
    with redirect_stderr(io.StringIO()):
        return a2m.main(["--apkbuild-dir", os.path.join(TESTDATA, name, "aport"), "--out", out])


def recipe_text(name):
    out = tempfile.mkdtemp()
    try:
        convert(name, out)
        with open(os.path.join(out, name + ".yaml")) as fh:
            return fh.read()
    finally:
        shutil.rmtree(out)


class SnapshotTest(unittest.TestCase):

    def test_snapshots(self):
        for name in cases():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as out:
                self.assertEqual(convert(name, out), 0)
                expected = os.path.join(TESTDATA, name, "expected")
                if os.environ.get("UPDATE_SNAPSHOTS"):
                    shutil.rmtree(expected, ignore_errors=True)
                    shutil.copytree(out, expected)
                    continue
                self.assertFalse(self._diff(filecmp.dircmp(out, expected)),
                                 "output differs from {}".format(expected))

    def _diff(self, cmp):
        bad = cmp.left_only + cmp.right_only + cmp.diff_files + cmp.funny_files
        for sub in cmp.subdirs.values():
            bad += self._diff(sub)
        return bad

    @unittest.skipIf(yaml is None, "PyYAML not installed")
    def test_output_is_valid_yaml_and_shell(self):
        for name in cases():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as out:
                convert(name, out)
                with open(os.path.join(out, name + ".yaml")) as fh:
                    data = yaml.safe_load(fh)
                scripts = []
                for pkg in [data] + data.get("subpackages", []):
                    scripts += [st["runs"] for st in pkg.get("pipeline", []) if "runs" in st]
                for pkg in [data["package"]] + data.get("subpackages", []):
                    scripts += list((pkg.get("scriptlets") or {}).values())
                for script in scripts:
                    script = re.sub(r"\$\{\{[^}]+\}\}", "X", script)
                    res = subprocess.run(SHELL + ["-n"], input=script, text=True, capture_output=True)
                    self.assertEqual(res.returncode, 0, res.stderr + script)


class RealAportsTest(unittest.TestCase):
    """Properties of the converted real-world aports."""

    def test_sha512_and_version_templating(self):
        text = recipe_text("libass")
        self.assertIn("uri: https://github.com/libass/libass/releases/download/"
                      "${{package.version}}/libass-${{package.version}}.tar.xz", text)
        self.assertIn("expected-sha512: b9e06023e9f5", text)

    def test_depends_dev_goes_to_dev_subpackage(self):
        text = recipe_text("libass")
        dev = text.split("- name: libass-dev", 1)[1]
        self.assertIn("harfbuzz-dev", dev)
        self.assertIn("uses: split/dev", dev)

    def test_helper_variables_are_carried(self):
        text = recipe_text("mujs")
        self.assertIn("_sover=${pkgver#1.}\n", text)
        self.assertIn("_sover=${_sover%%.*}\n", text)
        self.assertNotIn("local ver3", text)

    def test_secondary_source_goes_to_srcdir(self):
        text = recipe_text("zimg")
        self.assertIn("directory: _srcdir", text)
        self.assertIn("strip-components: 0", text)
        self.assertNotIn("default_prepare", text)

    def test_abuild_meson_helper(self):
        text = recipe_text("rubberband")
        self.assertIn("abuild_meson() {", text)
        self.assertNotIn("abuild-meson", text)

    def test_local_patch(self):
        text = recipe_text("libplacebo")
        self.assertIn("patches: libplacebo/glslang-deps.patch", text)

    def test_synthetic_features(self):
        text = recipe_text("foobar")
        self.assertIn("match: _rc", text)
        self.assertIn("v${{vars.mangled-pkgver}}.tar.gz", text)
        self.assertIn("- name: foobar-tools", text)
        self.assertNotIn("foobar-openrc", text.split("package:", 1)[1])
        self.assertNotIn("musl-dev", text.split("package:", 1)[1])
        self.assertIn("ninja  # Alpine: samurai", text)
        self.assertIn("pre-install: |", text)
        self.assertIn("- aarch64", text)
        self.assertNotIn("ppc64le", text.split("package:", 1)[1])


class ExpansionTest(unittest.TestCase):
    """The static expander must agree with a real shell."""

    EXPRS = [
        "${pkgver}", "${pkgver%.*}", "${pkgver%%.*}", "${pkgver#*.}", "${pkgver##*.}",
        "${pkgver/_rc/-rc}", "${pkgver//./_}", "${pkgver#1.}", "${pkgver%%[^0-9]*}",
        "$pkgname-$pkgver", "${pkgname}-v${pkgver/_/-}",
    ]

    def test_against_sh(self):
        for ver in ("1.3.9", "2.1.0_rc3", "7.360.1", "10.2.2.0.2"):
            apk = a2m.ApkBuild('pkgname=foo\npkgver={}\n'.format(ver))
            for expr in self.EXPRS:
                with self.subTest(ver=ver, expr=expr):
                    real = subprocess.run(SHELL + ["-c", 'pkgname=foo; pkgver={}; printf %s "{}"'.format(ver, expr)],
                                          capture_output=True, text=True).stdout
                    self.assertEqual(apk.expand(expr), real)

    def test_var_transform_matches_shell(self):
        for raw in ("${pkgver/_rc/-rc}", "${pkgver%.*}", "${pkgver%%.*}", "${pkgver#*.}", "${pkgver##*.}"):
            t = a2m.var_transform("_x", raw)
            for ver in ("2.1.0_rc3", "7.360.1"):
                with self.subTest(raw=raw, ver=ver):
                    real = subprocess.run(SHELL + ["-c", 'pkgver={}; printf %s "{}"'.format(ver, raw)],
                                          capture_output=True, text=True).stdout
                    got = re.sub(t["match"], t["replace"].replace("${1}", r"\1").replace("$$", "$"), ver)
                    self.assertEqual(got, real)

    def test_multiline_and_multiple_assignments(self):
        apk = a2m.ApkBuild('pkgver=1.3.9\n_a=${pkgver#1.}; _a=${_a%%.*}\nmakedepends="\n\tfoo\n\tbar\n\t"\n')
        self.assertEqual(apk.get("_a"), "3")
        self.assertEqual(apk.words("makedepends"), ["foo", "bar"])

    def test_functions_and_skipped_blocks(self):
        apk = a2m.ApkBuild('pkgname=x\ncase "$CARCH" in\nx86) options="!check" ;;\nesac\n'
                           'build() {\n\tmake\n\tif true; then\n\t\techo {}\n\tfi\n}\n\npackage() {\n\tmake install\n}\n')
        self.assertEqual(sorted(apk.functions), ["build", "package"])
        self.assertIn("\tmake", apk.functions["build"])
        self.assertEqual(len(apk.skipped), 1)


if __name__ == "__main__":
    unittest.main()
