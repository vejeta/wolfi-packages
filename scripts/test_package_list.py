# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Tests for scripts/package-list.py."""

import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("package_list", os.path.join(HERE, "package-list.py"))
pl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pl)

RECIPE = """\
package:
  name: foo
  version: '1.0'
  description: Foo | bar
  copyright:
    - license: MIT
data:
  - name: targets
    items:
      a: x
      b: y
subpackages:
  - name: foo-dev
  - range: targets
    name: foo-${{range.key}}
"""


class PackageListTest(unittest.TestCase):

    def test_rows_count_ranged_subpackages(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "foo.yaml"), "w") as fh:
                fh.write(RECIPE)
            rows = pl.recipes(tmp)
        self.assertEqual(rows, [("foo", "1.0", "Foo | bar", "MIT", 3)])

    def test_render_escapes_pipes(self):
        text = pl.render([("foo", "1.0", "Foo | bar", "MIT", 3)])
        self.assertIn("1 recipes", text)
        self.assertIn("| [foo](packages/foo.yaml) | 1.0 | Foo \\| bar | MIT | 3 |", text)

    def test_repository_list_is_up_to_date(self):
        self.assertEqual(pl.main(["--check"]), 0, "run scripts/package-list.py")


if __name__ == "__main__":
    unittest.main()
