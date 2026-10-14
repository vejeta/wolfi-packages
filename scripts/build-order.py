#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Split the recipes to build into dependency waves.

A recipe that needs, at build time, a package produced by another recipe
of this repository must be built after it. Recipes are grouped into waves:
every recipe in wave N only depends on recipes of earlier waves (or on
packages that are already published). CI builds the waves in order and
makes the packages of earlier waves available to later ones.

Which recipes are built:
  --all                 every recipe
  --filter a,b,c        the named recipes
  --changed-from REF    recipes whose files changed since REF (git); a change
                        to the build tooling (pipelines/, this script, the
                        build workflows) selects every recipe

Prints JSON: {"waves": [[...], ...], "count": N}, padded to --max-waves.
"""

import argparse
import json
import os
import re
import subprocess
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("error: PyYAML is required (pip install pyyaml)")

GLOBAL_TRIGGERS = (
    "pipelines/",
    "scripts/build-order.py",
    ".github/workflows/build-packages.yml",
    ".github/workflows/build-wave.yml",
)


def load_recipes(pkgdir):
    recipes = {}
    for fn in sorted(os.listdir(pkgdir)):
        if not fn.endswith(".yaml"):
            continue
        with open(os.path.join(pkgdir, fn)) as fh:
            data = yaml.safe_load(fh) or {}
        name = fn[:-5]
        provides = {data.get("package", {}).get("name", name)}
        provides |= {s["name"] for s in data.get("subpackages") or [] if "name" in s}
        for p in (data.get("package", {}).get("dependencies") or {}).get("provides") or []:
            provides.add(re.split(r"[=<>~]", p, maxsplit=1)[0])
        needs = set()
        for dep in ((data.get("environment") or {}).get("contents") or {}).get("packages") or []:
            needs.add(re.split(r"[=<>~]", str(dep), maxsplit=1)[0])
        recipes[name] = {"provides": provides, "needs": needs}
    return recipes


def changed_recipes(ref, recipes):
    out = subprocess.run(["git", "diff", "--name-only", ref, "HEAD"],
                         capture_output=True, text=True, check=True).stdout.split()
    selected = set()
    for path in out:
        if path.startswith(GLOBAL_TRIGGERS):
            return set(recipes)
        m = re.match(r"^packages/([^/]+?)(?:\.yaml$|/)", path)
        if m and m.group(1) in recipes:
            selected.add(m.group(1))
    return selected


def waves(selected, recipes):
    provider = {}
    for name, r in recipes.items():
        for p in r["provides"]:
            provider.setdefault(p, name)
    deps = {n: {provider[d] for d in recipes[n]["needs"] if d in provider} & selected - {n}
            for n in selected}
    level = {}

    def depth(n, seen=()):
        if n in level:
            return level[n]
        if n in seen:
            raise SystemExit("error: build dependency cycle: " + " -> ".join(seen + (n,)))
        level[n] = 1 + max((depth(d, seen + (n,)) for d in deps[n]), default=0)
        return level[n]

    for n in sorted(selected):
        depth(n)
    out = [[] for _ in range(max(level.values(), default=0))]
    for n in sorted(selected):
        out[level[n] - 1].append(n)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument("--all", action="store_true")
    sel.add_argument("--filter")
    sel.add_argument("--changed-from", metavar="REF")
    ap.add_argument("--packages-dir", default="packages")
    ap.add_argument("--max-waves", type=int, default=6)
    args = ap.parse_args(argv)

    recipes = load_recipes(args.packages_dir)
    if args.all:
        selected = set(recipes)
    elif args.filter:
        names = {n.strip() for n in args.filter.split(",") if n.strip()}
        unknown = names - set(recipes)
        if unknown:
            sys.exit("error: unknown recipes: " + ", ".join(sorted(unknown)))
        selected = names
    else:
        selected = changed_recipes(args.changed_from, recipes)

    result = waves(selected, recipes)
    if len(result) > args.max_waves:
        sys.exit("error: {} waves needed, the workflow runs {}".format(len(result), args.max_waves))
    result += [[] for _ in range(args.max_waves - len(result))]
    print(json.dumps({"waves": result, "count": len(selected)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
