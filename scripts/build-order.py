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

With --skip-published URL, a recipe that is selected only because the
tooling changed (or by --all) is left out for an architecture when the
repository at URL already has that version and epoch. Recipes whose own
files changed, and the --canary recipes, are always built.

Each wave is a list of {"package", "arch"} builds for the architectures in
--arch, minus those a recipe excludes with package.target-architecture and
those listed in packages/CI-SKIP.

Prints JSON: {"waves": [[...], ...], "count": N}, padded to --max-waves.
"""

import argparse
import gzip
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import urllib.request

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
        pkg = data.get("package", {})
        archs = pkg.get("target-architecture") or ["all"]
        version = "{}-r{}".format(pkg.get("version"), pkg.get("epoch", 0))
        recipes[name] = {"provides": provides, "needs": needs, "archs": archs,
                         "origin": pkg.get("name", name), "version": version}
    return recipes


def changed_recipes(ref, recipes):
    """Return (recipes whose files changed, whether the build tooling changed)."""
    out = subprocess.run(["git", "diff", "--name-only", ref, "HEAD"],
                         capture_output=True, text=True, check=True).stdout.split()
    selected, tooling = set(), False
    for path in out:
        if path.startswith(GLOBAL_TRIGGERS):
            tooling = True
        m = re.match(r"^packages/([^/]+?)(?:\.yaml$|/)", path)
        if m and m.group(1) in recipes:
            selected.add(m.group(1))
    return selected, tooling


def published(url, arch):
    """{(origin, version)} in the APKINDEX at URL/ARCH, or None if unreachable."""
    try:
        with urllib.request.urlopen("{}/{}/APKINDEX.tar.gz".format(url.rstrip("/"), arch),
                                    timeout=60) as resp:
            blob = resp.read()
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            text = tar.extractfile("APKINDEX").read().decode("utf-8", "replace")
    except (OSError, tarfile.TarError, KeyError, gzip.BadGzipFile) as exc:
        print("warning: {}/{}: {}; building everything".format(url, arch, exc), file=sys.stderr)
        return None
    out = set()
    for block in text.split("\n\n"):
        fields = dict(l.split(":", 1) for l in block.splitlines() if len(l) > 2 and l[1] == ":")
        if "V" in fields:
            out.add((fields.get("o") or fields.get("P"), fields["V"]))
    return out


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


def load_skips(path):
    """Read packages/CI-SKIP: {(recipe, arch)}."""
    skips = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                fields = line.split("#", 1)[0].split()
                if len(fields) == 2:
                    skips.add(tuple(fields))
    return skips


def builds(wave, recipes, archs, skips=frozenset()):
    """Matrix entries for one wave: every recipe on every architecture it supports.

    skips holds (recipe, arch) pairs to leave out."""
    out = []
    for name in wave:
        allowed = recipes[name]["archs"]
        out += [{"package": name, "arch": a} for a in archs
                if ("all" in allowed or a in allowed) and (name, a) not in skips]
    return out


def already_published(candidates, recipes, archs, index):
    """(recipe, arch) pairs among candidates whose version is in index[arch]."""
    out = set()
    for a in archs:
        if index.get(a) is None:
            continue
        for name in candidates:
            if (recipes[name]["origin"], recipes[name]["version"]) in index[a]:
                out.add((name, a))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument("--all", action="store_true")
    sel.add_argument("--filter")
    sel.add_argument("--changed-from", metavar="REF")
    ap.add_argument("--packages-dir", default="packages")
    ap.add_argument("--arch", default="x86_64", help="comma-separated architectures")
    ap.add_argument("--skip-published", metavar="URL",
                    help="repository whose published versions need no rebuild")
    ap.add_argument("--canary", default="", help="recipes always built (comma-separated)")
    ap.add_argument("--max-waves", type=int, default=6)
    args = ap.parse_args(argv)

    recipes = load_recipes(args.packages_dir)
    reusable = set()  # selected without a change of their own
    if args.all:
        selected = set(recipes)
        reusable = set(recipes)
    elif args.filter:
        names = {n.strip() for n in args.filter.split(",") if n.strip()}
        unknown = names - set(recipes)
        if unknown:
            sys.exit("error: unknown recipes: " + ", ".join(sorted(unknown)))
        selected = names
    else:
        direct, tooling = changed_recipes(args.changed_from, recipes)
        selected = set(recipes) if tooling else direct
        reusable = selected - direct
    reusable -= {n.strip() for n in args.canary.split(",") if n.strip()}

    result = waves(selected, recipes)
    if len(result) > args.max_waves:
        sys.exit("error: {} waves needed, the workflow runs {}".format(len(result), args.max_waves))
    archs = [a.strip() for a in args.arch.split(",") if a.strip()]
    skips = load_skips(os.path.join(args.packages_dir, "CI-SKIP"))
    reused = set()
    if args.skip_published and reusable:
        index = {a: published(args.skip_published, a) for a in archs}
        reused = already_published(reusable, recipes, archs, index)
    result = [b for b in (builds(w, recipes, archs, skips | reused) for w in result) if b]
    result += [[] for _ in range(args.max_waves - len(result))]
    print(json.dumps({"waves": result, "count": len(selected),
                      "reused": sorted("{}/{}".format(n, a) for n, a in reused)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
