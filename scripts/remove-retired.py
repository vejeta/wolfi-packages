#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Delete .apk files whose origin is listed in packages/RETIRED.

    scripts/remove-retired.py packages/RETIRED repo/x86_64 [repo/aarch64 ...]

The origin is read from each package's .PKGINFO (falling back to pkgname),
so subpackages of a retired recipe are removed as well.

Standard library only.
"""

import io
import os
import sys
import tarfile
import zlib


def read_list(path):
    with open(path, encoding="utf-8") as fh:
        return {l.split("#", 1)[0].strip() for l in fh} - {""}


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
            if origin in retired:
                os.remove(path)
                removed += 1
                print("removed {} (origin {})".format(path, origin))
    print("{} retired package file(s) removed".format(removed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
