#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""The published packages of this repository that a recipe's build needs.

    scripts/published-deps.py APKINDEX.tar.gz packages/foo.yaml

Prints the .apk file names (one per line): the build environment's packages
that this repository publishes, and what those depend on, transitively, as
apk resolves them (names, and provides such as so:, cmd:, pc:). Packages
Wolfi has are not listed. CI fetches these files over SFTP and builds with
them as a local repository, instead of downloading them from SourceForge
over HTTP, which SourceForge counts as user downloads.

Standard library and PyYAML.
"""

import importlib.util
import io
import os
import re
import sys
import tarfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("prune_old_versions", os.path.join(HERE, "prune-old-versions.py"))
_prune = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_prune)
version_key = _prune.version_key


def read_index(path):
    """[{field: value}] of an APKINDEX.tar.gz."""
    with tarfile.open(path, mode="r:gz") as tar:
        text = tar.extractfile("APKINDEX").read().decode("utf-8", "replace")
    entries = []
    for block in text.split("\n\n"):
        fields = dict(l.split(":", 1) for l in block.splitlines() if len(l) > 2 and l[1] == ":")
        if "P" in fields and "V" in fields:
            entries.append(fields)
    return entries


def bare(dep):
    """A dependency without its version constraint (so:libfoo.so.1>=2 -> so:libfoo.so.1)."""
    return re.split(r"[<>=~]", dep.strip().lstrip("!"), maxsplit=1)[0]


def build_packages(recipe):
    with open(recipe, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    packages = ((data.get("environment") or {}).get("contents") or {}).get("packages") or []
    return [bare(str(p)) for p in packages if p]


def needed(entries, wanted):
    """The newest entry for each name or provide, closed over its dependencies."""
    newest = {}
    for e in entries:
        if e["P"] not in newest or version_key(e["V"]) > version_key(newest[e["P"]]["V"]):
            newest[e["P"]] = e
    providers = {}
    for e in newest.values():
        for key in [e["P"]] + [bare(p) for p in e.get("p", "").split()]:
            providers.setdefault(key, e)
    out, todo = {}, [bare(w) for w in wanted]
    while todo:
        e = providers.get(todo.pop())
        if e is None or e["P"] in out:
            continue  # not published here (Wolfi has it), or already taken
        out[e["P"]] = e
        todo += [bare(d) for d in e.get("D", "").split() if not d.startswith("!")]
    return sorted("{}-{}.apk".format(e["P"], e["V"]) for e in out.values())


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    for name in needed(read_index(argv[0]), build_packages(argv[1])):
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
