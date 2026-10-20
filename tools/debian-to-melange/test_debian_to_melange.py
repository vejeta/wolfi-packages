#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
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
    argv = ["--debian-dir", os.path.join(TESTDATA, name, "debian"), "--out", out, "--no-check-wolfi"] + case_args(name)
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


class StremioTest(unittest.TestCase):
    """Rust/cargo package with debian/rules overrides (stremio 1.2.0+ds-1)."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        convert("stremio", cls.tmp)
        with open(os.path.join(cls.tmp, "stremio.yaml")) as fh:
            cls.text = fh.read()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def test_rust_crates_are_not_build_dependencies(self):
        self.assertNotIn("librust", self.text)

    def test_build_dependencies_are_kept_even_if_unknown(self):
        self.assertIn("- libwebkitgtk-6.0-dev", self.text)
        self.assertIn("- mpv-dev  # Debian: libmpv-dev", self.text)

    def test_overrides_are_ported(self):
        self.assertIn("cargo build --release --features offline-build", self.text)
        self.assertIn("install -D -m755 target/release/stremio-linux-shell "
                      "${{targets.destdir}}/usr/libexec/stremio/stremio-bin", self.text)
        self.assertIn(".recipe-files/stremio-wrapper ${{targets.destdir}}/usr/bin/stremio", self.text)
        self.assertNotIn("dh-cargo-built-using", self.text)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "stremio", "stremio-wrapper")))

    def test_exports_become_environment(self):
        self.assertIn("RUSTFLAGS: --remap-path-prefix=/home/build=.", self.text)
        self.assertNotIn("CARGO_HOME", self.text)

    def test_files_excluded_and_install_files(self):
        self.assertIn("rm -rf data/server.js", self.text)
        self.assertIn('cp -a data/com.stremio.Stremio.desktop "${{targets.destdir}}/usr/share/applications/"', self.text)
        self.assertIn('install -Dm644 data/stremio.1 -t "${{targets.destdir}}/usr/share/man/man1"', self.text)

    def test_github_watch_becomes_git_checkout(self):
        self.assertIn("uses: git-checkout", self.text)
        self.assertIn("repository: https://github.com/Stremio/stremio-linux-shell", self.text)
        self.assertIn("tag: v${{package.version}}", self.text)
        self.assertIn("TODO(debian-to-melange): set expected-commit", self.text)

    def test_patches_live_in_package_directory(self):
        # copied next to the recipe, then moved out of the build tree
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "stremio", "0001-disable-image-exr-feature.patch")))
        self.assertIn("for f in 0001-disable-image-exr-feature.patch", self.text)
        self.assertIn("patches: .recipe-files/0001-disable-image-exr-feature.patch", self.text)
        self.assertIn('"${{targets.destdir}}"/usr/share/doc/stremio/copyright', self.text)


class JvmPackagesTest(unittest.TestCase):
    """dh-scala and scala-2.13 (Debian Java team, salsa.debian.org/mendezr)."""

    @staticmethod
    def text(name):
        out = tempfile.mkdtemp()
        try:
            convert(name, out)
            with open(os.path.join(out, name + ".yaml")) as fh:
                return fh.read()
        finally:
            shutil.rmtree(out)

    def test_watch_v5_git_mode_becomes_git_checkout(self):
        text = self.text("scala-2.13")
        self.assertIn("repository: https://github.com/scala/scala", text)
        self.assertIn("tag: v${{package.version}}", text)

    def test_java_libraries_and_libjs(self):
        text = self.text("scala-2.13")
        self.assertIn("Java library, fetch from Maven Central (Debian: libjline3-java)", text)
        self.assertNotIn("- libjs-jquery", text)
        self.assertNotIn("- maven-repo-helper", text)
        self.assertIn("JAVA_HOME: /usr/lib/jvm/default-jvm", text)

    def test_build_profiles_are_honoured(self):
        text = self.text("scala-2.13")
        env = text.split("environment:", 1)[1].split("pipeline:", 1)[0]
        self.assertNotIn("scala-2.13-stage0", env)      # only with <pkg.scala.stage0>
        self.assertIn("- scala-2.13\n", env)             # <!pkg.scala.stage0>: normal build
        self.assertNotIn("$(firstword", text)

    def test_self_hosting_is_reported(self):
        out = tempfile.mkdtemp()
        try:
            with redirect_stderr(io.StringIO()) as err:
                d2m.main(["--debian-dir", os.path.join(TESTDATA, "scala-2.13", "debian"), "--out", out, "--no-check-wolfi"])
        finally:
            shutil.rmtree(out)
        self.assertIn("self-hosting", err.getvalue())

    def test_perl_modules_and_jdk(self):
        text = self.text("dh-scala")
        self.assertIn("perl-archive-zip  # Debian: libarchive-zip-perl", text)
        self.assertIn("openjdk-25-default-jdk  # Debian: default-jdk-headless", text)
        self.assertIn("autopkgtest: debian/tests/build-library 2.13", text)


class GitWatchTest(unittest.TestCase):
    """debian/watch v5 in git mode on a forge other than GitHub (xwpe, Codeberg)."""

    def test_codeberg_git_checkout(self):
        with tempfile.TemporaryDirectory() as out:
            convert("xwpe", out)
            with open(os.path.join(out, "xwpe.yaml")) as fh:
                text = fh.read()
        self.assertIn("repository: https://codeberg.org/mendezr/xwpe.git", text)
        self.assertIn("tag: v${{package.version}}", text)
        self.assertIn("update:\n  enabled: true\n  git:\n    strip-prefix: v", text)
        self.assertNotIn("example.invalid", text)
        self.assertIn("- xorgproto  # Debian: x11proto-core-dev", text)
        test_env = text.split("\ntest:", 1)[1]
        self.assertEqual(test_env.count("- glibc-locale-en"), 1)


class ScalaBuildTest(unittest.TestCase):
    """dh --buildsystem=scala becomes the scala/build pipeline."""

    def test_scala_build(self):
        with tempfile.TemporaryDirectory() as out:
            convert("scala-xml", out)
            with open(os.path.join(out, "libscala-xml-java.yaml")) as fh:
                text = fh.read()
            self.assertTrue(filecmp.cmp(os.path.join(out, "libscala-xml-java", "scala-build"),
                                        os.path.join(TESTDATA, "scala-xml", "debian", "scala-build"), False))
        self.assertIn("  - uses: scala/build\n", text)
        self.assertIn("- scala-2.12  # Debian: scala", text)
        self.assertNotIn("dh-sequence-scala", text)


class AutopkgtestTest(unittest.TestCase):

    def test_autopkgtests_become_test_steps(self):
        out = tempfile.mkdtemp()
        try:
            convert("libfoo", out)
            with open(os.path.join(out, "libfoo.yaml")) as fh:
                text = fh.read()
        finally:
            shutil.rmtree(out)
        test = text.split("\ntest:", 1)[1]
        self.assertIn("name: 'autopkgtest: foo-tool --version'", test)
        self.assertIn("name: 'autopkgtest: link-test'", test)
        self.assertIn('export AUTOPKGTEST_TMP="$(mktemp -d)"', test)
        self.assertIn("- libfoo-dev", test)
        self.assertIn("- build-base  # Debian: build-essential", test)
        self.assertNotIn("#!/bin/sh", test)


class BuildOptionTest(unittest.TestCase):

    def test_build_reports_a_missing_melange(self):
        out = tempfile.mkdtemp()
        try:
            argv = ["--debian-dir", os.path.join(TESTDATA, "libfoo", "debian"), "--out", out,
                    "--build", "--melange", "/nonexistent/melange"] + case_args("libfoo")
            with redirect_stderr(io.StringIO()) as err:
                rc = d2m.main(argv)
        finally:
            shutil.rmtree(out)
        self.assertEqual(rc, 3)
        self.assertIn("melange build: FAILED", err.getvalue())


class HelperTest(unittest.TestCase):

    def test_parse_relations(self):
        rel = d2m.parse_relations("a (>= 1), b | c [amd64], ${misc:Depends}, d:any <!nocheck>")
        self.assertEqual(rel, [["a"], ["b", "c"], ["${misc:Depends}"], ["d"]])
        self.assertEqual(d2m.parse_relations("x <stage1>, y <!stage1>, z <stage1> <!nocheck>"), [["y"], ["z"]])
        # the recipes build with the nocheck profile
        self.assertEqual(d2m.parse_relations("a, t <!nocheck>, n <nocheck>", d2m.BUILD_PROFILES), [["a"], ["n"]])

    def test_to_spdx(self):
        self.assertEqual(d2m.to_spdx("GPL-2+"), "GPL-2.0-or-later")
        self.assertEqual(d2m.to_spdx("GPL-2+ or Expat"), "GPL-2.0-or-later OR MIT")
        self.assertEqual(d2m.to_spdx("Apache-2.0"), "Apache-2.0")
        self.assertEqual(d2m.to_spdx("LGPL-2.1+ and BSD-3-clause"), "LGPL-2.1-or-later AND BSD-3-Clause")

    def test_alternatives(self):
        text = ("update-alternatives --install /usr/bin/fr fr /usr/bin/fr-a 50 \\\n"
                "  --slave /usr/share/man/man1/fr.1.gz fr.1.gz /usr/share/man/man1/fr-a.1.gz\n"
                "update-alternatives --install /usr/bin/fr fr /usr/bin/fr-b 30\n"
                "update-alternatives --install $LINK x $PATH 10\n")
        self.assertEqual(d2m.alternatives(text), [
            ("/usr/bin/fr", "/usr/bin/fr-a", [("/usr/share/man/man1/fr.1.gz", "/usr/share/man/man1/fr-a.1.gz")])])
        step = d2m.alternatives_step(d2m.alternatives(text), "${{targets.destdir}}")
        self.assertIn("alt /usr/bin/fr /usr/bin/fr-a\n", step["runs"])

    def test_drop_foreign_fakechroot(self):
        script = ("for v in a b; do\n"
                  "\tmmdebstrap --variant=$v --mode=root unstable root.tar\n"
                  "\ttouch fc.tar\n"
                  "\trunuser -u u -- mmdebstrap --variant=$v --mode=fakechroot unstable fc.tar\n"
                  "\tcmp root.tar fc.tar\n"
                  "\trm root.tar fc.tar\n"
                  "done\n")
        out, dropped = d2m.drop_foreign_fakechroot(script)
        self.assertTrue(dropped)
        self.assertIn("--mode=root", out)
        self.assertNotIn("fc.tar", out)
        self.assertIn("\trm root.tar\n", out)
        self.assertEqual(d2m.drop_foreign_fakechroot("true\n"), ("true\n", False))

    def test_debian_upstream_version(self):
        self.assertEqual(d2m.debian_upstream_version("1:2.3.4+dfsg-2"), "2.3.4")
        self.assertEqual(d2m.debian_upstream_version("0.40.0-3+deb13u1"), "0.40.0")
        self.assertEqual(d2m.debian_upstream_version("1"), "1")

    def test_dep_candidates(self):
        self.assertEqual(d2m.dep_candidates("zlib1g-dev"), ["zlib-dev"])
        self.assertIn("gtk-4-dev", d2m.dep_candidates("libgtk-4-dev"))
        self.assertIn("webkitgtk-6.0-dev", d2m.dep_candidates("libwebkitgtk-6.0-dev"))
        self.assertEqual(d2m.dep_candidates("libxml-libxml-perl")[0], "perl-xml-libxml")
        self.assertEqual(d2m.dep_candidates("openjdk-25-jdk-headless"), ["openjdk-25"])
        self.assertEqual(d2m.dep_candidates("openjdk-21-jre-headless"), ["openjdk-21-jre"])
        self.assertEqual(d2m.dep_candidates("default-jdk-headless"), ["openjdk-25-default-jdk"])
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

    def test_upstream_version_plus_digits(self):
        self.assertEqual(d2m.debian_upstream_version("0.35.0+20060710.6"), "0.35.0.20060710.6")
        self.assertEqual(d2m.debian_upstream_version("1.2+git20170224-1"), "1.2_git20170224")

    def test_xml_catalogs(self):
        cats = d2m.xml_catalogs(
            "local;docbook-xsl/catalog.xml;/usr/share/xml/docbook/stylesheet/docbook-xsl/catalog.xml\n\n"
            "root;uri;http://docbook.sourceforge.net/release/xsl/\n"
            "package;uri;http://docbook.sourceforge.net/release/xsl/;/usr/share/xml/x/catalog.xml\n")
        self.assertEqual(cats["local"], [("docbook-xsl/catalog.xml",
                                          "usr/share/xml/docbook/stylesheet/docbook-xsl/catalog.xml")])
        self.assertEqual(cats["package"], [("uri", "http://docbook.sourceforge.net/release/xsl/",
                                            "/usr/share/xml/x/catalog.xml")])

    def test_rules_arch_indep_configure(self):
        # aptitude: a full build configures twice, -indep last, so the docs are built
        rules = d2m.Rules(
            "ifneq (,$(filter nocheck,$(DEB_BUILD_OPTIONS)))\n  OPTS_TESTS = --disable-tests\nendif\n"
            "override_dh_auto_configure-arch:  OPTS_DOCS = --disable-docs\n"
            "override_dh_auto_configure-indep: OPTS_DOCS =\n"
            "override_dh_auto_configure-arch override_dh_auto_configure-indep:\n"
            "\tdh_auto_configure -- --htmldir='$${docdir}/html' $(OPTS_DOCS) $(OPTS_TESTS)\n")
        self.assertEqual(rules.configure_opts(), ["--htmldir='${docdir}/html'", "--disable-tests"])

    def test_convert_script_flags_debian_only_tools(self):
        notes = []
        body, _ = d2m.convert_script("#!/bin/sh\npy3compile -p foo\n", "postinst",
                                     "p", [], "/etc/p.conf", notes)
        self.assertIn(d2m.TODO, body)
        self.assertTrue(any("py3compile" in n for n in notes))

    def test_convert_script_records_tool_packages(self):
        d2m.SCRIPT_DEPS.clear()
        body, _ = d2m.convert_script("#!/bin/sh\nupdate-alternatives --install a b c 1\n"
                                     "touch /var/lib/ucf/hashfile\n", "postinst", "p", [], "/etc/p.conf", [])
        self.assertNotIn(d2m.TODO, body)
        self.assertEqual(d2m.SCRIPT_DEPS, {"postinst": {"dpkg"}})  # not ucf: only a path
        d2m.SCRIPT_DEPS.clear()

    def test_scalar_quoting(self):
        self.assertEqual(d2m.scalar("1.0"), "'1.0'")
        self.assertEqual(d2m.scalar("yes"), "'yes'")
        self.assertEqual(d2m.scalar("it's: x"), "'it''s: x'")
        self.assertEqual(d2m.scalar("plain-value"), "plain-value")

    def test_dh_ocaml_subst(self):
        self.assertEqual(d2m.dh_ocaml_subst("@OCamlStdlibDir@/csexp/META\nOPT: @OCamlStdlibDir@/csexp/*.a\n"
                                            "DYN: @OCamlDllDir@/dllfoo.so\n"),
                         "usr/lib/ocaml/csexp/META\nusr/lib/ocaml/csexp/*.a\nusr/lib/ocaml/stublibs/dllfoo.so\n")

    def test_watch_v5_matching_pattern(self):
        watch = ("Version: 5\n\nSource: https://gitlab.inria.fr/fpottier/@PACKAGE@/tags?sort=updated_desc\n"
                 "Matching-Pattern: -/archive/v?\\d[\\d.]+/@PACKAGE@-@ANY_VERSION@@ARCHIVE_EXT@\n")
        self.assertEqual(d2m.watch_tarball_urls(watch, "menhir", "20260209")[0],
                         "https://gitlab.inria.fr/fpottier/menhir/-/archive/20260209/menhir-20260209.tar.gz")

    def test_install_entries_expand_braces(self):
        self.assertEqual(list(d2m.install_entries("usr/lib/ocaml/optint/*.{cma,cmxs}\n")),
                         [("usr/lib/ocaml/optint/*.cma", "usr/lib/ocaml/optint", None),
                          ("usr/lib/ocaml/optint/*.cmxs", "usr/lib/ocaml/optint", None)])

    def test_ocaml_names_map_to_wolfi(self):
        self.assertEqual(d2m.NAME_MAP["libstdlib-ocaml-dev"], ["ocaml", "ocaml-findlib-compat"])
        self.assertEqual(d2m.NAME_MAP["libfindlib-ocaml-dev"], ["ocaml-findlib", "ocamlfind", "ocaml-findlib-compat"])
        self.assertIn(("dune-project", "ocaml_dune"), d2m.BUILDSYSTEM_FILES)


if __name__ == "__main__":
    unittest.main()
