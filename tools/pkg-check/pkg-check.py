#!/usr/bin/env python3
"""pkg-check: check whether a package already exists in Debian, Alpine or Wolfi.

Run it before investing time in packaging something that already exists.

    pkg-check --target debian --package mpv
    pkg-check --target alpine --package libass --version 0.17.4
    pkg-check --target all --package stremio

Standard library only.
"""

import argparse
import io
import json
import os
import re
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "pkg-check/0.1 (+https://github.com/vejeta/wolfi-packages)"
TIMEOUT = 60
CACHE_TTL = 6 * 3600

DEBIAN_MADISON = "https://api.ftp-master.debian.org/madison?f=json&package={name}"
DEBIAN_SUITE_ORDER = ["stable", "testing", "unstable", "oldstable", "experimental"]

ALPINE_INDEX = "https://dl-cdn.alpinelinux.org/alpine/{branch}/{repo}/{arch}/APKINDEX.tar.gz"
ALPINE_REPOS = ["main", "community", "testing"]

WOLFI_INDEX = "https://packages.wolfi.dev/os/{arch}/APKINDEX.tar.gz"

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Exit codes (the highest one across targets wins).
EXIT_ABSENT = 0
EXIT_PRESENT = 1
EXIT_OLDER = 2
EXIT_ERROR = 3


class Result:
    """Outcome of a lookup in one distribution."""

    def __init__(self, target, found, version=None, where=None, extra=None, error=None):
        self.target = target
        self.found = found
        self.version = version
        self.where = where
        self.extra = extra or []
        self.error = error


# --------------------------------------------------------------------------
# Version handling
# --------------------------------------------------------------------------

def upstream_version(version, target):
    """Strip distribution-specific decorations to get the upstream version."""
    v = version
    if target == "debian":
        v = v.split(":", 1)[-1]                 # epoch
        if "-" in v:
            v = v.rsplit("-", 1)[0]             # debian revision
        v = re.split(r"[+~](?:dfsg|ds|repack|really)", v)[0]
    else:
        v = re.sub(r"-r\d+$", "", v)            # alpine/wolfi pkgrel
    return v


def _tokens(version):
    return [int(t) if t.isdigit() else t for t in re.findall(r"\d+|[a-zA-Z]+", version)]


def compare_versions(a, b):
    """Return -1, 0 or 1. Numeric segments compare numerically, a trailing
    alphabetic segment (rc, beta, ...) sorts before the release."""
    ta, tb = _tokens(a), _tokens(b)
    for x, y in zip(ta, tb):
        if x == y:
            continue
        if isinstance(x, int) and isinstance(y, int):
            return -1 if x < y else 1
        if isinstance(x, int):
            return 1
        if isinstance(y, int):
            return -1
        return -1 if x < y else 1
    if len(ta) == len(tb):
        return 0
    longer, sign = (ta, 1) if len(ta) > len(tb) else (tb, -1)
    nxt = longer[min(len(ta), len(tb))]
    # 1.0.1 > 1.0 but 1.0rc1 < 1.0
    return sign if isinstance(nxt, int) else -sign


def recipe_version(name):
    """Version from packages/<name>.yaml in this repository, if present."""
    path = os.path.join(REPO_ROOT, "packages", name + ".yaml")
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                m = re.match(r"^\s{2}version:\s*['\"]?([^'\"\s#]+)", line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


# --------------------------------------------------------------------------
# HTTP + cache
# --------------------------------------------------------------------------

def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = os.path.join(base, "pkg-check")
    os.makedirs(path, exist_ok=True)
    return path


def fetch(url, cache=True):
    path = None
    if cache:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", url)
        path = os.path.join(cache_dir(), safe)
        if os.path.exists(path) and time.time() - os.path.getmtime(path) < CACHE_TTL:
            with open(path, "rb") as fh:
                return fh.read()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        data = resp.read()
    if path:
        with open(path, "wb") as fh:
            fh.write(data)
    return data


def parse_apkindex(blob):
    """Yield dicts (P=name, V=version, o=origin, ...) from an APKINDEX.tar.gz."""
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        member = tar.extractfile("APKINDEX")
        text = member.read().decode("utf-8", "replace")
    for block in text.split("\n\n"):
        entry = {}
        for line in block.splitlines():
            if len(line) > 2 and line[1] == ":":
                entry[line[0]] = line[2:]
        if entry:
            yield entry


def lookup_apkindex(target, name, urls, cache):
    """Search one or more APKINDEX files for a package or origin named `name`."""
    hits = []
    errors = []
    for label, url in urls:
        try:
            entries = parse_apkindex(fetch(url, cache))
        except (urllib.error.URLError, OSError, tarfile.TarError) as exc:
            errors.append("{}: {}".format(label, exc))
            continue
        for e in entries:
            if e.get("P") == name or (e.get("o") == name and e.get("P") != name):
                hits.append((label, e))
    if not hits:
        if errors and len(errors) == len(urls):
            return Result(target, False, error="; ".join(errors))
        return Result(target, False)
    exact = [h for h in hits if h[1].get("P") == name] or hits
    best = exact[0]
    for h in exact[1:]:
        if compare_versions(upstream_version(h[1]["V"], target),
                            upstream_version(best[1]["V"], target)) > 0:
            best = h
    label, e = best
    extra = []
    if e.get("P") != name:
        extra.append("only as subpackage(s) of origin '{}'".format(name))
    subs = sorted({h[1]["P"] for h in hits if h[1].get("P") != name})
    if subs:
        extra.append("subpackages: " + ", ".join(subs[:8]) + (" ..." if len(subs) > 8 else ""))
    return Result(target, True, e["V"], label, extra)


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------

def check_debian(name, args):
    url = DEBIAN_MADISON.format(name=urllib.parse.quote(name))
    try:
        data = json.loads(fetch(url, args.cache).decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return Result("debian", False, error=str(exc))
    suites = {}
    for item in data if isinstance(data, list) else [data]:
        for pkg in item.values():
            for suite, versions in pkg.items():
                if suite.endswith("-debug") or suite.endswith("-backports-sloppy"):
                    continue
                for ver in versions:
                    suites.setdefault(suite, []).append(ver)
    if not suites:
        return Result("debian", False)
    for suite in suites:
        suites[suite].sort(key=lambda v: _tokens(upstream_version(v, "debian")))
    preferred = args.debian_suite
    if preferred and preferred in suites:
        suite = preferred
    else:
        suite = next((s for s in DEBIAN_SUITE_ORDER if s in suites), sorted(suites)[0])
    extra = []
    if args.verbose:
        extra = ["{}: {}".format(s, ", ".join(v)) for s, v in sorted(suites.items())]
    return Result("debian", True, suites[suite][-1], suite, extra)


def check_alpine(name, args):
    urls = [("{}/{}".format(args.alpine_branch, repo),
             ALPINE_INDEX.format(branch=args.alpine_branch, repo=repo, arch=args.arch))
            for repo in ALPINE_REPOS]
    return lookup_apkindex("alpine", name, urls, args.cache)


def check_wolfi(name, args):
    urls = [("os", WOLFI_INDEX.format(arch=args.arch))]
    return lookup_apkindex("wolfi", name, urls, args.cache)


BACKENDS = {"debian": check_debian, "alpine": check_alpine, "wolfi": check_wolfi}
DISPLAY = {"debian": "Debian", "alpine": "Alpine", "wolfi": "Wolfi"}


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def report(name, result, yours, use_json):
    """Print one result and return its exit code."""
    distro = DISPLAY[result.target]
    status = "absent"
    code = EXIT_ABSENT
    if result.error:
        status, code = "error", EXIT_ERROR
    elif result.found:
        status, code = "present", EXIT_PRESENT
        if yours and compare_versions(upstream_version(result.version, result.target), yours) < 0:
            status, code = "older", EXIT_OLDER

    if use_json:
        print(json.dumps({
            "package": name, "target": result.target, "status": status,
            "version": result.version, "where": result.where,
            "yours": yours, "notes": result.extra, "error": result.error,
        }))
        return code

    if status == "error":
        print("! {}: could not query {}: {}".format(name, distro, result.error))
    elif status == "absent":
        print("✗ {} does NOT exist in {}".format(name, distro))
    elif status == "older":
        print("? {} exists in {} ({}) but older version: {} (yours: {})".format(
            name, distro, result.where, result.version, yours))
    else:
        print("✓ {} exists in {} ({}): {}".format(name, distro, result.where, result.version))
    for note in result.extra:
        print("    " + note)
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="pkg-check",
        description="Check whether a package already exists in Debian, Alpine or Wolfi.",
        epilog="Exit codes: 0 absent everywhere, 1 present, 2 present but older, 3 query error.")
    parser.add_argument("--target", "-t", action="append",
                        choices=sorted(BACKENDS) + ["all"],
                        help="distribution to query (repeatable; default: all)")
    parser.add_argument("--package", "-p", action="append", required=True,
                        help="package name (repeatable)")
    parser.add_argument("--version", "-V", dest="yours",
                        help="your version; defaults to packages/<name>.yaml if it exists")
    parser.add_argument("--arch", default="x86_64", help="architecture for APKINDEX lookups")
    parser.add_argument("--alpine-branch", default="edge", help="Alpine branch (edge, v3.22, ...)")
    parser.add_argument("--debian-suite", help="preferred Debian suite (stable, testing, unstable)")
    parser.add_argument("--no-cache", dest="cache", action="store_false",
                        help="do not use the local index cache")
    parser.add_argument("--json", action="store_true", help="one JSON object per line")
    parser.add_argument("--verbose", "-v", action="store_true", help="show all suites/branches")
    args = parser.parse_args(argv)

    targets = args.target or ["all"]
    if "all" in targets:
        targets = ["wolfi", "alpine", "debian"]

    rc = EXIT_ABSENT
    for name in args.package:
        yours = args.yours or recipe_version(name)
        for target in targets:
            rc = max(rc, report(name, BACKENDS[target](name, args), yours, args.json))
    return rc


if __name__ == "__main__":
    sys.exit(main())
