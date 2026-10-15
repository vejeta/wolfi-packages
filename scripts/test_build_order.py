# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Tests for build-order.py: python3 -m unittest discover -s scripts"""

import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("build_order", os.path.join(HERE, "build-order.py"))
bo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bo)


def write(d, name, text):
    with open(os.path.join(d, name + ".yaml"), "w") as fh:
        fh.write(text)


class BuildOrderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        write(d, "liba", "package: {name: liba}\nsubpackages: [{name: liba-dev}]\n")
        write(d, "app", "package: {name: app}\nenvironment: {contents: {packages: [liba-dev, busybox]}}\n")
        write(d, "big", "package: {name: big, target-architecture: [x86_64]}\n"
                        "environment: {contents: {packages: [liba-dev]}}\n")
        self.recipes = bo.load_recipes(d)

    def tearDown(self):
        self.tmp.cleanup()

    def test_waves_follow_build_dependencies(self):
        self.assertEqual(bo.waves({"liba", "app", "big"}, self.recipes),
                         [["liba"], ["app", "big"]])

    def test_target_architecture_limits_builds(self):
        wave = bo.builds(["app", "big"], self.recipes, ["x86_64", "aarch64"])
        self.assertEqual(wave, [
            {"package": "app", "arch": "x86_64"},
            {"package": "app", "arch": "aarch64"},
            {"package": "big", "arch": "x86_64"},
        ])

    def test_ci_skip_removes_one_architecture(self):
        wave = bo.builds(["app"], self.recipes, ["x86_64", "aarch64"], {("app", "aarch64")})
        self.assertEqual(wave, [{"package": "app", "arch": "x86_64"}])

    def test_published_versions_are_reused(self):
        index = {"x86_64": {("liba", "1.0-r0")}, "aarch64": {("liba", "0.9-r0")}}
        self.recipes["liba"]["version"] = "1.0-r0"
        reused = bo.already_published({"liba", "app"}, self.recipes, ["x86_64", "aarch64"], index)
        self.assertEqual(reused, {("liba", "x86_64")})

    def test_unreachable_index_reuses_nothing(self):
        reused = bo.already_published({"liba"}, self.recipes, ["x86_64"], {"x86_64": None})
        self.assertEqual(reused, set())

    def test_cycle_is_reported(self):
        self.recipes["liba"]["needs"].add("app")
        with self.assertRaises(SystemExit):
            bo.waves({"liba", "app"}, self.recipes)


if __name__ == "__main__":
    unittest.main()
