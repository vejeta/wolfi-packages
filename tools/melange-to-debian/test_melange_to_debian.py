# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Tests for melange-to-debian: python3 -m unittest discover -s tools/melange-to-debian"""

import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("m2d", os.path.join(HERE, "melange-to-debian.py"))
m2d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2d)

RECIPE = """
package:
  name: libfoo
  version: '1.2.3'
  epoch: 0
  description: Library for foo
  copyright:
    - license: LGPL-2.1-or-later
    - license: MIT
      paths:
        - data/*
  dependencies:
    runtime:
      - libfoo-data=${{package.full-version}}
environment:
  contents:
    packages:
      - build-base
      - busybox
      - meson
      - glib-dev
      - pkgconf-dev
      - frobnicate-dev
pipeline:
  - uses: fetch
    with:
      uri: https://example.org/releases/foo-${{package.version}}.tar.xz
      expected-sha512: 00
  - name: Remove non-free files
    runs: |
      rm -rf data/blob.bin
  - uses: patch
    with:
      patches: libfoo/fix-build.patch
  - uses: meson/configure
    with:
      opts: -Dtests=false -Ddocs=false
  - uses: meson/compile
  - uses: meson/install
  - runs: |
      install -Dm644 libfoo/foo.conf ${{targets.destdir}}/etc/foo.conf
  - uses: strip
subpackages:
  - name: libfoo-dev
    pipeline:
      - uses: split/dev
  - name: libfoo-data
    pipeline:
      - runs: |
          mkdir -p ${{targets.contextdir}}/usr/share
          mv ${{targets.destdir}}/usr/share/foo ${{targets.contextdir}}/usr/share/
  - name: libfoo-lang
    pipeline:
      - uses: split/locales
test:
  environment:
    contents:
      packages:
        - foo-tools
  pipeline:
    - name: Version
      runs: |
        foo-tool --version
    - uses: test/tw/ldd-check
"""


class ConvertTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        recipe_path = os.path.join(cls.tmp.name, "libfoo.yaml")
        with open(recipe_path, "w") as fh:
            fh.write(RECIPE)
        os.makedirs(os.path.join(cls.tmp.name, "libfoo"))
        for name, text in (("fix-build.patch", "--- a\n+++ b\n"), ("foo.conf", "x=1\n")):
            with open(os.path.join(cls.tmp.name, "libfoo", name), "w") as fh:
                fh.write(text)
        recipe = m2d.yaml.safe_load(RECIPE)
        cls.conv = m2d.Converter(recipe, recipe_path, "Jane Doe <jane@example.org>")
        cls.files, cls.copies = cls.conv.convert()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_control_build_depends(self):
        control = self.files["control"]
        self.assertIn(" debhelper-compat (= 13),", control)
        self.assertIn(" libglib2.0-dev,", control)
        self.assertIn(" pkgconf,", control)
        self.assertIn(" meson,", control)
        self.assertNotIn("build-base", control)
        self.assertNotIn("busybox", control)

    def test_name_guess_is_reported(self):
        self.assertIn(" libfrobnicate-dev", self.files["control"])
        self.assertTrue(any("frobnicate-dev" in n for n in self.conv.notes))

    def test_binary_packages(self):
        control = self.files["control"]
        self.assertIn("Package: libfoo-dev\nSection: libdevel", control)
        self.assertIn("Depends: libfoo (= ${binary:Version}), ${misc:Depends}", control)
        self.assertIn("libfoo-data (= ${binary:Version})", control)
        self.assertNotIn("Package: libfoo-lang", control)

    def test_rules_meson_options(self):
        rules = self.files["rules"]
        self.assertIn("\tdh $@ --buildsystem=meson", rules)
        self.assertIn("\t\t-Dtests=false \\\n\t\t-Ddocs=false", rules)

    def test_rules_install_step_uses_debian_files(self):
        rules = self.files["rules"]
        self.assertIn("install -Dm644 debian/foo.conf $(DESTDIR)/etc/foo.conf", rules)
        self.assertEqual(self.copies["foo.conf"], os.path.join(self.tmp.name, "libfoo", "foo.conf"))

    def test_files_excluded(self):
        self.assertIn("Files-Excluded:\n  data/blob.bin", self.files["copyright"])
        self.assertNotIn("blob.bin", self.files["rules"])

    def test_copyright(self):
        c = self.files["copyright"]
        self.assertIn("Files: *\n", c)
        self.assertIn("License: LGPL-2.1+\n On Debian systems", c)
        self.assertIn("Files: data/*\n", c)
        self.assertIn("License: Expat\n Permission is hereby granted", c)

    def test_watch_from_tarball_url(self):
        self.assertEqual(self.files["watch"],
                         "version=4\nhttps://example.org/releases/ foo\\-@ANY_VERSION@@ARCHIVE_EXT@\n")

    def test_patches(self):
        self.assertEqual(self.files["patches/series"], "fix-build.patch\n")
        self.assertIn("patches/fix-build.patch", self.copies)

    def test_install_files(self):
        self.assertIn("usr/include", self.files["libfoo-dev.install"])
        self.assertIn("usr/share/foo", self.files["libfoo-data.install"])

    def test_autopkgtest(self):
        self.assertIn("Tests: version\nDepends: @, foo-tools", self.files["tests/control"])
        self.assertIn("foo-tool --version", self.files["tests/version"])

    def test_changelog(self):
        first = self.files["changelog"].splitlines()[0]
        self.assertEqual(first, "libfoo (1.2.3-1) UNRELEASED; urgency=medium")


class NameTest(unittest.TestCase):
    def test_names(self):
        self.assertEqual(m2d.debian_name("ninja"), ("ninja-build", "table"))
        self.assertEqual(m2d.debian_name("py3-requests"), ("python3-requests", "rule"))
        self.assertEqual(m2d.debian_name("perl-yaml"), ("libyaml-perl", "rule"))
        self.assertEqual(m2d.debian_name("openjdk-21"), ("openjdk-21-jdk", "table"))
        self.assertEqual(m2d.debian_name("build-base"), (None, "dropped"))

    def test_licenses(self):
        self.assertEqual(m2d.to_debian_license("GPL-2.0-or-later AND MIT"), "GPL-2+ and Expat")
        self.assertEqual(m2d.to_debian_license("LGPL-3.0-only OR GPL-3.0-only"), "LGPL-3 or GPL-3")


class RepositoryRecipesTest(unittest.TestCase):
    """Every recipe in packages/ converts without errors."""

    def test_all_recipes(self):
        pkgdir = os.path.join(HERE, "..", "..", "packages")
        for fn in sorted(os.listdir(pkgdir)):
            if not fn.endswith(".yaml"):
                continue
            path = os.path.join(pkgdir, fn)
            with self.subTest(recipe=fn):
                with open(path) as fh:
                    recipe = m2d.yaml.safe_load(fh)
                files, _ = m2d.Converter(recipe, path, "A <a@b>").convert()
                self.assertTrue(files["control"].startswith("Source: "))
                self.assertTrue(files["rules"].startswith("#!/usr/bin/make -f"))


if __name__ == "__main__":
    unittest.main()
