#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""Remove every signature section from .apk files, in place.

An .apk is a concatenation of gzip streams: [signature] control data.
Signing an already signed package with `abuild-sign` prepends another
signature stream instead of replacing it; apk-tools, apko and melange then
read the second signature as the control section and reject the package
("control hash mismatch"). This script drops all leading signature-only
streams so the package can be signed again cleanly (`melange sign`).

    scripts/strip-apk-signatures.py repo/x86_64/*.apk

Standard library only.
"""

import io
import sys
import tarfile
import zlib


def split_streams(data):
    streams, pos = [], 0
    while pos < len(data):
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = d.decompress(data[pos:])
        used = len(data) - pos - len(d.unused_data)
        streams.append((data[pos:pos + used], raw))
        pos += used
    return streams


def is_signature(raw):
    """True if the tar stream holds only .SIGN.* entries."""
    names = []
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as tar:
            names = [m.name for m in tar.getmembers()]
    except tarfile.TarError:
        # signature streams have no end-of-archive marker; read one header
        if len(raw) >= 512:
            names = [raw[:100].split(b"\0", 1)[0].decode("utf-8", "replace")]
    return bool(names) and all(n.startswith(".SIGN.") for n in names)


def strip(path):
    with open(path, "rb") as fh:
        data = fh.read()
    streams = split_streams(data)
    keep = list(streams)
    while keep and is_signature(keep[0][1]):
        keep.pop(0)
    removed = len(streams) - len(keep)
    if len(keep) != 2:
        raise SystemExit("{}: expected control and data sections, found {}".format(path, len(keep)))
    if removed:
        with open(path, "wb") as fh:
            for raw_gz, _ in keep:
                fh.write(raw_gz)
    return removed


def main(paths):
    if not paths:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    for path in paths:
        print("{}: removed {} signature section(s)".format(path, strip(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
