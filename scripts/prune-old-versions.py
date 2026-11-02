#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Keep the newest versions of each package, delete the older .apk files.

    scripts/prune-old-versions.py --keep 3 repo/x86_64 [repo/aarch64 ...]

Packages are grouped by the pkgname in their .PKGINFO and ordered as apk
orders versions (1.10 > 1.9, 1.0_rc1 < 1.0 < 1.0_p1, -r2 > -r1). The
APKINDEX generated afterwards lists only what is kept, and the sync to
SourceForge deletes the rest there.

Standard library only.
"""

import argparse
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("remove_retired", os.path.join(HERE, "remove-retired.py"))
_retired = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_retired)
pkginfo = _retired.pkginfo

# apk's suffixes: the pre-release ones sort before the plain version, the others after
SUFFIXES = {"alpha": -4, "beta": -3, "pre": -2, "rc": -1, "": 0, "cvs": 1, "svn": 2, "git": 3, "hg": 4, "p": 5}


def version_key(version):
    """Sort key for an apk version such as 2.13_beta171-r2."""
    m = re.match(r"^(.*?)(?:-r(\d+))?$", version)
    main, release = m.group(1), int(m.group(2) or 0)
    base, *suffixes = main.split("_")
    parts = []
    for num, letter in re.findall(r"(\d+)([a-z]?)", base):
        parts.append((int(num), letter))
    sufs = []
    for s in suffixes:
        sm = re.match(r"^([a-z]*)(\d*)$", s)
        name, num = (sm.group(1), sm.group(2)) if sm else (s, "")
        sufs.append((SUFFIXES.get(name, 0), int(num or 0)))
    # no suffix sorts between the pre-release and the post-release ones
    sufs.append((0, 0))
    return parts, sufs, release


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--keep", type=int, default=3, help="versions to keep per package (default 3)")
    parser.add_argument("--dry-run", action="store_true", help="only print what would be deleted")
    parser.add_argument("dirs", nargs="+")
    args = parser.parse_args(argv)
    if args.keep < 1:
        parser.error("--keep must be at least 1")
    removed = 0
    for directory in args.dirs:
        if not os.path.isdir(directory):
            continue
        groups = {}
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".apk"):
                continue
            path = os.path.join(directory, name)
            info = pkginfo(path)
            pkg, ver = info.get("pkgname"), info.get("pkgver")
            if not pkg or not ver:
                print("skipped {} (no .PKGINFO)".format(path), file=sys.stderr)
                continue
            groups.setdefault(pkg, []).append((version_key(ver), ver, path))
        for pkg, builds in sorted(groups.items()):
            builds.sort(reverse=True)
            for _key, ver, path in builds[args.keep:]:
                if not args.dry_run:
                    os.remove(path)
                removed += 1
                print("{} {} {}".format("would remove" if args.dry_run else "removed", pkg, ver))
    print("{} old package file(s) {}".format(removed, "to remove" if args.dry_run else "removed"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
