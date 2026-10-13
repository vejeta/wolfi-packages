#!/usr/bin/env python3
"""Tests for debian-to-melange.

    python3 -m unittest discover -s tools/debian-to-melange -v

Snapshot tests convert every testdata/<case>/debian/ and compare the result
with testdata/<case>/expected/. Regenerate snapshots after an intended
change with:

    UPDATE_SNAPSHOTS=1 python3 -m unittest discover -s tools/debian-to-melange
"""

import filecmp
import importlib.util
import io
import os
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr

HERE = os.path.dirname(os.path.abspath(__file__))
TESTDATA = os.path.join(HERE, "testdata")

spec = importlib.util.spec_from_file_location("d2m", os.path.join(HERE, "debian-to-melange.py"))
d2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d2m)

try:
    import yaml
except ImportError:  # PyYAML is optional; only used to double-check output
    yaml = None


def cases():
    for name in sorted(os.listdir(TESTDATA)):
        if os.path.isdir(os.path.join(TESTDATA, name, "debian")):
            yield name


def case_args(name):
    path = os.path.join(TESTDATA, name, "args")
    if os.path.exists(path):
        with open(path) as fh:
            return fh.read().split()
    return []


def convert(name, out):
    argv = ["--debian-dir", os.path.join(TESTDATA, name, "debian"), "--out", out] + case_args(name)
    with redirect_stderr(io.StringIO()):
        rc = d2m.main(argv)
    return rc


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
                cmp = filecmp.dircmp(out, expected)
                self.assertFalse(self._diff(cmp), "output differs from {}".format(expected))

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
                recipe = next(f for f in os.listdir(out) if f.endswith(".yaml"))
                with open(os.path.join(out, recipe)) as fh:
                    data = yaml.safe_load(fh)
                for key in ("package", "environment", "pipeline", "test"):
                    self.assertIn(key, data)
                for pkg in [data["package"]] + data.get("subpackages", []):
                    for kind, script in (pkg.get("scriptlets") or {}).items():
                        res = subprocess.run(["sh", "-n"], input=script, text=True, capture_output=True)
                        self.assertEqual(res.returncode, 0, "{} {}: {}".format(pkg["name"], kind, res.stderr))


class StremioServerInstallerTest(unittest.TestCase):
    """Behaviour specific to the first real-world case."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        convert("stremio-server-installer", cls.tmp)
        with open(os.path.join(cls.tmp, "stremio-server-installer.yaml")) as fh:
            cls.text = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_version_comes_from_rules_variable(self):
        self.assertIn("version: '4.21.1'", self.text)

    def test_rules_variables_become_melange_references(self):
        self.assertIn('version="${{package.version}}"', self.text)
        self.assertIn('hash="${{vars.server-sha256}}"', self.text)
        self.assertIn("server-sha256: 405eb494d6708406a30e716c3cfb5abae7a5e9c7a8b79446d64c3f821385930f", self.text)

    def test_debconf_is_replaced_by_conffile(self):
        self.assertNotIn("confmodule", self.text.split("package:", 1)[1])
        self.assertNotIn("db_get", self.text)
        self.assertNotIn("db_stop", self.text)
        self.assertIn('RET="${STREMIO_SERVER_INSTALLER_DOWNLOAD:-true}"', self.text)
        conf = os.path.join(self.tmp, "stremio-server-installer", "stremio-server-installer.conf")
        with open(conf) as fh:
            self.assertIn('STREMIO_SERVER_INSTALLER_DOWNLOAD="true"', fh.read())

    def test_debhelper_token_removed(self):
        self.assertNotIn("#DEBHELPER#", self.text)

    def test_scriptlets_emulate_dpkg_arguments(self):
        self.assertIn("debian_postinst configure\n", self.text)
        self.assertIn('debian_postinst configure "$2"', self.text)


class HelperTest(unittest.TestCase):

    def test_parse_relations(self):
        rel = d2m.parse_relations("a (>= 1), b | c [amd64], ${misc:Depends}, d:any <!nocheck>")
        self.assertEqual(rel, [["a"], ["b", "c"], ["${misc:Depends}"], ["d"]])

    def test_to_spdx(self):
        self.assertEqual(d2m.to_spdx("GPL-2+"), "GPL-2.0-or-later")
        self.assertEqual(d2m.to_spdx("GPL-2+ or Expat"), "GPL-2.0-or-later OR MIT")
        self.assertEqual(d2m.to_spdx("Apache-2.0"), "Apache-2.0")
        self.assertEqual(d2m.to_spdx("LGPL-2.1+ and BSD-3-clause"), "LGPL-2.1-or-later AND BSD-3-Clause")

    def test_debian_upstream_version(self):
        self.assertEqual(d2m.debian_upstream_version("1:2.3.4+dfsg-2"), "2.3.4")
        self.assertEqual(d2m.debian_upstream_version("0.40.0-3+deb13u1"), "0.40.0")
        self.assertEqual(d2m.debian_upstream_version("1"), "1")

    def test_dep_candidates(self):
        self.assertEqual(d2m.dep_candidates("zlib1g-dev"), ["zlib-dev"])
        self.assertEqual(d2m.dep_candidates("python3-requests")[0], "py3-requests")
        self.assertIn("libass-dev", d2m.dep_candidates("libass-dev"))
        self.assertIn("libfoo-dev", d2m.dep_candidates("libfoo2-dev"))

    def test_norm_path(self):
        self.assertEqual(d2m.norm_path("usr/lib/*/libfoo.so"), "usr/lib/libfoo.so")
        self.assertEqual(d2m.norm_path("/usr/lib/${DEB_HOST_MULTIARCH}/pkgconfig/"), "usr/lib/pkgconfig")
        self.assertEqual(d2m.norm_path("usr/lib/x86_64-linux-gnu/libfoo.so.1"), "usr/lib/libfoo.so.1")
        self.assertEqual(d2m.norm_path("usr/share/foo"), "usr/share/foo")

    def test_shell_path_keeps_globs_unquoted(self):
        self.assertEqual(d2m.shell_path("$D", "usr/lib/libfoo.so.*"), '"$D"/usr/lib/libfoo.so.*')
        self.assertEqual(d2m.shell_path("$D", "usr/include"), '"$D/usr/include"')

    def test_rules_parsing(self):
        rules = d2m.Rules(
            "V = 1.2\nX := $(V)-x\n%:\n\tdh $@ --buildsystem=meson --with python3\n"
            "override_dh_auto_configure:\n\tdh_auto_configure -- \\\n\t\t-Dfoo=true -Dbar=$(V)\n"
            "override_dh_installdeb:\n\tsed -e 's/@V@/$(V)/g' debian/postinst.in > debian/postinst\n")
        self.assertEqual(rules.buildsystem(), "meson")
        self.assertEqual(rules.dh_with(), ["python3"])
        self.assertEqual(rules.expand("$(X)"), "1.2-x")
        self.assertEqual(rules.configure_opts(), ["-Dfoo=true", "-Dbar=1.2"])
        self.assertEqual(rules.template_substitutions(), {"postinst": ("postinst.in", {"@V@": "V"})})

    def test_convert_script_flags_debian_only_tools(self):
        notes = []
        body, _ = d2m.convert_script("#!/bin/sh\nupdate-alternatives --install a b c 1\n", "postinst",
                                     "p", [], "/etc/p.conf", notes)
        self.assertIn(d2m.TODO, body)
        self.assertTrue(any("update-alternatives" in n for n in notes))

    def test_scalar_quoting(self):
        self.assertEqual(d2m.scalar("1.0"), "'1.0'")
        self.assertEqual(d2m.scalar("yes"), "'yes'")
        self.assertEqual(d2m.scalar("it's: x"), "'it''s: x'")
        self.assertEqual(d2m.scalar("plain-value"), "plain-value")


if __name__ == "__main__":
    unittest.main()
