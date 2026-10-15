# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Tests for the script of pipelines/scala/build.yaml:
python3 -m unittest discover -s scripts"""

import os
import re
import tempfile
import types
import unittest
import zipfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")


def load_script():
    with open(os.path.join(ROOT, "pipelines", "scala", "build.yaml")) as fh:
        runs = yaml.safe_load(fh)["pipeline"][0]["runs"]
    code = re.search(r"<<'PY'\n(.*?)\nPY\n", runs, re.S).group(1)
    mod = types.ModuleType("scala_build")
    exec(compile(code, "scala-build.py", "exec"), mod.__dict__)
    return mod


sb = load_script()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "scala-build")

    def tearDown(self):
        self.tmp.cleanup()

    def config(self, text, version="1.0"):
        write(self.path, text)
        return sb.read_config(self.path, version)

    def test_defaults(self):
        s, = self.config("# c\nArtifact: foo\nGroup: org.example\nScala-Version: 2.13\n")
        self.assertEqual(s["id"], "foo_2.13")
        self.assertEqual(s["version"], "1.0")
        self.assertIsNone(s["package"])
        self.assertTrue(s["install"])
        self.assertEqual(sb.default_sources("2.13"),
                         ["src/main/scala", "src/main/java", "src/main/scala-2", "src/main/scala-2.13"])
        self.assertEqual(sb.default_sources("3"), ["src/main/scala", "src/main/java", "src/main/scala-3"])

    def test_fields(self):
        st = self.config(
            "Artifact: foo\nGroup: g\nScala-Version: 3\nVersion: 2.0\n"
            "Sources: a/@BINVER@\n b\nManifest: Automatic-Module-Name: foo\n Other: @VERSION@\n\n"
            "Artifact: foo-java\nGroup: g\nScala-Version: 2.13\nCross-Version: none\nInstall: no\n")
        self.assertEqual(st[0]["id"], "foo_3")
        self.assertEqual(st[0]["sources"], ["a/3", "b"])
        self.assertEqual(st[0]["manifest"], ["Automatic-Module-Name: foo", "Other: 2.0"])
        self.assertEqual(st[1]["id"], "foo-java")
        self.assertFalse(st[1]["install"])

    def test_errors(self):
        for text, msg in (
            ("Artifact: a\nGroup: g\n", "missing field scala-version"),
            ("Artifact: a\nGroup: g\nScala-Version: 2.11\n", "unknown Scala-Version"),
            ("Artifact: a\nGroup: g\nScala-Version: 3\nColour: red\n", "unknown field colour"),
            ("Artifact: a\nGroup: g\nScala-Version: 3\n\nArtifact: a\nGroup: g\nScala-Version: 3\n",
             "defined twice"),
            ("Artifact: a\nGroup: g\nScala-Version: 3\nManifest: bad\n", "bad Manifest line"),
        ):
            with self.subTest(msg=msg):
                with self.assertRaisesRegex(sb.Error, msg):
                    self.config(text)

    def test_repository_file(self):
        st = sb.read_config(os.path.join(ROOT, "packages", "scala-xml", "scala-build"), "2.5.0")
        self.assertEqual([s["id"] for s in st], ["scala-xml_3", "scala-xml_2.13", "scala-xml_2.12"])
        self.assertEqual(st[1]["package"], "scala-xml-2.13")


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_sources(self):
        for f in ("src/main/scala/a/A.scala", "src/main/scala/a/gen/G.scala",
                  "src/main/java/a/J.java", "src/main/scala/a/notes.txt"):
            write(os.path.join(self.d, f), "")
        s = {"sources": None, "binver": "2.13", "exclude": ["src/**/gen/*"], "where": "x"}
        all_files, java = sb.collect_sources(s, self.d)
        self.assertEqual(all_files, ["src/main/java/a/J.java", "src/main/scala/a/A.scala"])
        self.assertEqual(java, ["src/main/java/a/J.java"])

    def test_jar_is_reproducible(self):
        write(os.path.join(self.d, "c", "b", "B.class"), "b")
        write(os.path.join(self.d, "c", "A.class"), "a")
        jars = []
        for n in (1, 2):
            jar = os.path.join(self.d, "{}.jar".format(n))
            sb.write_jar(jar, os.path.join(self.d, "c"), ["Automatic-Module-Name: x"], 1700000000)
            with open(jar, "rb") as fh:
                jars.append(fh.read())
        self.assertEqual(jars[0], jars[1])
        with zipfile.ZipFile(os.path.join(self.d, "1.jar")) as z:
            self.assertEqual(z.namelist(), ["META-INF/", "META-INF/MANIFEST.MF", "A.class", "b/", "b/B.class"])
            self.assertEqual(z.read("META-INF/MANIFEST.MF"),
                             b"Manifest-Version: 1.0\r\nAutomatic-Module-Name: x\r\n\r\n")

    def test_classpath_from_maven_repo(self):
        repo = os.path.join(self.d, "repo")
        base = os.path.join(repo, "org", "x")
        write(os.path.join(base, "a", "1.0", "a-1.0.jar"), "")
        write(os.path.join(base, "a", "1.0", "a-1.0.pom"),
              "<project><dependencies><dependency><groupId>org.x</groupId>"
              "<artifactId>b</artifactId><version>2.0</version></dependency>"
              "<dependency><groupId>org.x</groupId><artifactId>t</artifactId>"
              "<scope>test</scope></dependency></dependencies></project>")
        write(os.path.join(base, "b", "2.0", "b-2.0.jar"), "")
        old, sb.MAVEN_REPO = sb.MAVEN_REPO, repo
        try:
            s = {"classpath": ["org.x:a"], "binver": "2.13", "where": "x"}
            cp = sb.resolve_classpath(s, {}, self.d)
            with self.assertRaisesRegex(sb.Error, "not found"):
                sb.resolve_classpath({"classpath": ["org.x:c"], "binver": "2.13", "where": "x"}, {}, self.d)
        finally:
            sb.MAVEN_REPO = old
        self.assertEqual([x["path"][len(repo):] for x in cp], ["/org/x/a/1.0/a-1.0.jar", "/org/x/b/2.0/b-2.0.jar"])
        self.assertTrue(cp[1]["transitive"])

    def test_pom_version(self):
        self.assertEqual(sb.pom_version("<project><parent><version>1</version></parent>"
                                        "<version>2</version></project>"), "2")
        self.assertEqual(sb.pom_version("<project><parent><version>1</version></parent></project>"), "1")

    def test_install_layout(self):
        s = {"id": "foo_3", "version": "1.2", "group": "org.example"}
        bd = os.path.join(self.d, "bd")
        write(os.path.join(bd, "foo_3.jar"), "jar")
        write(os.path.join(bd, "foo_3.pom"), "pom")
        dest = os.path.join(self.d, "dest")
        sb.install(s, bd, dest)
        self.assertEqual(os.readlink(os.path.join(dest, "usr/share/java/foo_3.jar")), "foo_3-1.2.jar")
        jar = os.path.join(dest, "usr/share/maven-repo/org/example/foo_3/1.2/foo_3-1.2.jar")
        with open(jar) as fh:
            self.assertEqual(fh.read(), "jar")


if __name__ == "__main__":
    unittest.main()
