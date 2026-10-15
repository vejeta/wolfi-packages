#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Delete .apk files whose origin is listed in packages/RETIRED.

    scripts/remove-retired.py packages/RETIRED repo/x86_64 [repo/aarch64 ...]

The origin is read from each package's .PKGINFO (falling back to pkgname),
so subpackages of a retired recipe are removed as well.

An entry "name>=version" or "name<version" removes only the builds of that
origin in that version range, for a name that a new recipe reuses. Names of
architectures after the entry limit it to those directories (repo/aarch64).

Standard library only.
"""

import io
import os
import re
import sys
import tarfile
import zlib


def read_list(path):
    """Return {origin: ((operator, version) or None, {arch} or None)}."""
    retired = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            entry = line.split("#", 1)[0].strip()
            if entry:
                m = re.match(r"^([^<>=\s]+)\s*(?:(>=|<)\s*([^\s<>=]+))?((?:\s+[a-z0-9_]+)*)$", entry)
                if not m:
                    sys.exit("error: bad entry in {}: {}".format(path, entry))
                versions = (m.group(2), m.group(3)) if m.group(2) else None
                retired[m.group(1)] = (versions, set(m.group(4).split()) or None)
    return retired


def version_key(version):
    """Numeric sort key for versions such as 4.4.169-r1 (release ignored)."""
    version = re.sub(r"-r\d+$", "", version)
    return [int(n) for n in re.findall(r"\d+", version)]


def is_retired(retired, origin, version, arch):
    if origin not in retired:
        return False
    versions, arches = retired[origin]
    if arches is not None and arch not in arches:
        return False
    if versions is None:
        return True
    op, limit = versions
    older = version_key(version) < version_key(limit)
    return older if op == "<" else not older


def pkginfo(path):
    """Return the .PKGINFO fields of an .apk as a dict."""
    with open(path, "rb") as fh:
        data = fh.read()
    pos = 0
    while pos < len(data):
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = d.decompress(data[pos:])
        pos = len(data) - len(d.unused_data)
        try:
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
                member = tar.next()
                if member is not None and member.name == ".PKGINFO":
                    text = tar.extractfile(member).read().decode("utf-8", "replace")
                    fields = {}
                    for line in text.splitlines():
                        key, sep, value = line.partition(" = ")
                        if sep and key not in fields:
                            fields[key.strip()] = value.strip()
                    return fields
        except tarfile.TarError:
            continue
    return {}


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    retired = read_list(argv[0])
    removed = 0
    for directory in argv[1:]:
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".apk"):
                continue
            path = os.path.join(directory, name)
            info = pkginfo(path)
            origin = info.get("origin") or info.get("pkgname")
            arch = os.path.basename(os.path.normpath(directory))
            if is_retired(retired, origin, info.get("pkgver", ""), arch):
                os.remove(path)
                removed += 1
                print("removed {} (origin {})".format(path, origin))
    print("{} retired package file(s) removed".format(removed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
