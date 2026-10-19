#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""debian-to-melange: convert Debian source packaging to a melange recipe.

    debian-to-melange --from-debian stremio-server-installer
    debian-to-melange --debian-dir ~/src/foo/debian --out packages/
    debian-to-melange --debian-dir foo/debian --upstream-url https://.../foo-1.0.tar.gz --download

Reads debian/control, changelog, copyright, rules, patches/series,
maintainer scripts, debconf templates and *.install/*.links/*.dirs/*.docs,
and writes <out>/<name>.yaml plus auxiliary files in <out>/<name>/.

Everything that cannot be converted mechanically is reported on stderr and
left as a "TODO(debian-to-melange)" comment in the generated recipe.

Standard library only.
"""

import argparse
import glob
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import textwrap
import urllib.error
import urllib.parse
import urllib.request

__version__ = "0.1.0"

USER_AGENT = "debian-to-melange/{} (+https://github.com/vejeta/wolfi-packages)".format(__version__)
SOURCES_API = "https://sources.debian.org/api/src/{name}/{version}/{path}/"
SOURCES_RAW = "https://sources.debian.org/data/{area}/{prefix}/{name}/{version}/{path}"
TODO = "TODO(debian-to-melange)"

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_CHECK = os.path.join(HERE, "..", "pkg-check", "pkg-check.py")


# ==========================================================================
# Package name mapping Debian -> Wolfi
# ==========================================================================

# Build tooling that has no equivalent (or is implicit) in melange.
DROP = {
    "debhelper", "debhelper-compat", "cdbs", "quilt", "po-debconf", "debconf",
    "debconf-2.0", "lsb-base", "dpkg-dev", "init-system-helpers",
    "sensible-utils", "base-files", "base-passwd", "ucf",
    # pybuild plugins: py/pip-build-install builds any PEP 517 project
    "pybuild-plugin-pyproject",
    # Debian-only Java helpers (Maven repository layout, jar symlinks)
    "maven-repo-helper", "maven-debian-helper", "javahelper",
}
DROP_PREFIXES = ("dh-", "dh_", "librust-")

# Exact Debian -> Wolfi mappings (runtime and build).
NAME_MAP = {
    "build-essential": "build-base",
    "gcc": "build-base",
    "g++": "build-base",
    "make": "make",
    "ninja-build": "ninja",
    "xsltproc": "libxslt",
    "sqv": "sequoia-sqv",
    "sq": "sequoia-sq",
    "stunnel4": "stunnel",
    "db-util": "db-utils",
    "valgrind-if-available": "valgrind",
    "pkg-config": "pkgconf-dev",
    "mawk": "gawk",
    # Wolfi ships the DocBook XSL stylesheets, and their catalog, in docbook-xml
    "docbook-xsl": "docbook-xml",
    "awk": "gawk",
    "pkgconf": "pkgconf-dev",
    "ca-certificates": "ca-certificates-bundle",
    "golang-go": "go",
    "x11proto-core-dev": "xorgproto",
    "libcairo2-dev": "cairo-dev",
    "libpango1.0-dev": "pango-dev",
    "libjson-c-dev": "json-c-dev",
    "x11proto-dev": "xorgproto",
    "librsvg2-bin": "rsvg-convert",
    "python3-pil": "py3-pillow",
    "libc6-dev": "glibc-dev",
    "locales-all": "glibc-locales",
    # Scala compilers (dh-scala's table): scala is Debian's 2.12 series
    "scala": "scala-2.12",
    "scala3": "scala-3.8",
    "golang": "go",
    "cargo": "rust",
    "rustc": "rust",
    "python3-all": "python3",
    "python3-all-dev": "python3-dev",
    "python3-setuptools": "py3-setuptools",
    "zlib1g-dev": "zlib-dev",
    "zlib1g": "zlib",
    "libssl-dev": "openssl-dev",
    "libcurl4-openssl-dev": "curl-dev",
    "libcurl4-gnutls-dev": "curl-dev",
    "libcurl-dev": "curl-dev",
    "libglib2.0-dev": "glib-dev",
    "libgtk-3-dev": "gtk-3-dev",
    "libncurses-dev": "ncurses-dev",
    "libncurses5-dev": "ncurses-dev",
    "libncursesw5-dev": "ncurses-dev",
    "libreadline-dev": "readline-dev",
    "libbz2-dev": "bzip2-dev",
    "liblzma-dev": "xz-dev",
    "libzstd-dev": "zstd-dev",
    "libsqlite3-dev": "sqlite-dev",
    "libjpeg-dev": "libjpeg-turbo-dev",
    "libjpeg62-turbo-dev": "libjpeg-turbo-dev",
    "libfreetype-dev": "freetype-dev",
    "libfreetype6-dev": "freetype-dev",
    "libfontconfig-dev": "fontconfig-dev",
    "libfontconfig1-dev": "fontconfig-dev",
    "libasound2-dev": "alsa-lib-dev",
    "libpulse-dev": "pulseaudio-dev",
    "libgl-dev": "mesa-dev",
    "libgl1-mesa-dev": "mesa-dev",
    "libegl-dev": "mesa-dev",
    "libegl1-mesa-dev": "mesa-dev",
    "libgles-dev": "mesa-dev",
    "libgbm-dev": "mesa-dev",
    "libvulkan-dev": "vulkan-loader-dev",
    "libavcodec-dev": "ffmpeg-dev",
    "libavformat-dev": "ffmpeg-dev",
    "libavutil-dev": "ffmpeg-dev",
    "libavfilter-dev": "ffmpeg-dev",
    "libswscale-dev": "ffmpeg-dev",
    "libswresample-dev": "ffmpeg-dev",
    "libpcre2-dev": "pcre2-dev",
    "libexpat1-dev": "expat-dev",
    "uuid-dev": "util-linux-dev",
    "libblkid-dev": "util-linux-dev",
    "libmount-dev": "util-linux-dev",
    "libudev-dev": "systemd-dev",
    "libsystemd-dev": "systemd-dev",
    "libdbus-1-dev": "dbus-dev",
    "libicu-dev": "icu-dev",
    "libboost-dev": "boost-dev",
    "libboost-all-dev": "boost-dev",
    "qtbase5-dev": "qt5-qtbase-dev",
    "qtbase5-dev-tools": "qt5-qtbase-dev",
    "qtdeclarative5-dev": "qt5-qtdeclarative-dev",
    "qtwebengine5-dev": "qt5-qtwebengine-dev",
    "qt6-base-dev": "qt6-qtbase-dev",
    "qt6-declarative-dev": "qt6-qtdeclarative-dev",
    "libmpv-dev": "mpv-dev",
    "default-jdk": "openjdk-25-default-jdk",
    "default-jdk-headless": "openjdk-25-default-jdk",
    "default-jre": "openjdk-25-default-jvm",
    "default-jre-headless": "openjdk-25-default-jvm",
    "libglib2.0-bin": "glib",
    "adduser": "shadow",
    "procps": "procps",
    "xz-utils": "xz",
    "bzip2": "bzip2",
    "openssl": "openssl",
    "nodejs": "nodejs",
    # Debian's xvfb ships Xvfb and xvfb-run, and depends on the keymaps that
    # Wolfi's Xvfb needs too but does not pull in
    "xvfb": ["xvfb-run", "xkbcomp", "xkeyboard-config"],
    "xkb-data": "xkeyboard-config",
    "bsdextrautils": "util-linux-misc",  # column, hexdump, col, ...
    "libcap2-bin": "libcap-utils",  # setcap, getcap, capsh
    "gnu-which": "which",
    # compiled locales (glibc-locales only has their sources)
    "locales-all": "glibc-locale-en",
    "locales": "glibc-locale-en",
    # Wolfi has ImageMagick 7 only, which lost the XWD reader that Debian's
    # ImageMagick 6 has; netpbm's xwdtopnm fills the gap
    "imagemagick": ["imagemagick-7", "netpbm"],
    "libc6-dev": "glibc-dev",
    "npm": "npm",
}


def lib_main(binary, source):
    """Is `binary` the shared library package (libfoo1) of source libfoo?"""
    return bool(source) and re.match(r"^{}[\d.]+(t64)?$".format(re.escape(source)), binary) is not None


def perl_name(binary):
    """Wolfi names Perl modules perl-foo, Debian libfoo-perl."""
    m = re.match(r"^lib(.+)-perl$", binary)
    return "perl-" + m.group(1) if m else binary


# The Python behind Wolfi's python3.
DEFAULT_PYTHON = "3.13"


def python_name(binary):
    """Wolfi names Python modules py3-foo, Debian python3-foo."""
    m = re.match(r"^python3-(.+)$", binary)
    return "py3-" + m.group(1) if m and not binary.endswith("-dev") else binary


# Debian packages that bundle several upstream programs; Wolfi packages
# them one by one.
BUNDLES = {
    "x11-apps": "atobm bitmap bmtoa ico oclock rendercheck transset x11perf xbiff xcalc xclipboard "
                "xclock xconsole xcursorgen xcutsel xditview xedit xeyes xgc xload xlogo xmag xman "
                "xmore xwd xwud".split(),
    "x11-xserver-utils": "iceauth sessreg showrgb xcmsdb xgamma xhost xkill xmodmap xrandr xrdb "
                         "xrefresh xset xsetmode xsetpointer xsetroot xstdcmap xvidtune".split(),
    # the X.Org misc fonts (font-misc-misc is font-misc in Wolfi)
    "xfonts-base": "font-arabic-misc font-cursor-misc font-daewoo-misc font-dec-misc font-isas-misc "
                   "font-jis-misc font-micro-misc font-misc font-mutt-misc font-schumacher-misc "
                   "font-sony-misc font-sun-misc".split(),
    "x11-xkb-utils": "setxkbmap xkbcomp xkbevd xkbprint xkbutils".split(),
    "x11-utils": "appres editres listres luit viewres xdpyinfo xdriinfo xev xfd xfontsel xlsatoms "
                 "xlsclients xlsfonts xmessage xprop xvinfo xwininfo".split(),
}


# Gems that Wolfi's ruby package bundles (Debian packages them as ruby-<gem>).
RUBY_BUNDLED_GEMS = {
    "abbrev", "benchmark", "bigdecimal", "csv", "debug", "drb", "getoptlong", "logger", "matrix",
    "minitest", "mutex-m", "net-ftp", "net-pop", "net-smtp", "nkf", "observer", "ostruct",
    "power-assert", "prime", "pstore", "racc", "rake", "rbs", "rdoc", "readline", "reline",
    "resolv-replace", "rinda", "rss", "syslog", "test-unit", "typeprof",
}


def dep_candidates(name):
    """Ordered Wolfi name candidates for a Debian package name."""
    m = re.match(r"^ruby-(.+)$", name)
    if m and m.group(1) in RUBY_BUNDLED_GEMS:
        return ["ruby"]
    if isinstance(NAME_MAP.get(name), list):
        return NAME_MAP[name][:1]
    if name in NAME_MAP:
        return [NAME_MAP[name]]
    cands = [name]
    m = re.match(r"^openjdk-(\d+)-(jdk|jre)(?:-headless)?$", name)
    if m:
        return ["openjdk-{}".format(m.group(1)) if m.group(2) == "jdk" else "openjdk-{}-jre".format(m.group(1))]
    m = re.match(r"^lib(.+)-perl$", name)
    if m:
        # Wolfi names Perl modules after the CPAN distribution: Text-Iconv is
        # perl-text-iconv, but libintl-perl is perl-libintl-perl
        return ["perl-" + m.group(1), "perl-" + name, name]
    m = re.match(r"^python3-(.+)$", name)
    if m and not name.endswith("-dev"):
        cands = ["py3-" + m.group(1), name]
    m = re.match(r"^lib(.+?)(-?[\d.]+)?-dev$", name)
    if m:
        base, ver = m.group(1), m.group(2) or ""
        cands += ["lib{}-dev".format(base), "{}-dev".format(base)]
        if ver:
            cands.append("{}{}-dev".format(base, ver))
    m = re.match(r"^lib(.+?)[\d.]+$", name)
    if m:
        cands += ["lib" + m.group(1), m.group(1)]
    seen = []
    for c in cands:
        if c not in seen:
            seen.append(c)
    return seen


# Packages published by this repository (Wolfi Community Packages).
COMMUNITY_INDEX = "https://downloads.sourceforge.net/project/wolfi/{arch}/APKINDEX.tar.gz"


def recipe_names(directory):
    """Package and subpackage names defined by the melange recipes in `directory`."""
    names = set()
    for f in glob.glob(os.path.join(directory, "*.yaml")):
        with open(f, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        block = re.search(r"(?ms)^vars:\n(.*?)(?=^\S|\Z)", text)
        var = dict(re.findall(r"(?m)^  ([\w-]+): ['\"]?([^'\"\n]+)", block.group(1))) if block else {}
        def expand(n):
            return re.sub(r"\$\{\{vars\.([\w-]+)\}\}", lambda v: var.get(v.group(1), v.group(0)), n.strip("'\""))
        m = re.search(r"(?m)^package:\n(?:  .*\n)*?  name: (\S+)", text)
        if m:
            names.add(m.group(1))
        sub = re.search(r"(?ms)^subpackages:\n(.*?)(?=^\S|\Z)", text)
        for n in re.findall(r"(?m)^  - name: (\S+)", sub.group(1) if sub else ""):
            n = expand(n)
            if "${{" not in n:  # range subpackages
                names.add(n)
    return names


class WolfiIndex:
    """Optional lookup of package names in the Wolfi APKINDEX (via pkg-check).

    Names published by this repository are tracked separately, so a
    dependency that only exists here can be labelled as such.
    """

    def __init__(self, enabled, arch="x86_64"):
        self.names = None
        self.community = set()
        self.unversioned_so = {}  # package -> sonames without a version (libdb-5.3.so)
        if not enabled:
            return
        spec = importlib.util.spec_from_file_location("pkg_check", PKG_CHECK)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        try:
            self.names = self._load(mod, mod.WOLFI_INDEX.format(arch=arch))
        except Exception as exc:
            print("warning: cannot read the Wolfi index ({}); names are not checked".format(exc), file=sys.stderr)
            return
        try:
            self.community = self._load(mod, COMMUNITY_INDEX.format(arch=arch))
        except Exception as exc:  # the community index is optional
            print("warning: cannot read {}: {}".format(COMMUNITY_INDEX.format(arch=arch), exc), file=sys.stderr)
        # recipes of this repository not published yet
        self.community |= recipe_names(os.path.join(HERE, "..", "..", "packages"))

    def _load(self, mod, url):
        names = set()
        for e in mod.parse_apkindex(mod.fetch(url, True)):
            names.add(e.get("P"))
            for prov in e.get("p", "").split():
                names.add(re.split(r"[=<>~]", prov, maxsplit=1)[0])
                so = re.match(r"^so:(lib[^=]*\.so)=", prov)
                if so and so.group(1) not in self.unversioned_so.get(e.get("P"), []):
                    self.unversioned_so.setdefault(e.get("P"), []).append(so.group(1))
        return names

    def has(self, name):
        if self.names is None:
            return None
        return name in self.names or name in self.community

    def community_only(self, name):
        return self.names is not None and name not in self.names and name in self.community


# ==========================================================================
# Debian file parsers
# ==========================================================================

def parse_deb822(text):
    """Parse deb822 paragraphs into a list of dicts (field names lowercased)."""
    paras, cur, last = [], {}, None
    for raw in text.splitlines():
        if raw.startswith("#"):
            continue
        if not raw.strip():
            if cur:
                paras.append(cur)
            cur, last = {}, None
            continue
        if raw[0] in " \t" and last:
            cur[last] += "\n" + raw[1:]
            continue
        key, _, val = raw.partition(":")
        last = key.strip().lower()
        cur[last] = val.strip()
    if cur:
        paras.append(cur)
    return paras


def parse_relations(value):
    """'a (>= 1) | b, c [amd64]' -> [['a', 'b'], ['c']] (names only)."""
    out = []
    if not value:
        return out
    for group in re.split(r",\s*", value.replace("\n", " ")):
        group = group.strip()
        if not group:
            continue
        alts = []
        for alt in group.split("|"):
            # Build profiles: <a b> <c> means (a and b) or c. With no profile
            # enabled (a normal build), "!x" holds and "x" does not.
            formulas = re.findall(r"<([^>]*)>", alt)
            if formulas and not any(all(t.startswith("!") for t in f.split()) for f in formulas):
                continue
            alt = re.sub(r"\(.*?\)|\[.*?\]|<.*?>", "", alt).strip()
            if not alt.startswith("${"):
                alt = alt.split(":", 1)[0]      # :any, :native
            if alt:
                alts.append(alt)
        if alts:
            out.append(alts)
    return out


def parse_changelog(text):
    m = re.match(r"^(\S+) \(([^)]+)\) ([^;]+);", text)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def debian_upstream_version(version):
    v = version.split(":", 1)[-1]
    if "-" in v:
        v = v.rsplit("-", 1)[0]
    v = re.split(r"[+~](?:dfsg|ds|repack)", v)[0]
    # apk versions: 1.2+git20170224 -> 1.2_git20170224, 1.2~rc1 -> 1.2_rc1
    v = re.sub(r"[+~.]?git[.+~]?(\d{8})\b.*$", r"_git\1", v)
    v = re.sub(r"\+nmu(\d+)$", r"_p\1", v)  # non-maintainer uploads of native packages
    return re.sub(r"~(alpha|beta|pre|rc)", r"_\1", v)


SPDX_MAP = {
    "gpl-1": "GPL-1.0-only", "gpl-1+": "GPL-1.0-or-later",
    "gpl-2": "GPL-2.0-only", "gpl-2+": "GPL-2.0-or-later",
    "gpl-3": "GPL-3.0-only", "gpl-3+": "GPL-3.0-or-later",
    "lgpl-2": "LGPL-2.0-only", "lgpl-2+": "LGPL-2.0-or-later",
    "lgpl-2.1": "LGPL-2.1-only", "lgpl-2.1+": "LGPL-2.1-or-later",
    "lgpl-3": "LGPL-3.0-only", "lgpl-3+": "LGPL-3.0-or-later",
    "agpl-3": "AGPL-3.0-only", "agpl-3+": "AGPL-3.0-or-later",
    "expat": "MIT", "mit": "MIT",
    "bsd-2-clause": "BSD-2-Clause", "bsd-3-clause": "BSD-3-Clause",
    "apache-2.0": "Apache-2.0", "apache-2": "Apache-2.0",
    "mpl-1.1": "MPL-1.1", "mpl-2.0": "MPL-2.0",
    "isc": "ISC", "zlib": "Zlib", "artistic": "Artistic-1.0-Perl",
    "public-domain": "LicenseRef-public-domain", "cc0-1.0": "CC0-1.0",
    "wtfpl": "WTFPL", "bsl-1.0": "BSL-1.0", "unlicense": "Unlicense",
}


def to_spdx(expr):
    """Convert a DEP-5 license expression to SPDX (best effort)."""
    tokens = re.split(r"(\s+(?:and|or|with)\s+|[(),])", expr.strip(), flags=re.I)
    out = []
    for tok in tokens:
        low = tok.strip().lower()
        if low in ("and", "or", "with"):
            out.append(" {} ".format(low.upper()))
        elif low in ("(", ")", ","):
            out.append(low)
        elif low:
            # "GPL-2.0+" style: the deprecated SPDX "+" suffix
            norm = re.sub(r"^((?:a|l)?gpl-\d)\.0(\+?)$", r"\1\2", low)
            out.append(SPDX_MAP.get(low) or SPDX_MAP.get(norm, tok.strip()))
    return "".join(out)


def guess_license(text):
    """SPDX id from the license notice of a free-form debian/copyright, or None."""
    t = re.sub(r"\s+", " ", text or "")
    later = re.search(r"(at your option\)? any later version|or later)", t, re.I)
    for name, spdx in (("(?:Lesser|Library) General Public License", "LGPL"),
                       ("(?<!Lesser )(?<!Library )General Public License", "GPL")):
        if re.search(r"GNU (Affero )?" + name, t):
            v = re.search(name + r".{0,120}?version (\d(?:\.\d)?)", t)
            if not v:
                continue
            ver = v.group(1) if "." in v.group(1) else v.group(1) + ".0"
            if spdx == "LGPL" and ver == "2.0":
                spdx_id = "LGPL-2.0"
            else:
                spdx_id = "{}-{}".format(spdx, ver)
            return spdx_id + ("-or-later" if later else "-only")
    if "Permission is hereby granted, free of charge" in t:
        return "MIT"
    if "Redistribution and use in source and binary forms" in t:
        return "BSD-3-Clause" if re.search(r"Neither the name|endorse or promote", t) else "BSD-2-Clause"
    if re.search(r"Apache License,? Version 2\.0", t):
        return "Apache-2.0"
    return None


def parse_copyright(text):
    """Return [(spdx, [paths])] for non-debian/* paragraphs, main first."""
    if not text or "Format:" not in text.split("\n", 1)[0] + text[:200]:
        lic = guess_license(text)
        return [(lic, ["*"])] if lic else []
    result = []
    for para in parse_deb822(text):
        if "files" not in para or "license" not in para:
            continue
        files = para["files"].split()
        if all(f.startswith("debian/") for f in files):
            continue
        lic = to_spdx(para["license"].split("\n", 1)[0])
        result.append((lic, files))
    result.sort(key=lambda r: 0 if r[1] == ["*"] else 1)
    return result


def files_excluded(text):
    """Paths listed in the Files-Excluded field of a DEP-5 debian/copyright."""
    if not text:
        return []
    paras = parse_deb822(text)
    return paras[0].get("files-excluded", "").split() if paras else []


# dpkg-architecture and friends, for a native build on Linux (amd64 stands
# for any architecture: conditionals only ask about the OS and cross builds).
BUILD_CONTEXT = {
    "DEB_HOST_ARCH_OS": "linux", "DEB_BUILD_ARCH_OS": "linux",
    "DEB_HOST_GNU_SYSTEM": "linux-gnu", "DEB_BUILD_GNU_SYSTEM": "linux-gnu",
    "DEB_HOST_GNU_TYPE": "x86_64-linux-gnu", "DEB_BUILD_GNU_TYPE": "x86_64-linux-gnu",
    "DEB_HOST_ARCH": "amd64", "DEB_BUILD_ARCH": "amd64", "DEB_HOST_MULTIARCH": "x86_64-linux-gnu",
    "DEB_BUILD_OPTIONS": "", "DEB_BUILD_PROFILES": "",
}


def make_functions(text):
    """$(findstring), $(filter), $(filter-out), $(strip) on already expanded text."""
    for _ in range(5):
        m = re.search(r"\$\((findstring|filter|filter-out|strip)\s+([^()$]*)\)", text)
        if not m:
            break
        fn, args = m.group(1), m.group(2)
        if fn == "strip":
            out = " ".join(args.split())
        else:
            pat, _, words = args.partition(",")
            if fn == "findstring":
                out = pat if pat in words else ""
            else:
                pats = [re.escape(p).replace("%", ".*") for p in pat.split()]
                keep = [w for w in words.split() if any(re.fullmatch(p, w) for p in pats)]
                out = " ".join(keep if fn == "filter" else [w for w in words.split() if w not in keep])
        text = text[:m.start()] + out + text[m.end():]
    return text


# Variables GNU make defines by itself.
MAKE_DEFAULTS = {"RM": "rm -f", "MAKE": "make", "CC": "cc", "CXX": "g++", "INSTALL": "install"}


class Rules:
    """Minimal debian/rules (Makefile) model: variables, dh line, overrides."""

    def __init__(self, text):
        self.vars = {}
        self.exports = []
        self.targets = {}
        self.target_vars = {}
        self.dh_args = ""
        lines = self._join_continuations(text.splitlines())
        target = None
        active = []  # make conditionals: is each enclosing branch taken?
        for line in lines:
            cond = re.match(r"^\s*(ifeq|ifneq|ifdef|ifndef|else|endif)\b\s*(.*)$", line)
            if cond:
                kw, arg = cond.groups()
                if kw == "endif":
                    active and active.pop()
                elif kw == "else":
                    if active:
                        taken = not active[-1] and not getattr(self, "_done", {}).get(len(active))
                        inner = re.match(r"^(ifeq|ifneq|ifdef|ifndef)\s*(.*)$", arg)
                        if inner and taken:
                            taken = self._condition(inner.group(1), inner.group(2))
                        self._done = dict(getattr(self, "_done", {}), **{str(len(active)): False})
                        active[-1] = taken if all(active[:-1]) else False
                else:
                    active.append(self._condition(kw, arg) if all(active) else False)
                continue  # conditionals do not end a recipe
            if not all(active):
                continue
            if line.startswith("\t") and target is not None:
                for t in target:
                    self.targets[t].append(line[1:])
                continue
            line = line.lstrip("\t")  # indented inside a conditional, outside any rule
            if not line.strip() or line.lstrip().startswith("#"):
                continue  # blank lines and comments do not end a recipe
            target = None
            m = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*([:?+]?=)\s*(.*)$", line)
            if m:
                name, op, val = m.groups()
                if line.startswith("export") and name not in self.exports:
                    self.exports.append(name)
                if op == "+=":
                    self.vars[name] = (self.vars.get(name, "") + " " + val).strip()
                elif op != "?=" or name not in self.vars:
                    self.vars[name] = val.strip()
                continue
            m = re.match(r"^([^:=\s][^:=]*?)\s*:(?!=)\s*(.*)$", line)
            if m:
                names = m.group(1).split()
                tv = re.match(r"^(?:export\s+)?([A-Za-z_]\w*)\s*[:?+]?=\s*(.*)$", m.group(2))
                if tv:
                    # target-specific variable: "override_dh_x: VAR=value"
                    for t in names:
                        self.target_vars.setdefault(t, {})[tv.group(1)] = tv.group(2).strip()
                    continue
                target = names
                for t in names:
                    self.targets[t] = []
        self._merge_arch_indep()
        for recipe in self.targets.get("%", []):
            m = re.search(r"\bdh\s+\$@(.*)$", recipe)
            if m:
                self.dh_args = m.group(1).strip()

    def _merge_arch_indep(self):
        """One melange build makes the arch and the indep packages: override_dh_x-arch and
        override_dh_x-indep become override_dh_x, with their target-specific variables
        joined (arch first, so later cmake/configure flags from indep win)."""
        groups = {}
        for t in self.targets:
            m = re.match(r"^((?:override|execute_before|execute_after)_dh_\w+)-(arch|indep)$", t)
            if m:
                groups.setdefault(m.group(1), []).append(t)
        for t in list(self.targets):
            if t not in sum(groups.values(), []):
                self.targets[t] = self._target_vars(t, self.targets[t], self.target_vars.get(t, {}))
        for base, ts in groups.items():
            ts.sort()  # arch, indep
            if base in self.targets:
                continue
            tvars, recipe = {}, []
            for t in ts:
                for k, v in self.target_vars.get(t, {}).items():
                    tvars[k] = v if tvars.get(k, v) == v else tvars[k] + " " + v
                for line in self.targets[t]:
                    if line not in recipe:
                        recipe.append(line)
            for t in ts:
                del self.targets[t]
            self.targets[base] = self._target_vars(base, recipe, tvars)

    def _target_vars(self, target, recipe, tvars):
        def sub(line):
            for k, v in tvars.items():
                line = line.replace("$({})".format(k), v).replace("${{{}}}".format(k), v)
            return line
        return [sub(l) for l in recipe]

    def _condition(self, kw, arg):
        """Evaluate ifeq/ifneq/ifdef/ifndef for a native Debian build on Linux."""
        if kw in ("ifdef", "ifndef"):
            defined = bool(self.vars.get(arg.strip()) or BUILD_CONTEXT.get(arg.strip()))
            return defined if kw == "ifdef" else not defined
        arg = arg.strip()
        if arg.startswith("(") and arg.endswith(")"):
            # split at the comma outside $(...)
            depth, cut = 0, None
            for i, ch in enumerate(arg[1:-1]):
                depth += {"(": 1, ")": -1}.get(ch, 0)
                if ch == "," and depth == 0:
                    cut = i
                    break
            if cut is None:
                return True
            parts = (arg[1:-1][:cut], arg[1:-1][cut + 1:])
        else:
            m = re.match(r"^[\"'](.*)[\"']\s+[\"'](.*)[\"']$", arg)
            if not m:
                return True
            parts = m.groups()
        a, b = (make_functions(self.expand(x, context=True)).strip() for x in parts)
        return (a == b) if kw == "ifeq" else (a != b)

    @staticmethod
    def _join_continuations(lines):
        out, buf = [], ""
        for line in lines:
            if line.endswith("\\"):
                buf += line[:-1] + " "
                continue
            out.append(buf + line)
            buf = ""
        if buf:
            out.append(buf)
        return out

    def expand(self, value, depth=0, context=False):
        if depth > 10:
            return value
        def repl(m):
            name = m.group(1) or m.group(2)
            default = BUILD_CONTEXT.get(name, m.group(0)) if context else m.group(0)
            return self.expand(self.vars.get(name, MAKE_DEFAULTS.get(name, default)), depth + 1, context)
        return re.sub(r"\$\((\w+)\)|\$\{(\w+)\}", repl, value)

    def buildsystem(self):
        m = re.search(r"--buildsystem[= ](\S+)", self.dh_args)
        return m.group(1) if m else None

    def dh_with(self):
        return re.findall(r"--with[= ](\S+)", self.dh_args)

    def overrides(self):
        return {t: r for t, r in self.targets.items() if t.startswith(("override_", "execute_"))}

    def configure_opts(self):
        """Arguments passed after '--' to dh_auto_configure, if any."""
        for recipe in self.targets.get("override_dh_auto_configure", []):
            if re.search(r"\s(-B\s*|--builddir(?:ectory)?[= ])\S*udeb", recipe):
                continue  # the debian-installer build
            m = re.search(r"dh_auto_configure\b.*?\s--\s+(.*)$", recipe)
            if m:
                return self.expand(m.group(1)).split()
        return []

    def template_substitutions(self):
        """Find 'sed -e s/#X#/$(VAR)/ debian/foo.in > debian/foo' recipes.

        Returns {output_name: (input_name, {placeholder: VAR})}.
        """
        found = {}
        for recipe_lines in self.targets.values():
            for line in recipe_lines:
                if "sed" not in line or ".in" not in line:
                    continue
                m = re.search(r"(\S+\.in)\s*>\s*(\S+)", line)
                if not m:
                    continue
                subs = {ph: var for _sep, ph, var in
                        re.findall(r"s([/|@,])(.+?)\1\$\((\w+)\)\1", line)}
                if not subs:
                    continue  # literal values: generate_from_in() makes the file
                found[os.path.basename(m.group(2))] = (os.path.basename(m.group(1)), subs)
        return found


def install_entries(text, keep_src=False):
    """(source, destination dir, new name or None) for each line of a
    debian/*.install file, including dh-exec's "src => dest" renames."""
    for line in (text or "").splitlines():
        if line.lstrip().startswith("#"):
            continue  # comments, #!/usr/bin/dh-exec
        parts = line.split()
        if not parts:
            continue
        if parts[0].startswith("debian/tmp/"):
            parts[0] = parts[0][len("debian/tmp/"):]  # dh_install --sourcedir default
        src = parts[0] if keep_src else norm_path(parts[0])
        if "=>" in parts and parts.index("=>") == 1 and len(parts) == 3:
            dst = usr_merge(norm_path(parts[2]))
            yield src, os.path.dirname(dst), os.path.basename(dst)
        elif len(parts) == 1:
            yield src, usr_merge(os.path.dirname(norm_path(parts[0]))), None
        else:
            yield src, usr_merge(norm_path(parts[-1])), None


def norm_path(path):
    """Debian multiarch paths -> Wolfi paths (usr/lib/<triplet>/ -> usr/lib/)."""
    path = path.strip("/")
    path = re.sub(r"(^|/)lib/(?:\*(?=/)|\$[({]DEB_HOST_MULTIARCH[)}]|[a-z0-9_]+-linux-gnu[a-z]*)(/|$)",
                  r"\1lib\2", path).rstrip("/")
    # Perl modules: Debian's vendor directories are Wolfi's vendor_perl, and
    # Wolfi's man pages of modules end in .3 (Debian: .3pm)
    path = re.sub(r"^usr/share/perl5(/|$)", r"usr/share/perl5/vendor_perl\1", path)
    path = re.sub(r"^usr/lib/perl5/[\d.]+(/|$)", r"usr/lib/perl5/vendor_perl\1", path)
    path = re.sub(r"^(usr/share/man/man3/.*)\.3pm$", r"\1.3", path)
    return path


def usr_merge(path):
    """Installation paths on Wolfi: usr-merged, with sbin merged into bin."""
    return re.sub(r"^(?:usr/)?s?bin(/|$)", r"usr/bin\1", re.sub(r"^lib(/|$)", r"usr/lib\1", path))


def shell_path(prefix, rel):
    """Quote prefix, leave globs in rel unquoted so the shell expands them."""
    if re.search(r"[*?\[]", rel):
        return '"{}"/{}'.format(prefix, rel)
    return '"{}/{}"'.format(prefix, rel)


# ==========================================================================
# Source acquisition
# ==========================================================================

def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def release_monitoring_id(name, version):
    """The release-monitoring.org project named `name` that knows `version`."""
    try:
        data = json.loads(http_get("https://release-monitoring.org/api/v2/projects/?name="
                                   + urllib.parse.quote(name)))
    except Exception:
        return None
    items = [p for p in data.get("items", []) if version in p.get("versions", [])]
    return items[0]["id"] if len(items) == 1 else None


def debian_providers(name):
    """Packages that provide the Debian virtual package `name` (packages.debian.org)."""
    try:
        html = http_get("https://packages.debian.org/sid/" + urllib.parse.quote(name)).decode("utf-8", "replace")
    except Exception:
        return []
    m = re.search(r"<h2>Packages providing [^<]*</h2>(.*?)</dl>", html, re.S)
    return re.findall(r'<dt><a href="/sid/([^"/]+)">', m.group(1)) if m else []


def is_archive(data):
    """gzip, xz, bzip2, zstd, zip or tar data (not an HTML error page)."""
    return data[:2] == b"\x1f\x8b" or data[:6] == b"\xfd7zXZ\x00" or data[:3] == b"BZh" \
        or data[:4] in (b"\x28\xb5\x2f\xfd", b"PK\x03\x04") or data[257:262] == b"ustar"


def url_exists(url, tries=2):
    for _ in range(tries):
        try:
            return is_archive(http_get(url))
        except urllib.error.HTTPError:
            return False
        except Exception:
            continue  # connection reset and the like: retry
    return False


def binary_to_source(binary):
    """Source package of a Debian binary package (unstable), or None."""
    try:
        page = http_get("https://packages.debian.org/sid/{}".format(binary)).decode("utf-8", "replace")
    except Exception:
        return None
    m = re.search(r'href="/source/sid/([a-z0-9][a-z0-9.+-]+)"', page)
    return m.group(1) if m else None


# Upstream files the converter reads (build tool detection, Python metadata).
UPSTREAM_FILES = ("configure.ac", "autogen.sh", "pyproject.toml", "setup.cfg", "setup.py")


def python_requirements(tree):
    """Runtime requirements declared by upstream (what dh_python3 puts in ${python3:Depends})."""
    def read(f):
        try:
            with open(os.path.join(tree, f), encoding="utf-8", errors="replace") as fh:
                return fh.read()
        except OSError:
            return None
    reqs = []
    text = read("pyproject.toml")
    if text:
        try:
            import tomllib
            reqs += tomllib.loads(text).get("project", {}).get("dependencies", [])
        except (ImportError, ValueError):
            pass
    text = read("setup.cfg")
    m = re.search(r"(?ms)^install_requires\s*=\s*\n?(.*?)(?=^\S|\Z)", text or "")
    if m:
        reqs += [l.strip() for l in m.group(1).splitlines() if l.strip() and not l.strip().startswith("#")]
    m = re.search(r"install_requires\s*=\s*\[([^\]]*)\]", read("setup.py") or "")
    if m:
        reqs += re.findall(r"[\"']([^\"']+)[\"']", m.group(1))
    names = []
    for req in reqs:
        req, _, marker = req.partition(";")
        if "extra" in marker:
            continue
        n = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", req)
        if n:
            n = re.sub(r"[._]+", "-", n.group(1)).lower()
            if n not in names:
                names.append(n)
    return names


DEBIAN_AREA = {}  # source package -> archive area (main, contrib, non-free)


def fetch_from_debian(spec, dest):
    """Download debian/ of a source package from sources.debian.org into dest.

    Returns (source_tree_dir, top-level file names, version).
    """
    name, _, version = spec.partition("=")
    info = json.loads(http_get("https://sources.debian.org/api/src/{}/".format(name)))
    if "versions" not in info:
        # a binary package name: find its source package
        source = binary_to_source(name)
        if source and source != name:
            print("note: {} is built from the source package {}".format(name, source), file=sys.stderr)
            name = source
            info = json.loads(http_get("https://sources.debian.org/api/src/{}/".format(name)))
    if "versions" not in info:
        raise SystemExit("error: '{}' not found on sources.debian.org".format(name))
    versions = info["versions"]
    entry = next((v for v in versions if v["version"] == version), None) if version else versions[0]
    if entry is None:
        raise SystemExit("error: version {} of {} not found".format(version, name))
    version, area = entry["version"], entry.get("area", "main")
    DEBIAN_AREA[name] = area
    prefix = name[:4] if name.startswith("lib") else name[0]
    tree = os.path.join(dest, "{}-{}".format(name, version))

    def walk(path):
        listing = json.loads(http_get(SOURCES_API.format(name=name, version=version, path=path)))
        for item in listing.get("content", []):
            sub = (path + "/" if path else "") + item["name"]
            link = (item.get("stat") or {}).get("symlink_dest")
            if link:
                # sources.debian.org does not serve symlinks; recreate them
                os.symlink(link, os.path.join(tree, sub))
            elif item["type"] == "directory":
                os.makedirs(os.path.join(tree, sub), exist_ok=True)
                walk(sub)
            else:
                data = http_get(SOURCES_RAW.format(area=area, prefix=prefix, name=name,
                                                   version=version, path=sub))
                with open(os.path.join(tree, sub), "wb") as fh:
                    fh.write(data)

    os.makedirs(os.path.join(tree, "debian"), exist_ok=True)
    top = json.loads(http_get("https://sources.debian.org/api/src/{}/{}/".format(name, version)))
    top_names = [c["name"] for c in top.get("content", [])]
    walk("debian")
    egg = next((n for n in top_names if n.endswith(".egg-info")), None)
    if egg:
        # setuptools metadata in the sdist: top_level.txt names the importable modules
        try:
            data = http_get(SOURCES_RAW.format(area=area, prefix=prefix, name=name, version=version,
                                               path=egg + "/top_level.txt"))
            os.makedirs(os.path.join(tree, egg), exist_ok=True)
            with open(os.path.join(tree, egg, "top_level.txt"), "wb") as fh:
                fh.write(data)
        except Exception:
            pass
    for f in UPSTREAM_FILES:
        if f in top_names:
            with open(os.path.join(tree, f), "wb") as fh:
                fh.write(http_get(SOURCES_RAW.format(area=area, prefix=prefix, name=name,
                                                     version=version, path=f)))
    return tree, top_names, version


# ==========================================================================
# Maintainer scripts and debconf
# ==========================================================================

# Debian maintainer script -> [(melange script, positional args emulating dpkg)]
SCRIPT_MAP = {
    "preinst": [("pre-install", 'install'), ("pre-upgrade", 'upgrade "$2"')],
    "postinst": [("post-install", "configure"), ("post-upgrade", 'configure "$2"')],
    "prerm": [("pre-deinstall", "remove")],
    "postrm": [("post-deinstall", "remove")],
}

DEBIAN_ONLY_TOOLS = ["py3compile", "py3clean"]

# Debian tools that maintainer scripts call, and the package that has them
# (Wolfi's dpkg; init-system-helpers and ucf from this repository).
SCRIPT_TOOLS = {
    "update-alternatives": "dpkg", "dpkg-maintscript-helper": "dpkg", "dpkg-divert": "dpkg",
    "dpkg-statoverride": "dpkg", "dpkg-trigger": "dpkg",
    "invoke-rc.d": "init-system-helpers", "update-rc.d": "init-system-helpers",
    "deb-systemd-helper": "init-system-helpers", "deb-systemd-invoke": "init-system-helpers",
    "ucf": "ucf", "ucfr": "ucf", "ucfq": "ucf",
}

# A command word: at the start of a command, not part of a path or a name.
def command_re(tool):
    return r"(?:^|[;&|(`]|\bthen|\bdo|\belse|\bexec|\$\()\s*(?:/usr/s?bin/)?{}(?![\w.-])".format(re.escape(tool))


def env_name(pkg, question):
    """debconf question 'pkg/foo-bar' -> PKG_FOO_BAR."""
    short = question.split("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9]", "_", "{}_{}".format(pkg, short)).upper()


def parse_templates(text):
    templates = []
    for para in parse_deb822(text or ""):
        if "template" not in para:
            continue
        desc = para.get("_description") or para.get("description") or ""
        short, _, long_ = desc.partition("\n")
        templates.append({
            "name": para["template"],
            "type": para.get("type", "string"),
            "default": para.get("default", ""),
            "short": short.strip(),
            "long": "\n".join("" if l.strip() == "." else l for l in long_.splitlines()),
        })
    return templates


def render_conffile(pkg, templates):
    lines = ["# Configuration for {}.".format(pkg),
             "#",
             "# Converted from debconf templates by debian-to-melange. These values",
             "# replace the questions Debian asks at install time; edit them before",
             "# installing or upgrading the package to change the behaviour.",
             ""]
    for t in templates:
        if t["type"] not in ("boolean", "string", "select", "multiselect", "password"):
            continue
        lines.append("# " + t["short"])
        body = textwrap.dedent(t["long"]).strip("\n")
        for para in re.split(r"\n\s*\n", body):
            wrapped = textwrap.fill(" ".join(para.split()), width=72) if para.strip() else ""
            lines += ["# " + l if l else "#" for l in wrapped.splitlines()] + ["#"]
        if t["type"] == "boolean":
            lines.append("# Values: true | false")
        lines.append('{}="{}"'.format(env_name(pkg, t["name"]), t["default"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# commands in ported debian/rules recipes -> Wolfi build packages
RECIPE_TOOLS = {
    "pod2man": ["perl"], "pod2text": ["perl"], "perl": ["perl"],
    "dpkg-parsechangelog": ["dpkg-dev"], "dpkg-architecture": ["dpkg-dev"], "dpkg-vendor": ["dpkg-dev"],
    "xsltproc": ["libxslt"], "help2man": ["help2man"], "python3": ["python3"],
}


# Debian's Essential packages, present on every autopkgtest testbed (GNU tools, dpkg)
ESSENTIAL = ["bash", "coreutils", "diffutils", "dpkg", "findutils", "grep", "sed"]

def alternatives(text):
    """update-alternatives --install calls of a postinst: [(link, path, [(slave link, slave path)])],
    the highest priority per link, as dpkg's automatic mode picks."""
    best = {}
    body = re.sub(r"\\\n", " ", text)
    for m in re.finditer(r"update-alternatives\s+(?:--quiet\s+)?--install\s+(\S+)\s+\S+\s+(\S+)\s+(\S+)((?:\s+--slave\s+\S+\s+\S+\s+\S+)*)", body):
        link, path, prio = m.group(1), m.group(2), m.group(3)
        if not link.startswith("/") or not path.startswith("/"):
            continue  # set from shell variables
        prio = int(prio) if prio.isdigit() else -1
        slaves = [(s[0], s[2]) for s in re.findall(r"--slave\s+(\S+)\s+(\S+)\s+(\S+)", m.group(4))
                  if s[0].startswith("/") and s[2].startswith("/")]
        if link not in best or prio > best[link][0]:
            best[link] = (prio, path, slaves)
    return [(link, path, slaves) for link, (_p, path, slaves) in best.items()]


def alternatives_step(alts, root):
    """Ship the links update-alternatives would make: apko does not run maintainer scripts."""
    cmds = ['alt() {',
            '  for s in "" .gz; do',
            '    t="${2%.gz}$s" l="${1%.gz}$s"',
            '    [ -e "{0}$t" ] && [ ! -e "{0}$l" ] || continue'.format(root),
            '    mkdir -p "$(dirname "{0}$l")" && ln -s "$t" "{0}$l" && return'.format(root),
            '  done',
            '}']
    for link, path, slaves in alts:
        for l, p in [(link, path)] + slaves:
            cmds.append("alt /{} /{}".format(usr_merge(l.lstrip("/")), usr_merge(p.lstrip("/"))))
    return {"name": "Alternatives (links update-alternatives makes)", "runs": "\n".join(cmds) + "\n"}


# Debian names of Essential packages, registered in the test's dpkg database too
ESSENTIAL_ALIASES = {"perl-base": "perl", "libc6": "glibc", "libc-bin": "glibc"}


def dpkg_database_step(aliases, deb_pkg):
    """A Debian testbed has a dpkg database (dpkg-query -L/-W/-s, --control-path): register
    the installed apk packages in it, also under the Debian names of the test's dependencies,
    with the package's debconf templates from the source tree as dpkg installs them."""
    pairs = " ".join("{}={}".format(d, w) for d, w in sorted(aliases.items()) if d != w)
    return {"name": "dpkg database (as on a Debian testbed)", "runs": (
        "db=/var/lib/dpkg\n"
        'mkdir -p "$db/info" && touch "$db/status"\n'
        "awk -v db=\"$db\" -v aliases='{0}' '\n"
        "  BEGIN {{ n = split(aliases, a, \" \"); for (i = 1; i <= n; i++) {{ split(a[i], kv, \"=\"); alias[kv[2]] = alias[kv[2]] \" \" kv[1] }} }}\n"
        "  function add(   m, j, f) {{\n"
        "    m = split(pkg alias[pkg], names, \" \")\n"
        "    for (j = 1; j <= m; j++) {{\n"
        "      f = db \"/info/\" names[j] \".list\"\n"
        "      printf \"%s\", files > f; close(f)\n"
        "      gsub(/_/, \"~\", ver)\n"
        "      printf \"Package: %s\\nStatus: install ok installed\\nPriority: optional\\nArchitecture: all\\nVersion: %s\\nMaintainer: Wolfi\\nDescription: %s (apk package %s)\\n\\n\", names[j], ver, names[j], pkg >> (db \"/status\")\n"
        "    }}\n"
        "    pkg = \"\"\n"
        "  }}\n"
        "  /^P:/ {{ pkg = substr($0, 3); files = \"\"; dir = \"\" }}\n"
        "  /^V:/ {{ ver = substr($0, 3) }}\n"
        "  /^F:/ {{ dir = substr($0, 3); files = files \"/\" dir \"\\n\" }}\n"
        "  /^R:/ {{ files = files (dir == \"\" ? \"\" : \"/\" dir) \"/\" substr($0, 3) \"\\n\" }}\n"
        "  /^$/ && pkg != \"\" {{ add() }}\n"
        "  END {{ if (pkg != \"\") add() }}\n"
        "' /lib/apk/db/installed\n"
        "for t in debian/{1}.templates debian/templates; do\n"
        "  # po-debconf's translatable fields (_Description, __Choices) in the C locale\n"
        "  [ -f \"$t\" ] && sed '/^#/d; s/^__*//' \"$t\" > \"$db/info/{1}.templates\" && break\n"
        "done\n").format(pairs, deb_pkg)}


SCRIPT_DEPS = {}  # script label -> packages its commands come from
KEEP_DEBCONF = set()  # packages whose maintainer scripts keep using debconf


def convert_script(text, kind, pkg, templates, conffile, notes):
    """Rewrite a Debian maintainer script body for apk."""
    names = {t["name"]: env_name(pkg, t["name"]) for t in templates}
    body = []
    uses_debconf = False
    for line in text.splitlines():
        s = line.strip()
        if s == "#DEBHELPER#":
            continue
        if pkg in KEEP_DEBCONF:
            pass  # debconf itself, or a package that depends on it: debconf runs as in Debian
        elif re.match(r"^\.\s+/usr/share/debconf/confmodule\s*$", s):
            uses_debconf = True
            body.append("# debconf replaced by {}".format(conffile))
            body.append('[ -r "{0}" ] && . "{0}"'.format(conffile))
            continue
        if pkg not in KEEP_DEBCONF and re.match(r"^db_(stop|go|capb|title|version)\b", s):
            continue
        m = re.match(r"^(\s*)db_get\s+(\S+)(.*)$", line)
        if pkg not in KEEP_DEBCONF and m and m.group(2) in names:
            indent, q = m.group(1), m.group(2)
            t = next(t for t in templates if t["name"] == q)
            body.append('{}RET="${{{}:-{}}}"'.format(indent, names[q], t["default"]))
            continue
        if pkg not in KEEP_DEBCONF and re.match(r"^\s*db_\w+", line):
            notes.append("{}: debconf call not converted: {}".format(kind, s))
            body.append("# {}: {}".format(TODO, s))
            continue
        code = line.split("#", 1)[0]
        for tool in DEBIAN_ONLY_TOOLS:
            if re.search(command_re(tool), code):
                notes.append("{}: uses Debian-only tool '{}'".format(kind, tool))
                body.append("# {}: '{}' does not exist on Wolfi".format(TODO, tool))
                break
        for tool, pkg_ in SCRIPT_TOOLS.items():
            if re.search(command_re(tool), code) or re.search(r"-x\s+\"?/usr/s?bin/{}\b".format(re.escape(tool)), code):
                SCRIPT_DEPS.setdefault(kind, set()).add(pkg_)
        body.append(line)
    if body and body[0].startswith("#!"):
        body = body[1:]
    return "\n".join(body).strip("\n"), uses_debconf


def wrap_script(kind, body, args):
    """Run a Debian maintainer script body in a subshell with dpkg-style args."""
    fn = "debian_" + re.sub(r"[^A-Za-z0-9_]", "_", kind)
    return "\n".join([
        "#!/bin/sh",
        "# Converted from debian/{} by debian-to-melange.".format(kind),
        "# apk passes different arguments than dpkg, so the original script runs",
        "# in a subshell with the arguments dpkg would have used.",
        "{}() (".format(fn),
        body,
        ")",
        "{} {}".format(fn, args),
        "",
    ])


# ==========================================================================
# YAML emitter (melange style, no dependency on PyYAML)
# ==========================================================================

class C:
    """A value with a trailing comment."""

    def __init__(self, value, comment):
        self.value, self.comment = value, comment


class Comment:
    """A standalone comment line inside a mapping or list."""

    def __init__(self, text):
        self.text = text


_PLAIN = re.compile(r"^[A-Za-z0-9_./${}+-][A-Za-z0-9_ ./${}()+=,:@-]*$")


def scalar(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    s = str(v)
    if (not s or not _PLAIN.match(s) or s != s.strip() or ": " in s or s.endswith(":")
            or re.match(r"^[\d.]+$", s) or s.lower() in ("yes", "no", "true", "false", "null", "on", "off")):
        return "'" + s.replace("'", "''") + "'"
    return s


def emit(node, indent=0):
    pad = " " * indent
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, Comment):
                out.append(pad + "# " + v.text)
                continue
            comment = ""
            if isinstance(v, C):
                comment, v = "  # " + v.comment, v.value
            if isinstance(v, str) and "\n" in v:
                out.append("{}{}: |{}".format(pad, k, comment))
                out += [(pad + "  " + l) if l else "" for l in v.rstrip("\n").split("\n")]
            elif isinstance(v, (dict, list)):
                if not v:
                    out.append("{}{}: {}{}".format(pad, k, "{}" if isinstance(v, dict) else "[]", comment))
                else:
                    out.append("{}{}:{}".format(pad, k, comment))
                    out += emit(v, indent + 2)
            else:
                out.append("{}{}: {}{}".format(pad, k, scalar(v), comment))
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, Comment):
                out.append(pad + "# " + item.text)
                continue
            comment = ""
            if isinstance(item, C):
                comment, item = "  # " + item.comment, item.value
            if isinstance(item, dict):
                sub = emit(item, indent + 2)
                first = sub[0].lstrip()
                out.append(pad + "- " + first + (comment if not first.startswith("#") else ""))
                out += sub[1:]
            else:
                out.append("{}- {}{}".format(pad, scalar(item), comment))
    return out


# ==========================================================================
# Conversion
# ==========================================================================

# Upstream license files installed in /usr/share/licenses/<name>.
LICENSE_FILES = ("COPYING", "COPYING.LIB", "COPYING.LESSER", "LICENSE", "LICENSE.txt",
                 "LICENSE.md", "LICENCE", "NOTICE")


def dh_compat(source, read):
    """debhelper compatibility level, from debhelper-compat or debian/compat."""
    m = re.search(r"debhelper-compat\s*\(\s*=\s*(\d+)", source.get("build-depends", ""))
    if m:
        return int(m.group(1))
    text = (read("compat") or "").strip()
    return int(text) if text.isdigit() else 0


BUILDSYSTEM_FILES = [
    ("meson.build", "meson"),
    ("CMakeLists.txt", "cmake"),
    ("configure.ac", "autoconf"),
    ("configure", "autoconf"),
    ("autogen.sh", "autoconf"),
    ("pyproject.toml", "pybuild"),
    ("setup.py", "pybuild"),
    ("go.mod", "golang"),
    ("Cargo.toml", "cargo"),
    ("Makefile.PL", "perl_makemaker"),
    ("Makefile", "makefile"),
]

BUILD_PIPELINES = {
    "cmake": ["cmake/configure", "cmake/build", "cmake/install"],
    "meson": ["meson/configure", "meson/compile", "meson/install"],
    "autoconf": ["autoconf/configure", "autoconf/make", "autoconf/make-install"],
    "pybuild": ["py/pip-build-install"],
    "perl_makemaker": ["perl/make", "autoconf/make", "autoconf/make-install", "perl/cleanup"],
    "cargo": ["cargo/build"],
    "golang": ["go/build"],
}


class Converter:

    def __init__(self, tree, top_names, args, wolfi):
        self.tree = tree
        self.deb = os.path.join(tree, "debian")
        self.top = top_names if top_names is not None else self._listdir(tree)
        self.args = args
        self.wolfi = wolfi
        self.notes = []
        self.git_source = None  # (repository URL, tag prefix) from debian/watch
        self.aux = {}          # filename -> content (bytes or str) for <out>/<name>/
        self.install_excludes = {}  # Debian binary package (or "*") -> dh_install -X patterns
        self.rename = {}       # Debian binary package name -> melange package name
        self.upstream_installs = True  # does the build system install into destdir?

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _listdir(path):
        try:
            return sorted(os.listdir(path))
        except OSError:
            return []

    def read(self, rel):
        if rel in getattr(self, "generated", {}):
            return self.generated[rel]
        path = os.path.join(self.deb, rel)
        if os.path.isfile(path):
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read()
        return None

    def pkgfile(self, binary, suffix, main):
        """debian/<binary>.<suffix>, falling back to debian/<suffix> for the main package."""
        text = self.read("{}.{}".format(binary, suffix))
        if text is None and main:
            text = self.read(suffix)
        return text

    def patch_imports(self):
        """Third-party modules that lines added by debian/patches import."""
        series = self.read("patches/series") or ""
        mods = []
        for p in series.split():
            if p.startswith("#"):
                continue
            for m in re.finditer(r"(?m)^\+\s*(?:from\s+([A-Za-z_]\w*)[\w.]*\s+import|import\s+([A-Za-z_]\w*))",
                                 self.read(os.path.join("patches", p)) or ""):
                mod = m.group(1) or m.group(2)
                if mod in sys.stdlib_module_names or mod == getattr(self, "python_module", None) or mod in mods:
                    continue
                mods.append(mod)
        own = {n for n in self.top if not n.startswith(".")}
        return [m for m in mods if m not in own]

    def debian_file(self, path):
        """debian/<file> named by a packaging file: copied next to the recipe."""
        if not path.startswith("debian/"):
            return path
        rel = path[len("debian/"):]
        full = os.path.join(self.deb, rel)
        if not os.path.isfile(full):
            return path
        with open(full, "rb") as fh:
            self.aux[os.path.basename(rel)] = fh.read()
        return "{}/{}".format(self.recipe_dir, os.path.basename(rel))

    def todo(self, msg):
        self.notes.append(msg)
        return Comment("{}: {}".format(TODO, msg))

    @staticmethod
    def multiarch(line):
        """usr/lib/$(DEB_HOST_MULTIARCH) is usr/lib on Wolfi; the triplet elsewhere is the host's."""
        line = re.sub(r"(^|/|\s|=)(usr/lib)/\$[({]DEB_HOST_MULTIARCH[)}]", r"\1\2", line)
        return re.sub(r"\$[({]DEB_HOST_MULTIARCH[)}]", "${{host.triplet.gnu}}", line)

    SED_IN = re.compile(r"^sed\s+(?:-e\s+)?(['\"])((?:s(.).*?\3.*?\3[gi]*;?)+)\1\s+debian/(\S+\.in)\s*>\s*debian/(\S+)\s*$")

    def generate_from_in(self, rules):
        """sed 's/@X@/value/' debian/foo.in > debian/foo in debian/rules: make foo now,
        so maintainer scripts and *.links generated at build time are converted too."""
        self.generated = {}
        templated = rules.template_substitutions()  # those keep their variables as melange vars
        for recipe in rules.targets.values():
            for raw in recipe:
                m = self.SED_IN.match(rules.expand(raw.strip().lstrip("@-")))
                if not m or self.read(m.group(4)) is None or \
                        (m.group(5) in templated and re.search(r"(pre|post)(inst|rm)$", m.group(5))):
                    continue
                text = self.read(m.group(4))
                for expr in re.findall(r"s(.)(.*?)\1(.*?)\1[gi]*", m.group(2)):
                    sep, pat, repl = expr
                    repl = re.sub(r"(^|/)usr/lib/\$[({]DEB_HOST_MULTIARCH[)}]", r"\1usr/lib", repl)
                    if "$(" in pat or "$(" in repl:
                        break
                    text = text.replace(pat, repl)
                else:
                    self.generated[m.group(5)] = text

    def port_recipe(self, rules, lines, name, deb_pkg):
        """Translate a debian/rules recipe into shell for a melange step.

        Returns None when a line still depends on make or debhelper.
        """
        out = []
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            line = line.lstrip("@-")
            if re.match(r"^dh[_-]", line):
                auto = self.dh_auto_command(self.multiarch(rules.expand(line)))
                if auto == "":
                    continue
                if auto:
                    out.append(auto)
                    continue
                if self.dh_install_options(line):
                    continue  # applied by install_lines()
                if re.match(r"^dh_auto_|^dh_(install|link)\b", line):
                    return None
                continue  # debhelper bookkeeping (Built-Using, substvars...)
            line = rules.expand(line)
            m = self.SED_IN.match(line)
            if m and m.group(5) in getattr(self, "generated", {}):
                continue  # generated now, see generate_from_in()
            line = re.sub(r"`pwd`/|\$\(pwd\)/|\$\$\(pwd\)/", "", line)  # the source tree, like $(CURDIR)
            line = self.multiarch(line)
            for pkg, target in self.rename.items():
                if pkg != deb_pkg:
                    # files for another binary package: its melange output directory
                    line = re.sub(r"(?<![\w/])debian/{}(?=/|\s|$)".format(re.escape(pkg)),
                                  "${{{{targets.outdir}}}}/{}".format(target), line)
            for pkg in (deb_pkg, "tmp"):
                line = re.sub(r"(?<![\w/])debian/{}(?=\s|$)".format(re.escape(pkg)), "${{targets.destdir}}", line)
                line = re.sub(r"\$\(CURDIR\)/debian/{}(/|\b)".format(re.escape(pkg)), "${{targets.destdir}}/", line)
                line = re.sub(r"(?<![\w/])debian/{}/".format(re.escape(pkg)), "${{targets.destdir}}/", line)
            line = re.sub(r"target/\$\(DEB_HOST_RUST_TYPE\)/", "target/", line)
            line = line.replace("usr/share/doc/{}/".format(deb_pkg), "usr/share/doc/{}/".format(self.rename.get(deb_pkg, deb_pkg)))
            line = line.replace("$(CURDIR)/", "").replace("$(CURDIR)", ".")
            line = line.replace("$$", "$")  # make's escape for the shell's $
            line = line.replace("${{targets.destdir}}/usr/sbin/", "${{targets.destdir}}/usr/bin/")  # usr-merged
            def aux(m):
                rel = m.group(1)
                path = os.path.join(self.deb, rel)
                if not os.path.isfile(path):
                    return m.group(0)
                with open(path, "rb") as fh:
                    self.aux[os.path.basename(rel)] = fh.read()
                return "{}/{}".format(name, os.path.basename(rel))
            line = re.sub(r"(?<![\w/$.])debian/([\w.+-]+)", aux, line)
            line = line.replace("${{targets.destdir}}//", "${{targets.destdir}}/")
            if "$(" in line:
                return None
            words = line.split()
            if words and words[0] in ("install", "cp") and not re.search(r"\s-[a-zA-Z]*[dDt]\b", line) \
                    and words[-1].startswith("${{targets."):
                # dh_install made the package directories before this ran
                d = words[-1] if words[-1].endswith("/") else os.path.dirname(words[-1])
                if "mkdir -p {}".format(d) not in out:
                    out.append("mkdir -p {}".format(d))
            # debhelper has made debian/<pkg>/... and debian/ by now; a redirect here may not have it
            for target in re.findall(r"(?<![<>&\d])>>?\s*\"?([^\s\"'&|;]+)/[^\s/\"']+", line):
                if target not in ("/dev",) and "mkdir -p {}".format(target) not in out:
                    out.append("mkdir -p {}".format(target))
            out.append(line)
        return out

    def essential_used(self, binary):
        """Debian never declares Depends on its Essential packages; a Breaks or Conflicts on
        one (libapt-pkg: Breaks dpkg (<< 1.20.8)) shows the package works with it."""
        rels = parse_relations(binary.get("breaks")) + parse_relations(binary.get("conflicts"))
        return [C(e, "Essential in Debian; named in Breaks/Conflicts") for e in ESSENTIAL
                if any(alts[0] == e for alts in rels)]

    def unversioned_libs(self, binary, source):
        """${shlibs:Depends} for libraries with an unversioned soname (libdb-5.3.so):
        melange only derives so: dependencies for versioned ones."""
        if "${shlibs:Depends}" not in (binary.get("depends") or "") or binary.get("architecture") == "all":
            return []
        out = []
        for alts in parse_relations(source.get("build-depends")) + parse_relations(source.get("build-depends-arch")):
            for cand in dep_candidates(alts[0]):
                base = cand[:-len("-dev")] if cand.endswith("-dev") else None
                if base and self.wolfi.unversioned_so.get(base) and base not in out:
                    out.append(C(base, "{}: unversioned soname, no so: dependency".format(", ".join(self.wolfi.unversioned_so[base]))))
                    break
        return out

    def libexec_opts(self, bs, binaries):
        """Upstream CMake projects may put helpers in /usr/lib/<name> only on Debian (apt:
        if /etc/debian_version exists); the Debian packaging expects them there."""
        if bs != "cmake":
            return []
        names = {b["package"] for b in binaries} | {self.source_name}
        for b in binaries:
            for src, _dst, _r in install_entries(self.pkgfile(b["package"], "install", b["package"] == self.main_package) or ""):
                m = re.match(r"^usr/lib/([\w.+-]+)/", src)
                if m and m.group(1) in names:
                    return ["-DCMAKE_INSTALL_LIBEXECDIR=lib"]
        return []

    def dh_install_options(self, line):
        """dh_install with only package selection and -X excludes: record the excludes."""
        words = shlex.split(line) if line.startswith("dh_install ") or line == "dh_install" else None
        if words is None:
            return False
        pkgs, excludes, it = [], [], iter(words[1:])
        for w in it:
            if w in ("-a", "-i", "--arch", "--indep", "--remaining", "--remaining-packages",
                     "--list-missing", "--fail-missing") or w.startswith("--sourcedir"):
                continue
            m = re.match(r"^(?:-p|--package=)(.*)$", w)
            x = re.match(r"^(?:-X|--exclude=)(.*)$", w)
            if m:
                pkgs.append(m.group(1) or next(it, ""))
            elif x:
                excludes.append(x.group(1) or next(it, ""))
            else:
                return False  # files to install: not handled here
        for pkg in pkgs or ["*"]:
            self.install_excludes.setdefault(pkg, []).extend(excludes)
        return True

    def dh_auto_command(self, line):
        """dh_auto_build/dh_auto_install [-- ARGS] for make-based builds, as shell."""
        opts, sep, rest = line.partition(" -- ")  # debhelper options, then the build system's
        sub = re.search(r"\s(?:-D\s*|--sourcedir(?:ectory)?[= ])(\S+)", opts)
        if sub:
            opts = opts[:sub.start()] + opts[sub.end():]
        line = opts + sep + rest
        builddir = re.search(r"\s(?:-B\s*|--builddir(?:ectory)?[= ])(\S+)", opts)
        if builddir:
            if "udeb" in builddir.group(1):
                return ""  # the debian-installer build: left out with the udeb
            if getattr(self, "multi_builddir", False):
                return self.builddir_command(line, builddir.group(1))
            # the configure pipeline builds in the source tree
            line = line[:builddir.start()] + line[builddir.end():]
        line = re.sub(r"\s--destdir[= ]\S+", "", line)
        m = re.match(r"^dh_auto_(build|install)(?:\s+(?:-\S+\s*)*)?(?:--\s+(.*))?$", line)
        if m and getattr(self, "bs", None) == "pybuild":
            return self.PIPELINE_MARK
        if not m or getattr(self, "bs", None) not in ("makefile", "autoconf"):
            return None
        args = (" " + m.group(2).strip()) if m.group(2) else ""
        if sub:
            args = " -C " + sub.group(1) + args
        if m.group(1) == "build":
            return "make -j$(nproc)" + args
        return 'make install DESTDIR="${{targets.destdir}}"' + (" PREFIX=/usr" if self.bs == "makefile" else "") + args

    def builddir_command(self, line, builddir):
        """dh_auto_* for one of several build directories (variants of one source)."""
        m = re.match(r"^dh_auto_(configure|build|install|test)\b", line)
        bs = re.search(r"--buildsystem[= ](\S+)", line)
        bs = bs.group(1) if bs else self.bs
        if bs == "cmake+ninja":
            bs = "cmake"
        args = line.split(" -- ", 1)[1].strip() if " -- " in line else ""
        if not m or m.group(1) == "test":
            return "" if m else None
        step, dest = m.group(1), 'DESTDIR="${{targets.destdir}}"'
        if bs == "meson":
            return {"configure": "meson setup --prefix=/usr --libdir=lib --libexecdir=lib --buildtype=plain "
                                 "--wrap-mode=nodownload {} {}".format(builddir, args).strip(),
                    "build": "meson compile -C {}".format(builddir),
                    "install": "{} meson install -C {}".format(dest, builddir)}[step]
        if bs == "cmake":
            return {"configure": "cmake -S . -B {} -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_BUILD_TYPE=None {}".format(
                        builddir, args).strip(),
                    "build": "cmake --build {} -j$(nproc)".format(builddir),
                    "install": "{} cmake --install {}".format(dest, builddir)}[step]
        if bs in ("autoconf", "makefile"):
            return {"configure": "mkdir -p {0} && (cd {0} && ../configure --prefix=/usr --sysconfdir=/etc "
                                 "--localstatedir=/var {1})".format(builddir, args).strip(),
                    "build": "make -C {} -j$(nproc)".format(builddir),
                    "install": "make -C {} install {}".format(builddir, dest)}[step]
        return None

    # Stands for the build system's melange pipeline inside a ported override.
    PIPELINE_MARK = "\0pipeline"

    def override_steps(self, lines, label):
        """Steps for a ported override, with PIPELINE_MARK as the pipeline (once)."""
        steps, chunk = [], []
        for line in lines + [None]:
            if line is not None and line != self.PIPELINE_MARK:
                chunk.append(line)
                continue
            if chunk:
                steps.append({"name": label, "runs": "\n".join(chunk) + "\n"})
                chunk = []
            if line == self.PIPELINE_MARK and not self.pipeline_used:
                steps += [{"uses": st} for st in BUILD_PIPELINES[self.bs]]
                self.pipeline_used = True
        return steps

    SKIP_EXPORTS = {"PATH", "CARGO_HOME", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS",
                    "DH_VERBOSE", "PYBUILD_NAME", "GOCACHE", "GOPATH", "HOME"}

    def ported_exports(self, rules):
        env = {}
        for var in rules.exports:
            if var.startswith(("DEB_", "DH_", "PYBUILD_")) or var in self.SKIP_EXPORTS or var not in rules.vars:
                continue
            value = rules.expand(rules.vars[var]).replace("$(CURDIR)", "/home/build")
            value = value.replace("/usr/lib/jvm/default-java", "/usr/lib/jvm/default-jvm")  # Wolfi's default JDK
            if "$(" in value or "${" in value:
                continue
            env[var] = value
        return env

    def map_deps(self, relations, kind):
        out, comments = [], []
        for alts in relations:
            if len(alts) == 1 and isinstance(NAME_MAP.get(alts[0]), list):
                for m in NAME_MAP[alts[0]]:
                    if not any(o == m or (isinstance(o, C) and o.value == m) for o in out):
                        out.append(C(m, "Debian: " + alts[0]))
                continue
            if len(alts) == 1 and alts[0] in BUNDLES and self.wolfi.names is None:
                out.append(C(alts[0], "{}: a Debian bundle; list the programs used ({}...)".format(
                    TODO, ", ".join(BUNDLES[alts[0]][:3]))))
                self.notes.append("{} dependency '{}' is a Debian bundle of several programs".format(kind, alts[0]))
                continue
            if len(alts) == 1 and alts[0] in BUNDLES:
                # the members that exist in Wolfi
                members = [m for m in BUNDLES[alts[0]] if self.wolfi.has(m)]
                for m in members:
                    if not any(o == m or (isinstance(o, C) and o.value == m) for o in out):
                        label = "Wolfi Community Packages, " if self.wolfi.community_only(m) else ""
                        out.append(C(m, "{}Debian: {}".format(label, alts[0])))
                self.notes.append("{} dependency '{}' is a bundle; using {}".format(kind, alts[0], ", ".join(members) or "none"))
                continue
            chosen = None
            for alt in alts:
                if kind == "test" and alt in ("debconf", "ucf"):
                    pass  # an autopkgtest that exercises them gets the real ones
                elif alt in DROP or alt.startswith(DROP_PREFIXES) or alt.startswith("${"):
                    chosen = ""
                    break
                if alt in self.rename or alt in getattr(self, "sibling_provides", {}):
                    own = self.rename.get(alt) or self.sibling_provides[alt]
                    chosen = (own, own, True)
                    break
                cands = dep_candidates(alt)
                if alt.startswith("python3-") and cands[0].startswith("py3-") and self.wolfi.names is not None:
                    # Wolfi's py3-foo may be an empty package or follow the newest
                    # Python; py3-supported-foo works with any python3.
                    cands.insert(0, "py3-supported-" + cands[0][4:])
                for cand in cands:
                    found = self.wolfi.has(cand)
                    if found or (found is None and chosen is None):
                        chosen = (cand, alt, found)
                        if found:
                            break
                if chosen and chosen[2]:
                    break
            if (chosen is None or (chosen and chosen[2] is False)) and getattr(self.args, "download", False):
                # a Debian virtual package: try the packages that provide it
                for alt in alts:
                    for prov in debian_providers(alt):
                        cand = next((c for c in dep_candidates(prov) if self.wolfi.has(c)), None)
                        if cand:
                            chosen = (cand, alt, True)
                            break
                    if chosen and chosen[2]:
                        break
            if chosen is None:
                # Nothing matched in the index: keep the best guess, flagged.
                chosen = (dep_candidates(alts[0])[0], alts[0], False)
            if not chosen:
                continue
            cand, alt, found = chosen
            if any(o == cand or (isinstance(o, C) and o.value == cand) for o in out):
                continue
            mb = re.match(r"^python3-(.+)$", alt)
            if mb and self.wolfi.has("py{}-{}-bin".format(DEFAULT_PYTHON, mb.group(1))):
                # Debian's python3-foo ships the commands Wolfi splits into py3.X-foo-bin
                out.append(C("py{}-{}-bin".format(DEFAULT_PYTHON, mb.group(1)), "commands of Debian's " + alt))
            if found is not True and re.match(r"^libjs-", alt):
                self.notes.append("{} dependency '{}': Debian ships JavaScript libraries separately; "
                                  "Wolfi does not, keep the copy bundled upstream".format(kind, alt))
                continue
            if found is not True and re.match(r"^lib.+-java$", alt):
                self.notes.append("{} dependency '{}' is a Java library: Wolfi has no packaged jars, "
                                  "the build must fetch it from Maven Central".format(kind, alt))
                out.append(C(cand, "{}: Java library, fetch from Maven Central (Debian: {})".format(TODO, alt)))
                continue
            if found is False:
                # Left out, so that the environment resolves; optional features
                # are then disabled by the build, required ones fail there.
                self.notes.append("{} dependency '{}' (Debian '{}') not found in Wolfi; left out".format(kind, cand, alt))
                out.append(Comment("{}: {} is not in Wolfi (Debian: {}); left out".format(TODO, cand, alt)))
            elif self.wolfi.community_only(cand) and cand not in self.rename.values():
                out.append(C(cand, "Wolfi Community Packages" + ("" if cand == alt else " (Debian: {})".format(alt))))
            elif cand != alt:
                out.append(C(cand, "Debian: {}".format(alt)))
            else:
                out.append(cand)
        return out

    # -- main --------------------------------------------------------------

    def convert(self):
        a = self.args
        control_text = self.read("control")
        if control_text is None:
            raise SystemExit("error: no debian/control in {}".format(self.deb))
        paras = parse_deb822(control_text)
        source = paras[0]
        binaries = [p for p in paras[1:] if "package" in p]
        udebs = [p["package"] for p in binaries if p.get("package-type") == "udeb"]
        if udebs:
            # debian-installer packages have no meaning outside Debian
            self.notes.append("udeb package(s) left out: " + ", ".join(udebs))
            binaries = [p for p in binaries if p["package"] not in udebs]
        if not binaries:
            raise SystemExit("error: no binary package in debian/control")

        src_name, deb_version = parse_changelog(self.read("changelog") or "")
        self.deb_version = deb_version
        self.homepage = paras[0].get("homepage", "")
        src_name = src_name or source.get("source")
        fmt = (self.read("source/format") or "").strip()
        native = "native" in fmt or (deb_version is not None and "-" not in deb_version)
        rules = Rules(self.read("rules") or "")
        self.generate_from_in(rules)
        if deb_version:
            # /usr/share/dpkg/pkg-info.mk
            # a native version is the package version; its mangled form stays as Debian's
            native_ver = "${{package.version}}" if (native and "-" not in deb_version) else deb_version
            for var, value in (("DEB_VERSION", native_ver), ("DEB_SOURCE", src_name or ""),
                               ("DEB_VERSION_UPSTREAM", debian_upstream_version(deb_version))):
                rules.vars.setdefault(var, value)
        for var, value in rules.vars.items():
            # $(shell dh_listpackages): the binary packages, in debian/control order
            pkgs = " ".join(p["package"] for p in paras[1:] if "package" in p)
            value = value.replace("$(firstword $(shell dh_listpackages))", pkgs.split(" ")[0] if pkgs else "")
            rules.vars[var] = value.replace("$(shell dh_listpackages)", pkgs)

        self.source_name = src_name
        self.source = source
        main = next((b for b in binaries if b["package"] == src_name), None)
        if main is None:
            # libfoo built as libfoo1 + libfoo-dev: the shared library is the
            # main package, named after the source as Wolfi does
            lib = [b for b in binaries if re.match(r"^{}[\d.]+(t64)?$".format(re.escape(src_name or "")), b["package"])]
            main = lib[0] if len(lib) == 1 else binaries[0]
        default_name = src_name if lib_main(main["package"], src_name) else perl_name(python_name(main["package"]))
        dist = re.match(r"https?://metacpan\.org/(?:release|dist)/([\w-]+)", source.get("homepage", ""))
        if dist and main["package"].endswith("-perl"):
            default_name = "perl-" + dist.group(1).lower()  # Wolfi names Perl modules after the CPAN distribution
        name = a.name or default_name
        self.rename = {b["package"]: b["package"] for b in binaries}
        if name != main["package"] and name == python_name(main["package"]):
            # python3-foo -> py3-foo, and python-foo-doc -> py3-foo-doc
            base = main["package"][len("python3-"):]
            for b in binaries:
                m = re.match(r"^python3?-{}(-.+)?$".format(re.escape(base)), b["package"])
                if m:
                    self.rename[b["package"]] = name + (m.group(1) or "")
        for b in binaries:
            if b is not main and re.match(r"^lib.+-perl$", b["package"]):
                self.rename[b["package"]] = perl_name(b["package"])  # libfoo-xs-perl -> perl-foo-xs
        self.rename[main["package"]] = name
        self.recipe_dir = name
        # virtual packages the source's own binaries provide (libapt-pkg -> libapt-pkg7.0)
        self.sibling_provides = {}
        for b in binaries:
            for alts in parse_relations(b.get("provides")):
                if alts[0] not in self.rename and not alts[0].startswith("${"):
                    self.sibling_provides.setdefault(alts[0], self.rename[b["package"]])
        if deb_version and re.search(r"[+~](dfsg|ds|repack)", deb_version) \
                and not files_excluded(self.read("copyright")):
            self.notes.append("Debian repacks the upstream tarball ({}); check debian/copyright "
                              "Files-Excluded before using the pristine upstream source".format(deb_version))

        # ---- version -----------------------------------------------------
        self.version_for_url = None
        version_var = a.version_var
        if not version_var and native and not a.version:
            cands = [v for v in rules.vars if re.match(r"^[A-Z0-9_]*VERSION$", v) and not v.startswith("DEB_")]
            if len(cands) == 1:
                version_var = cands[0]
                self.notes.append("native package: using {}={} from debian/rules as the version "
                                  "(Debian version is {})".format(version_var, rules.vars[version_var], deb_version))
        if a.version:
            version = a.version
        elif version_var:
            if version_var not in rules.vars:
                raise SystemExit("error: variable {} not defined in debian/rules".format(version_var))
            version = rules.expand(rules.vars[version_var])
        else:
            version = debian_upstream_version(deb_version or "0")

        self.version_for_url = version
        # ---- rules variables that feed templated files -> melange vars ------
        templated = rules.template_substitutions()
        melange_vars = {}
        var_refs = {}
        for _out, (_in, subs) in templated.items():
            for ph, var in subs.items():
                if var == version_var:
                    var_refs[var] = "${{package.version}}"
                elif "DEB_VERSION_UPSTREAM" in rules.vars.get(var, "") or var in ("DEB_VERSION_UPSTREAM",):
                    var_refs[var] = "${{package.version}}"
                else:
                    value = rules.expand(rules.vars.get(var, ""))
                    if "$(" in value:
                        self.notes.append("debian/rules variable {} = {} needs make to evaluate; "
                                          "set its value by hand".format(var, rules.vars.get(var, "")))
                    key = var.lower().replace("_", "-")
                    melange_vars[key] = value
                    var_refs[var] = "${{vars.%s}}" % key

        # ---- package ------------------------------------------------------
        desc = main.get("description", "").split("\n", 1)[0].strip()
        desc = desc[:1].upper() + desc[1:]
        pkg = {"name": name, "version": version, "epoch": 0, "description": desc}
        lics = parse_copyright(self.read("copyright"))
        if lics and "Format:" not in (self.read("copyright") or "")[:200]:
            self.notes.append("license {} read from the notice in debian/copyright (not DEP-5); check it".format(lics[0][0]))
        if lics:
            pkg["copyright"] = []
            main_lic = next((lic for lic, files in lics if files == ["*"]), None)
            for lic, files in lics:
                # Files under the main license need no entry of their own.
                if files != ["*"] and lic == main_lic:
                    continue
                entry = {"license": lic}
                if files != ["*"]:
                    entry["paths"] = files
                pkg["copyright"].append(entry)
        else:
            pkg["copyright"] = [{"license": "NOASSERTION"}]
            pkg["copyright"].insert(0, self.todo("debian/copyright is not machine-readable (DEP-5); set the SPDX license"))

        self.main_depends = main.get("depends") or ""
        self.main_package = main["package"]
        runtime = self.map_deps(parse_relations(main.get("depends")) + parse_relations(main.get("pre-depends")), "runtime")
        runtime += self.unversioned_libs(main, source)
        runtime += self.essential_used(main)
        if "${python3:Depends}" in (main.get("depends") or ""):
            reqs = python_requirements(self.tree)
            for mod in self.patch_imports():
                # a Debian patch imports a module that upstream does not require
                if mod not in reqs:
                    reqs.append(mod)
                    self.notes.append("debian/patches import '{}', not in upstream's requirements; added".format(mod))
            if reqs:
                self.notes.append("${python3:Depends} from upstream's requirements: " + ", ".join(reqs))
                runtime += self.map_deps([["python3-" + r] for r in reqs], "runtime")
        build_names = {alt for alts in parse_relations(source.get("build-depends")) for alt in alts}
        if build_names & {"libfontconfig-dev", "libfontconfig1-dev", "libxft-dev"} \
                and main.get("architecture", "any") != "all":
            # Debian's libfontconfig1 brings fontconfig-config, which depends on
            # a font; Wolfi's fontconfig has none, and Xft finds nothing to draw with
            runtime.append(C("ttf-dejavu", "Debian: fontconfig-config depends on fonts-dejavu-core"))
        recommends = [x[0] for x in parse_relations(main.get("recommends"))]
        if runtime or recommends:
            deps = {"runtime": runtime} if runtime else {}
            if recommends:
                deps = dict(deps)
                deps.setdefault("runtime", [])
                deps["runtime"].append(Comment("Debian Recommends (not supported by apk): " + ", ".join(recommends)))
            pkg["dependencies"] = deps

        # ---- maintainer scripts + debconf ----------------------------------
        templates = parse_templates(self.pkgfile(main["package"], "templates", True))
        if main["package"] == "debconf" or "debconf-2.0" in (main.get("provides") or ""):
            templates = []  # debconf itself: keep the confmodule its scripts use
            KEEP_DEBCONF.add(name)
        conffile = "/etc/{}.conf".format(name)
        if re.search(r"(^|\s)/?etc/?(\s|$)|etc/{}\.conf".format(re.escape(name)),
                     self.pkgfile(main["package"], "install", True) or ""):
            # the package installs its own /etc/<name>.conf
            conffile = "/etc/{}-debconf.conf".format(name)
        scripts, uses_debconf = self.scriptlets(main, True, name, templates, conffile, templated, var_refs)
        main_alts = self.alternatives
        if self.script_deps:
            have = pkg.setdefault("dependencies", {}).setdefault("runtime", [])
            for d in self.script_deps:
                if not any((r.value if isinstance(r, C) else r) == d for r in have if not isinstance(r, Comment)):
                    have.insert(0, C(d, "used by the maintainer scripts"))
        config_script = self.pkgfile(main["package"], "config", True)
        if config_script:
            extra = [l.strip() for l in config_script.splitlines()
                     if l.strip() and not l.lstrip().startswith("#")
                     and not re.match(r"^(set -e|\. /usr/share/debconf/confmodule|db_(input|go|beginblock|endblock)\b.*)$", l.strip())]
            if extra:
                self.notes.append("debian/config contains logic beyond prompting; review: " + "; ".join(extra[:3]))
        if templates and uses_debconf:
            self.aux[name + ".conf"] = render_conffile(name, templates)
            self.notes.append("debconf questions converted to {} ({})".format(
                conffile, ", ".join(env_name(name, t["name"]) for t in templates)))
        if scripts:
            pkg["scriptlets"] = scripts
            self.notes.append("maintainer scripts converted; note that apko does not run install scripts")

        # ---- environment ---------------------------------------------------
        build_deps = self.map_deps(parse_relations(source.get("build-depends")) +
                                   parse_relations(source.get("build-depends-indep")) +
                                   parse_relations(source.get("build-depends-arch")), "build")
        own = {b["package"] for b in binaries}
        self_deps = sorted(own & {alt for alts in parse_relations(source.get("build-depends")) for alt in alts})
        if self_deps:
            self.notes.append("build-depends on its own binary package(s) {} (self-hosting): Wolfi needs a "
                              "bootstrap first, e.g. a {}-stage0 recipe from upstream binaries; Debian's "
                              "build profiles show which dependencies that stage uses".format(
                                  ", ".join(self_deps), name))
        bs = rules.buildsystem()
        if bs == "cmake+ninja":
            bs = "cmake"  # Wolfi's cmake pipelines generate Ninja files
        if not bs:
            bs = next((b for f, b in BUILDSYSTEM_FILES if f in self.top), None)
        base = ["build-base", "busybox"] if bs else ["busybox"]
        if bs == "pybuild":
            base += ["python3", "py3-pip", "py3-wheel"]
        if bs == "perl_makemaker":
            base += ["perl"]
        if native and bs:
            # a Debian-native build assumes what debhelper brings: perl (pod2man)
            # and dpkg-dev (dpkg-parsechangelog)
            base += [p for p in ("perl", "dpkg-dev") if p not in base]
        if bs == "autoconf" and self.needs_autoreconf(source):
            base += self.autoreconf_tools()
        env_pkgs = base + [d for d in build_deps if (d.value if isinstance(d, C) else d) not in base]
        environment = {"contents": {
            "keyring": ["https://packages.wolfi.dev/os/wolfi-signing.rsa.pub"],
            "repositories": ["https://packages.wolfi.dev/os"],
            "packages": env_pkgs,
        }}
        exports = self.ported_exports(rules)
        if exports:
            environment["environment"] = exports

        # ---- pipeline -----------------------------------------------------
        pipeline = []
        self.source_steps = []
        if native and a.from_debian and [n for n in self.top if n != "debian"]:
            # a Debian-native program (ucf ...): its source is the Debian tarball
            native_src = self.debian_native_url(source)
            if native_src:
                pipeline.append(native_src)
                self.source_steps = [native_src]
        if not native:
            pipeline += self.fetch_step(source, version)
            self.source_steps = [st for st in pipeline if isinstance(st, dict)]
            excluded = files_excluded(self.read("copyright"))
            if excluded:
                pipeline.append({"name": "Remove files excluded by Debian (debian/copyright Files-Excluded)",
                                 "runs": "rm -rf " + " ".join(excluded) + "\n"})
        series = self.read("patches/series")
        if series:
            patches = [l.split()[0] for l in series.splitlines() if l.strip() and not l.startswith("#")]
            for p in patches:
                with open(os.path.join(self.deb, "patches", p), "rb") as fh:
                    self.aux[os.path.basename(p)] = fh.read()
            pipeline.append({"uses": "patch", "with": {"patches": " ".join(
                "{}/{}".format(name, os.path.basename(p)) for p in patches)}})

        overrides = rules.overrides()
        self.bs = bs
        self.pipeline_used = False
        builddirs = {d for r in overrides.values() for l in r
                     for d in re.findall(r"\s(?:-B\s*|--builddir(?:ectory)?[= ])(\S+)", " " + l) if "udeb" not in d}
        self.multi_builddir = len(builddirs) > 1
        self.python_module = rules.vars.get("PYBUILD_NAME") if bs == "pybuild" else None
        if bs == "pybuild":
            # what can be imported: setuptools' top_level.txt, else the distribution name
            egg = next((n for n in self.top if n.endswith(".egg-info")), None)
            top_level = ""
            if egg and os.path.isfile(os.path.join(self.tree, egg, "top_level.txt")):
                with open(os.path.join(self.tree, egg, "top_level.txt")) as fh:
                    top_level = next((l.strip() for l in fh if l.strip() and not l.startswith("_")), "")
            if top_level:
                self.python_module = top_level
            elif not self.python_module or "-" in self.python_module:
                self.python_module = re.sub(r"^(py3|python3?)-", "", self.python_module or name).replace("-", "_")
        ported = {}
        targets = ("override_dh_auto_configure", "override_dh_auto_build", "override_dh_auto_install") \
            if self.multi_builddir else ("override_dh_auto_build", "override_dh_auto_install")
        for target in targets:
            if target in overrides:
                ported[target] = self.port_recipe(rules, overrides[target], name, main["package"])
        # Overrides that generate the build system (./autogen.sh) run before configure.
        prepare = []
        for target in ("override_dh_update_autotools_config", "override_dh_autoreconf"):
            if target in overrides:
                cmds = self.port_recipe(rules, overrides[target], name, main["package"])
                if cmds:
                    ported[target] = cmds
                    prepare.append({"name": "Prepare the build system (from debian/rules {})".format(target),
                                    "runs": "\n".join(cmds) + "\n"})
        if prepare and bs == "autoconf":
            env_pkgs += [t for t in self.autoreconf_tools() if t not in env_pkgs]
        pipeline += prepare
        self.ported_install = [v for v in ported.values() if v]
        build_override = ported.get("override_dh_auto_build")
        install_override = ported.get("override_dh_auto_install")
        # cargo and go builds install nothing into debian/tmp; an
        # override_dh_auto_install replaces upstream's install step, and when
        # it installs into destdir the *.install files are already satisfied.
        self.upstream_installs = bs not in ("cargo", "golang") and (
            "override_dh_auto_install" not in overrides
            or bool(install_override and any("${{targets.destdir}}" in l or l == self.PIPELINE_MARK
                                             for l in install_override)))
        if ported.get("override_dh_auto_configure"):
            # several build directories: configure each as debian/rules does
            if bs == "autoconf" and self.needs_autoreconf(source):
                pipeline.append({"runs": "autoreconf -fi\n"})
            pipeline.append({"name": "Configure (from debian/rules override_dh_auto_configure)",
                             "runs": "\n".join(ported["override_dh_auto_configure"]) + "\n"})
        elif bs in BUILD_PIPELINES and (build_override or install_override) and bs in ("cmake", "meson", "autoconf"):
            # configure as dh_auto_configure would, then the overrides
            if bs == "autoconf" and self.needs_autoreconf(source):
                pipeline.append({"runs": "autoreconf -fi\n"})
            opts = rules.configure_opts() + self.libexec_opts(bs, binaries)
            entry = {"uses": BUILD_PIPELINES[bs][0]}
            if opts:
                entry["with"] = {"opts": " ".join(opts)}
            pipeline.append(entry)
            if not build_override:
                pipeline.append({"uses": BUILD_PIPELINES[bs][1]})
        if build_override:
            pipeline += self.override_steps(build_override, "Build (from debian/rules override_dh_auto_build)")
        elif bs in BUILD_PIPELINES and not install_override:
            if bs == "autoconf" and self.needs_autoreconf(source):
                pipeline.append({"runs": "autoreconf -fi\n"})
            opts = rules.configure_opts() + self.libexec_opts(bs, binaries)
            for i, step in enumerate(BUILD_PIPELINES[bs]):
                entry = {"uses": step}
                if i == 0 and opts:
                    entry["with"] = {"opts": " ".join(opts)}
                pipeline.append(entry)
            if bs in ("golang", "cargo") and "override_dh_auto_build" not in overrides:
                pipeline.append(self.todo("review the {} pipeline inputs (Debian used dh --buildsystem={})".format(BUILD_PIPELINES[bs][0], bs)))
        elif bs == "scala":
            # dh-scala: the scala/build pipeline of this repository reads the
            # same file, copied next to the recipe.
            config = self.read("scala-build") or ""
            self.aux["scala-build"] = config
            pipeline.append({"uses": "scala/build"})
            if re.search(r"^Package:", config, re.M | re.I):
                pipeline.append(self.todo("the Package fields of scala-build name Debian packages; "
                                          "use melange package names, or remove them"))
        elif bs == "makefile":
            cmds = [] if build_override else ["make -j$(nproc)"]
            if not install_override:
                # dh_auto_install runs "make install" only when the Makefile has it
                cmds.append('if make -s -n install >/dev/null 2>&1; then\n'
                            '  make install DESTDIR="${{targets.destdir}}" PREFIX=/usr\nfi')
            if cmds:
                pipeline.append({"runs": "\n".join(cmds) + "\n"})
        elif bs and bs not in BUILD_PIPELINES:
            pipeline.append(self.todo("unsupported Debian build system '{}'".format(bs)))

        post_install, pre_install = [], []
        for with_ in rules.dh_with():
            if with_ in ("autoreconf", "python3", "sphinxdoc", "systemd", "quilt"):
                continue  # done by the generated steps, or not needed
            self.notes.append("dh --with {} has no direct melange equivalent; review".format(with_))
        skip_overrides = {"override_dh_installdeb", "override_dh_clean", "override_dh_auto_configure",
                          "override_dh_auto_clean"}
        for target, recipe in overrides.items():
            if target in skip_overrides and (target != "override_dh_installdeb" or templated):
                continue
            if target in ("override_dh_update_autotools_config", "override_dh_autoreconf") and ported.get(target):
                continue
            if ported.get(target):
                if target == "override_dh_auto_install":
                    pipeline += self.override_steps(ported[target], "Install (from debian/rules override_dh_auto_install)")
                continue
            if re.search(r"_dh_(lintian|installchangelogs|compress|fixperms|missing|strip|dwz|shlibdeps|makeshlibs|gencontrol|builddeb|md5sums)$", target):
                continue  # Debian packaging checks and bookkeeping (execute_before/after_*)
            tool = re.sub(r"-(indep|arch)$", "", target[len("override_"):])
            calls = [l.strip().lstrip("@-") for l in recipe if l.strip() and not l.strip().startswith("#")]
            if calls and all(re.match(r"^({}|dh_missing)\b".format(re.escape(tool)), c) for c in calls):
                continue  # only adjusts how the same debhelper tool runs
            if target.startswith(("override_dh_auto_test", "override_dh_strip", "override_dh_shlibdeps",
                                  "override_dh_makeshlibs", "override_dh_gencontrol", "override_dh_builddeb",
                                  "override_dh_dwz", "override_dh_installchangelogs", "override_dh_compress",
                                  "override_dh_missing", "override_dh_update_autotools_config",
                                  "override_dh_fixperms", "override_dh_lintian", "override_dh_usrlocal",
                                  "override_dh_installsystemd", "override_dh_installinit")):
                continue
            if re.match(r"^(override|execute_after|execute_before)_dh_", target) and not target.startswith("override_dh_auto_"):
                # dh_foo plus commands of its own
                cmds = self.port_recipe(rules, recipe, name, main["package"])
                if cmds:
                    step = {"name": "From debian/rules " + target, "runs": "\n".join(cmds) + "\n"}
                    if re.match(r"^execute_(after_dh_auto_(configure|build|test)|before_dh_auto_(build|test|install))$", target):
                        pre_install.append(step)   # before the files are installed
                    else:
                        post_install.append(step)  # on the installed files
                    continue
            pipeline.append(self.todo("port debian/rules {}: {}".format(
                target, " && ".join(l.strip() for l in recipe if l.strip())[:200])))

        pipeline += pre_install
        pipeline.append(self.install_step(main, True, native, name))
        pipeline += post_install
        if bs and self.upstream_installs:
            # upstream may install into sbin or /lib; Wolfi is usr-merged with sbin in bin
            pipeline.append({"name": "Usr-merge (sbin into bin)", "runs": (
                'for d in "${{targets.destdir}}" "${{targets.outdir}}"/*; do\n'
                '  for s in usr/sbin sbin bin; do\n'
                '    [ -d "$d/$s" ] && [ ! -L "$d/$s" ] || continue\n'
                '    mkdir -p "$d/usr/bin" && mv "$d/$s"/* "$d/usr/bin/" 2>/dev/null; rmdir "$d/$s"\n'
                '  done\n'
                'done\n')})
        if post_install or ported:
            # commands from debian/rules expect GNU tools (rm --verbose, find -print0 ...)
            env_pkgs += [p for p in ("coreutils", "findutils") if p not in env_pkgs]
            # tools debhelper brings along (perl, dpkg-dev) or the recipe names
            text = "\n".join(l for st in pipeline if isinstance(st, dict) for l in st.get("runs", "").splitlines())
            for tool, pkgs in RECIPE_TOOLS.items():
                if re.search(r"(^|[\s;&|(`])" + re.escape(tool) + r"\b", text, re.M):
                    env_pkgs += [p for p in pkgs if p not in env_pkgs]
        if templates and uses_debconf:
            pipeline[-1]["runs"] += 'install -Dm644 {0}/{0}.conf "${{{{targets.destdir}}}}"{1}\n'.format(name, conffile)
        if main_alts:
            pipeline.append(alternatives_step(main_alts, "${{targets.destdir}}"))
        if any(b.get("architecture", "any") != "all" for b in binaries) and bs:
            # dh_strip; Wolfi recipes strip with the strip pipeline.
            pipeline.append({"uses": "strip"})

        # ---- subpackages --------------------------------------------------
        subpackages = []
        for b in binaries:
            if b is main:
                continue
            subpackages.append(self.subpackage(b, name, main))

        # ---- copy debian/copyright for /usr/share/doc --------------------
        if self.read("copyright") is not None and not self.license_files():
            self.aux["copyright"] = self.read("copyright")

        # ---- update -------------------------------------------------------
        self.version = version
        update = self.update_section(source, native, version_var)

        # ---- test ---------------------------------------------------------
        test = self.test_section(main, name, conffile if (templates and uses_debconf) else None)

        pipeline = self.move_recipe_files(name, [p for p in pipeline if p])
        for sp in subpackages:
            sp["pipeline"] = self.rewrite_recipe_paths(name, sp.get("pipeline", []))

        data = None
        if self.python_module and name.startswith("py3-") and all(
                b.get("architecture", "any") == "all" for b in binaries):
            data = self.python_versions(name, pkg, environment, pipeline, subpackages, test, melange_vars)

        recipe = {"package": pkg}
        if melange_vars:
            recipe["vars"] = melange_vars
        if data:
            recipe["data"] = data
        recipe["environment"] = environment
        recipe["pipeline"] = [p for p in pipeline if p]
        if subpackages:
            recipe["subpackages"] = subpackages
        recipe["update"] = update
        recipe["test"] = test
        return name, recipe, self.header(src_name, deb_version, source, native, fmt)

    # Python versions built when the Wolfi index cannot be read.
    PYTHON_VERSIONS = ("3.12", "3.13")

    def python_versions(self, name, pkg, environment, pipeline, subpackages, test, melange_vars):
        """Rewrite a pure Python recipe in the Wolfi layout: one py3.X-foo
        subpackage per supported Python, py3-supported-foo, and an empty
        py3-foo resolved through provides."""
        def val(d):
            return d.value if isinstance(d, C) else d
        runtime = pkg.get("dependencies", {}).get("runtime", [])
        py_deps = [re.sub(r"^py3-(supported-)?", "", val(d)) for d in runtime
                   if not isinstance(d, Comment) and val(d).startswith("py3-")]
        others = [d for d in runtime if isinstance(d, Comment) or not val(d).startswith("py3-")]
        if self.wolfi.names is None:
            versions = list(self.PYTHON_VERSIONS)
        else:
            # every supported Python that has all the dependencies
            versions = ["3.{}".format(n) for n in range(8, 30)
                        if self.wolfi.has("py3.{}-build-base".format(n))
                        and all(self.wolfi.has("py3.{}-{}".format(n, d)) for d in py_deps)]
            if not versions:
                versions = list(self.PYTHON_VERSIONS)
                self.notes.append("no Python version in Wolfi has all of: " + ", ".join(py_deps))
        pypi = name[len("py3-"):]
        melange_vars["pypi-package"] = pypi
        melange_vars["import"] = self.python_module
        pkg["dependencies"] = {"provider-priority": 0}

        env = environment["contents"]["packages"]
        keep = []
        for d in env:
            v = None if isinstance(d, Comment) else val(d)
            if v in ("build-base", "python3", "py3-pip", "py3-wheel", "py3-setuptools", "py3-supported-setuptools"):
                continue
            if v and re.match(r"^py3\.\d+-.+-bin$", v):
                continue  # commands of one Python: they clash with the other versions' build-base
            if v and v.startswith("py3-") and not v.startswith("py3-supported-") \
                    and self.wolfi.has("py3-supported-" + v[4:]):
                d = C("py3-supported-" + v[4:], d.comment if isinstance(d, C) else "Debian: python3-" + v[4:])
            keep.append(d)
        uses_python = any("python3 " in st.get("runs", "") for st in pipeline if isinstance(st, dict))
        env[:] = [keep[0], "py3-supported-build-base"] + (["python3"] if uses_python else []) + keep[1:]

        pipeline[:] = [st for st in pipeline if not (isinstance(st, dict) and st.get("uses") == "py/pip-build-install")]
        # py3-foo is never installed (provides pick py3.X-foo): the license
        # goes with each py3.X-foo.
        dest = '"${{targets.destdir}}"/usr/share/'
        lic_dirs = (dest + "licenses/" + name, dest + "doc/" + name + "/")
        lic = []
        for st in pipeline:
            if isinstance(st, dict) and any(d in st.get("runs", "") for d in lic_dirs):
                lines = st["runs"].rstrip("\n").split("\n")
                sub_name = "py${{range.key}}-${{vars.pypi-package}}"
                for l in lines:
                    if any(d in l for d in lic_dirs):
                        l = l.replace(lic_dirs[0], '"${{targets.contextdir}}"/usr/share/licenses/' + sub_name)
                        lic.append(l.replace(lic_dirs[1], '"${{targets.contextdir}}"/usr/share/doc/' + sub_name + "/"))
                st["runs"] = "".join(l + "\n" for l in lines if not any(d in l for d in lic_dirs))
        pipeline[:] = [st for st in pipeline if not (isinstance(st, dict) and "runs" in st and not st["runs"])]
        for st in test["pipeline"]:
            if "runs" in st:
                st["runs"] = "".join(l + "\n" for l in st["runs"].splitlines()
                                     if not l.startswith(("test -f /usr/share/licenses/",
                                                          "test -f /usr/share/doc/{}/".format(name))))
        test["pipeline"] = [st for st in test["pipeline"] if st.get("runs", True)]
        sub = {
            "range": "py-versions",
            "name": "py${{range.key}}-${{vars.pypi-package}}",
            "description": "${{vars.pypi-package}} installed for python${{range.key}}",
            "dependencies": {"provider-priority": "${{range.value}}",
                             "provides": ["py3-${{vars.pypi-package}}"]},
            "pipeline": [{"uses": "py/pip-build-install", "with": {"python": "python${{range.key}}"}}]
            + ([{"runs": "\n".join(lic) + "\n"}] if lic else []),
            "test": {"pipeline": [{"uses": "python/import",
                                   "with": {"python": "python${{range.key}}", "import": "${{vars.import}}"}}]},
        }
        deps = ["py${{range.key}}-" + d for d in py_deps] + others
        if deps:
            sub["dependencies"]["runtime"] = deps
        meta = {
            "name": "py3-supported-${{vars.pypi-package}}",
            "description": "meta package providing ${{vars.pypi-package}} for supported python versions.",
            "dependencies": {"runtime": ["py{}-${{{{vars.pypi-package}}}}".format(v) for v in versions]},
            "test": {"environment": {"contents": {"packages": ["busybox", "apk-tools"]}},
                     "pipeline": [{"uses": "test/metapackage"}]},
        }
        subpackages[:0] = [sub, meta]
        # py3-foo resolves to the newest py3.X-foo, not necessarily python3's
        test["environment"]["contents"]["packages"].append("py3-supported-" + pypi)
        test["pipeline"] = [st for st in test["pipeline"] if st.get("uses") != "python/import"]
        test["pipeline"].append({"uses": "python/import", "with": {"python": "python3", "imports": "import ${{vars.import}}"}})
        self.notes.append("Wolfi Python layout: py3.X-{} for Python {}".format(pypi, ", ".join(versions)))
        return [{"name": "py-versions",
                 "items": {v: v.replace(".", "") for v in reversed(versions)}}]

    # The files next to the recipe (packages/<name>/) are copied into the
    # build tree as <name>/, where they can clash with the sources (a file
    # called <name>) or what upstream builds, so they are moved aside first.
    RECIPE_FILES = ".recipe-files"

    def rewrite_recipe_paths(self, name, steps):
        if not self.aux:
            return steps
        def fix(v):
            if isinstance(v, str):
                for fname in self.aux:
                    # relative paths only: not .../usr/share/doc/<name>/copyright
                    v = re.sub(r"(?<![\w/.-]){}/{}\b".format(re.escape(name), re.escape(fname)),
                               "{}/{}".format(self.RECIPE_FILES, fname), v)
                return v
            if isinstance(v, list):
                return [fix(x) for x in v]
            if isinstance(v, dict):
                return {k: fix(x) for k, x in v.items()}
            return v
        out = []
        for st in steps:
            st = fix(st)
            if isinstance(st, dict) and st.get("uses") == "scala/build":
                st = dict(st, **{"with": dict(st.get("with") or {}, config=self.RECIPE_FILES + "/scala-build")})
            out.append(st)
        return out

    def move_recipe_files(self, name, steps):
        if not self.aux:
            return steps
        steps = self.rewrite_recipe_paths(name, steps)
        files = " ".join(sorted(self.aux))
        move = {"name": "Move the recipe files out of the build tree",
                "runs": "mkdir -p {d}\nfor f in {files}; do mv {n}/$f {d}/; done\nrmdir {n} 2>/dev/null || true\n".format(
                    d=self.RECIPE_FILES, files=files, n=name)}
        # first: the sources may contain a file named like the directory
        return [move] + steps

    # -- sections -----------------------------------------------------------

    def scriptlets(self, binary, is_main, name, templates, conffile, templated, var_refs):
        """Convert the maintainer scripts of one binary package."""
        scripts, uses_debconf = {}, False
        self.alternatives = []
        for kind, targets in SCRIPT_MAP.items():
            text = self.pkgfile(binary["package"], kind, is_main)
            if text is None and is_main:
                for out_name in (kind, "{}.{}".format(binary["package"], kind)):
                    if out_name in templated:
                        src, subs = templated[out_name]
                        text = self.read(src)
                        for ph, var in subs.items():
                            text = text.replace(ph, var_refs[var]) if text else text
                        break
            if text is None:
                continue
            if kind == "postinst":
                self.alternatives = alternatives(text)
            label = kind if is_main else "{}.{}".format(binary["package"], kind)
            body, dc = convert_script(text, label, name, templates if is_main else [], conffile, self.notes)
            if dc and not is_main:
                self.notes.append("{}: debconf in a subpackage is not converted".format(label))
            uses_debconf |= dc
            for target, argv in targets:
                scripts[target] = wrap_script(label, body, argv)
        # packages whose commands the scripts call (update-alternatives -> dpkg ...)
        own = self.rename.get(binary["package"], binary["package"])
        self.script_deps = sorted({d for ds in SCRIPT_DEPS.values() for d in ds} - {own})
        SCRIPT_DEPS.clear()
        return scripts, uses_debconf

    def header(self, src, version, source, native, fmt):
        lines = [
            "Generated by debian-to-melange {} from Debian source package".format(__version__),
            "{} {}{}.".format(src, version, " ({})".format(fmt) if fmt else ""),
        ]
        if self.args.from_debian:
            lines.append("https://tracker.debian.org/pkg/{}".format(src))
        if source.get("vcs-browser"):
            lines.append("Debian packaging: {}".format(source["vcs-browser"]))
        if self.notes:
            lines.append("")
            lines.append("Conversion notes:")
            lines += ["- " + n for n in self.notes]
        return lines

    def fetch_step(self, source, version):
        url = self.args.upstream_url
        if not url:
            watch = self.read("watch") or ""
            m = re.search(r"https?://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/(?:tags|releases)", watch)
            tpl = re.search(r"(?mi)^Template:\s*GitHub\s*$", watch)
            if not m and tpl:
                # debian/watch v5 template: Owner + Project
                owner = re.search(r"(?mi)^Owner:\s*(\S+)", watch)
                project = re.search(r"(?mi)^Project:\s*(\S+)", watch)
                if owner and project:
                    m = re.match(r"(.*)/(.*)", "{}/{}".format(owner.group(1), project.group(1)))
            repo, prefix = None, None
            if m:
                repo = "https://github.com/{}/{}".format(m.group(1), m.group(2))
            elif re.search(r"opts=\"?[^\n]*\bmode=git\b", watch):
                # debian/watch v4, git mode: opts="mode=git" <repo> refs/tags/<prefix>(...)
                body = re.sub(r"\\\n", " ", watch)
                gm = re.search(r"mode=git[^\n]*?\s((?:git|https?)://\S+)\s+refs/tags/([^(\s]*)\(", body)
                if gm:
                    repo = re.sub(r"^git://", "https://", gm.group(1)).rstrip("/")
                    prefix = gm.group(2).replace("\\", "")
            elif re.search(r"(?mi)^Mode:\s*git\b", watch):
                # debian/watch v5, git mode: Source: <repo> + Matching-Pattern: refs/tags/<prefix>(...)
                sm = re.search(r"(?mi)^Source:\s*(https?://\S+?)/?\s*$", watch)
                repo = sm.group(1) if sm else None
                pm = re.search(r"(?mi)^Matching-Pattern:\s*refs/tags/([^(@\s]*)(?:\(|@)", watch)
                prefix = pm.group(1).replace("\\", "") if pm else None
            if repo:
                # Wolfi pins git sources with git-checkout + expected-commit.
                gh = re.match(r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", repo)
                if gh:
                    repo = "https://github.com/{}/{}".format(gh.group(1), gh.group(2))
                snap = re.match(r"^(.*)_git(\d{8})$", version)
                if snap:
                    steps, notes = git_snapshot_step(repo, snap.group(2), resolve=self.args.download)
                    self.git_source = (repo, prefix or "")
                    self.notes += notes or ["upstream git snapshot of {} (debian/watch), pinned to the last commit "
                                            "of that day".format(snap.group(2))]
                    return steps
                steps, notes = git_url_checkout_step(repo, version, prefix, resolve=self.args.download)
                tag = next(st["with"]["tag"] for st in steps if isinstance(st, dict))
                self.git_source = (repo, tag.replace("${{package.version}}", ""))
                self.notes += notes
                if not notes:
                    self.notes.append("upstream from debian/watch ({}), pinned to the tag's commit".format(
                        "GitHub" if gh else "git"))
                return steps
        cpan = re.match(r"https?://metacpan\.org/(?:release|dist)/([\w-]+)", source.get("homepage", ""))
        if not url and cpan:
            # CPAN keeps every release under modules/by-module/<top namespace>/
            dist = cpan.group(1)
            cands = []
            if self.args.download:
                # metacpan knows the author directory of the latest release
                try:
                    latest = json.loads(http_get("https://fastapi.metacpan.org/v1/release/" + dist))
                    cands.append(latest["download_url"].replace(latest["version"], version))
                    self.cpan_module = latest.get("main_module")
                except Exception:
                    pass
            cands += ["https://www.cpan.org/modules/by-module/{}/{}-{}.{}".format(dist.split("-")[0], dist, version, ext)
                      for ext in ("tar.gz", "tgz", "tar.bz2")]
            for cand in cands:
                if not self.args.download or url_exists(cand):
                    url = cand
                    self.notes.append("upstream tarball from CPAN ({})".format(dist))
                    break
        if not url:
            cands = watch_tarball_urls(self.read("watch") or "", source.get("source", ""), version)
            if cands and self.args.download:
                # the first that exists
                url = next((c for c in cands if url_exists(c)), None)
            elif cands:
                url = cands[0]
            if url:
                self.notes.append("upstream tarball from debian/watch")
        if not url and self.args.download:
            url = self.debian_orig_url(source, version)
        if not url:
            return [self.todo("set the upstream tarball URL (see debian/watch or {})".format(source.get("homepage", "Homepage"))),
                    {"uses": "fetch", "with": {"uri": "https://example.invalid/${{package.name}}-${{package.version}}.tar.gz",
                                               "expected-sha256": "0" * 64}}]
        url = url.replace(version, "${{package.version}}")
        sha = None
        if self.args.download:
            real = url.replace("${{package.version}}", version)
            sha = hashlib.sha256(http_get(real)).hexdigest()
        step = {"uses": "fetch", "with": {"uri": url, "expected-sha256": sha or "0" * 64}}
        if not sha:
            return [self.todo("compute expected-sha256 (re-run with --download)"), step]
        return [step]

    def debian_native_url(self, source):
        """fetch step for the tarball of a Debian-native source package."""
        ver = (self.deb_version or "").split(":", 1)[-1]
        name = source.get("source", "")
        prefix = name[:4] if name.startswith("lib") else name[0]
        for ext in ("xz", "gz", "bz2"):
            url = "https://deb.debian.org/debian/pool/{}/{}/{}/{}_{}.tar.{}".format(
                DEBIAN_AREA.get(name, "main"), prefix, name, name, ver, ext)
            data = None
            if self.args.download:
                try:
                    data = http_get(url)
                except Exception:
                    continue
                if not is_archive(data):
                    continue
            step = {"uses": "fetch", "with": {
                "uri": url.replace(ver, "${{package.version}}") if ver == self.version_for_url else url,
                "expected-sha256": hashlib.sha256(data).hexdigest() if data else "0" * 64}}
            self.notes.append("Debian-native package: source from the Debian archive")
            return step
        return None

    def debian_orig_url(self, source, version):
        """Debian's copy of the upstream tarball, when upstream cannot be reached."""
        upver = (self.deb_version or "").split(":", 1)[-1].rsplit("-", 1)[0]
        name = source.get("source", "")
        if not upver or not name or re.search(r"[+~](dfsg|ds|repack)", upver):
            return None  # repacked by Debian: not the upstream tarball
        prefix = name[:4] if name.startswith("lib") else name[0]
        for ext in ("gz", "xz", "bz2"):
            url = "https://deb.debian.org/debian/pool/{}/{}/{}/{}_{}.orig.tar.{}".format(
                DEBIAN_AREA.get(name, "main"), prefix, name, name, upver, ext)
            if url_exists(url):
                self.notes.append("upstream download not reachable; using Debian's copy of the upstream "
                                  "tarball ({}), which disappears from the pool when Debian updates".format(url))
                return url
        return None

    def install_lines(self, binary, main, native, destdir):
        cmds = []
        inst = self.pkgfile(binary["package"], "install", main)
        # Nothing installed by the upstream build system (native packages,
        # cargo, overridden dh_auto_install): dh_install takes the paths
        # from the source tree. Otherwise upstream installs straight into
        # destdir, and only subpackages move files out of it.
        from_tree = native or not self.upstream_installs
        if inst and (from_tree or not main):
            for src, dst, rename in install_entries(inst, keep_src=native):
                if not rename and re.search(r"[*?\[]", os.path.dirname(src)) \
                        and dst == usr_merge(os.path.dirname(norm_path(src))):
                    # a glob in the directories: each match keeps its own path (locale/*/*/foo.mo)
                    tree = from_tree and not (native and main and self.upstream_installs and self.bs)
                    base = "." if tree else "${{targets.destdir}}"
                    if not tree and main:
                        continue  # installed by the build, already in place
                    cmds.append('for f in {0}; do\n'
                                '  [ -e "$f" ] || continue\n'
                                '  r="${{f#{1}/}}"\n'
                                '  mkdir -p "{2}/$(dirname "$r")" && {3} "$f" "{2}/$r"\n'
                                'done'.format(shell_path(base, src if tree else norm_path(src)), base, destdir,
                                              "cp -a" if tree else "mv"))
                    continue
                src = self.debian_file(src)
                target = '"{}/{}/{}"'.format(destdir, dst, rename) if rename else '"{}/{}/"'.format(destdir, dst)
                if from_tree and native and main and self.upstream_installs and self.bs and not rename:
                    # dh_install looks in debian/tmp first: the build may have installed it already
                    cmds.append('if ! ls -d {4} >/dev/null 2>&1; then\n  mkdir -p "{0}/{1}"\n  cp -a {2} {3}\nfi'.format(
                        destdir, dst, src, target, shell_path(destdir, norm_path(src))))
                elif from_tree:
                    cmds.append('mkdir -p "{0}/{1}"\ncp -a {2} {3}'.format(destdir, dst, src, target))
                elif dst.startswith("usr/share/man/") and "*" not in src:
                    # Wolfi's perl/make, for one, does not install module man pages
                    cmds.append('if [ -e {2} ]; then\n  mkdir -p "{0}/{1}"\n  mv {2} {3}\nfi'.format(
                        destdir, dst, shell_path("${{targets.destdir}}", src), target))
                else:
                    cmds.append('mkdir -p "{0}/{1}"\nmv {2} {3}'.format(
                        destdir, dst, shell_path("${{targets.destdir}}", src), target))
        for pat in self.install_excludes.get("*", []) + self.install_excludes.get(binary["package"], []):
            # dh_install -X: not in this package
            if main:
                cmds.append('find "{0}" -path "*{1}*" -prune -exec rm -rf {{}} +'.format(destdir, pat))
            else:
                cmds.append('(cd "{0}" && find . -path "*{1}*" -prune | while read -r f; do\n'
                            '  mkdir -p "$(dirname "${{{{targets.destdir}}}}/$f")" && mv "$f" "${{{{targets.destdir}}}}/$f"\n'
                            'done)'.format(destdir, pat))
        for line in (self.pkgfile(binary["package"], "manpages", main) or "").splitlines():
            page = line.split("#", 1)[0].strip()
            if page.startswith("debian/tmp/"):
                page = page[len("debian/tmp/"):]
            if page.startswith("usr/") and self.upstream_installs:
                continue  # installed by the build into destdir already
            m = re.search(r"\.(\d)\w*(\.gz)?$", page)
            if page and m:
                cmds.append('install -Dm644 {0} -t "{1}/usr/share/man/man{2}"'.format(
                    self.debian_file(page), destdir, m.group(1)))
        for line in (self.pkgfile(binary["package"], "dirs", main) or "").splitlines():
            if line.strip():
                cmds.append('mkdir -p "{}/{}"'.format(destdir, usr_merge(norm_path(line))))
        for line in (self.pkgfile(binary["package"], "links", main) or "").splitlines():
            parts = line.split("#", 1)[0].split()
            if len(parts) == 2:
                target, link = usr_merge(norm_path(parts[0])), usr_merge(norm_path(parts[1]))
                cmds.append('mkdir -p "{0}/{2}"\nln -sf /{1} "{0}/{3}"'.format(
                    destdir, target, os.path.dirname(link), link))
        unit = self.read("{}.service".format(binary["package"])) or (self.read("service") if main else None)
        if unit is not None:
            # dh_installsystemd
            pkgname = self.rename.get(binary["package"], binary["package"])
            self.aux[pkgname + ".service"] = unit
            cmds.append('install -Dm644 {0}/{1}.service "{2}/usr/lib/systemd/system/{1}.service"'.format(
                self.recipe_dir, pkgname, destdir))
        docdir = "{}/usr/share/doc/{}".format(destdir, self.rename.get(binary["package"], binary["package"]))
        for line in (self.pkgfile(binary["package"], "examples", main) or "").splitlines():
            ex = line.split("#", 1)[0].strip()
            if ex.startswith(("usr/", "debian/tmp/usr/")) and self.upstream_installs:
                # dh_installexamples finds it in debian/tmp: installed by the build
                ex = ex[len("debian/tmp/"):] if ex.startswith("debian/tmp/") else ex
                if os.path.dirname(ex).rstrip("/*") == "{}/examples".format(docdir[len(destdir) + 1:]).rstrip("/") \
                        or ex.rstrip("/*").startswith("{}/examples".format(docdir[len(destdir) + 1:])):
                    continue  # already where dh_installexamples puts it
                ex = shell_path("${{targets.destdir}}", ex)
            if ex:
                # dh_installexamples
                cmds.append('mkdir -p "{0}/examples"\ncp -a {1} "{0}/examples/"'.format(docdir, ex))
        for line in (self.pkgfile(binary["package"], "docs", main) or "").splitlines():
            doc = line.split("#", 1)[0].strip()
            if doc:
                # dh_installdocs takes them from the source tree; may be directories
                cmds.append('mkdir -p "{0}"\ncp -a {1} "{0}/"'.format(docdir, self.debian_file(doc)))
        # Drop repeated "mkdir -p" of the same directory.
        out, made = [], set()
        for cmd in cmds:
            lines = cmd.split("\n")
            if lines[0].startswith("mkdir -p ") and lines[0] in made:
                lines = lines[1:]
            made.add(cmd.split("\n")[0])
            if lines:
                out.append("\n".join(lines))
        return out

    def needs_autoreconf(self, source):
        """dh runs dh_autoreconf from compat 10; a git checkout has no configure."""
        if dh_compat(source, self.read) < 10:
            return False
        return self.git_source is not None or ("configure.ac" in self.top and "configure" not in self.top)

    def autoreconf_tools(self):
        tools = ["autoconf", "automake"]
        ac = ""
        for f in ("configure.ac", "autogen.sh"):
            try:
                with open(os.path.join(self.tree, f), errors="replace") as fh:
                    ac += fh.read()
            except OSError:
                pass
        if re.search(r"\b(LT_INIT|AC_PROG_LIBTOOL|libtoolize|LIBTOOLIZE)\b", ac):
            tools.append("libtool")
        if re.search(r"\bAM_GNU_GETTEXT\b", ac):
            tools.append("gettext-dev")
        return tools

    def license_files(self):
        return [f for f in LICENSE_FILES if f in self.top]

    def install_step(self, binary, main, native, name):
        dest = "${{targets.destdir}}"
        cmds = self.install_lines(binary, main, native, dest)
        lic = self.license_files()
        if lic:
            cmds.append('install -Dm644 {} -t "{}"/usr/share/licenses/{}'.format(" ".join(lic), dest, name))
        else:
            cmds.append('install -Dm644 {0}/copyright "{1}"/usr/share/doc/{0}/copyright'.format(name, dest))
        return {"name": "Install files", "runs": "\n".join(cmds) + "\n"}

    def subpackage(self, b, name, main):
        desc = b.get("description", "").split("\n", 1)[0].strip()
        sub = {"name": self.rename.get(b["package"], b["package"]), "description": desc[:1].upper() + desc[1:]}
        cmds = self.install_lines(b, False, False, "${{targets.contextdir}}")
        filled = "${{{{targets.outdir}}}}/{}".format(sub["name"])
        if cmds:
            sub["pipeline"] = [{"runs": "\n".join(cmds) + "\n"}]
        elif any(filled in l for ls in self.ported_install for l in ls):
            # debian/rules installs straight into this package
            sub["pipeline"] = [{"runs": "true\n"}]
        elif b.get("section", "").endswith("metapackages") or re.match(r"(?i)^meta-?package", desc) \
                or re.search(r"(?i)\btransitional (dummy )?package\b", desc):
            sub["pipeline"] = [{"runs": "true\n"}]  # only dependencies
        elif b["package"].endswith("-dev"):
            sub["pipeline"] = [{"uses": "split/dev"}]
        elif b["package"].endswith("-doc") and self.bs not in ("pybuild",):
            sub["pipeline"] = [{"uses": "split/manpages"}]
        else:
            sub["pipeline"] = [self.todo("no debian/{}.install; define which files go to this subpackage".format(b["package"])),
                               {"runs": "true\n"}]
        deps = self.map_deps(parse_relations(b.get("depends")), "runtime")
        deps += self.unversioned_libs(b, self.source)
        deps += self.essential_used(b)
        if deps:
            sub["dependencies"] = {"runtime": deps}
        scripts, _ = self.scriptlets(b, False, name, [], "", {}, {})
        if self.alternatives:
            sub["pipeline"].append(alternatives_step(self.alternatives, "${{targets.contextdir}}"))
        if self.script_deps:
            sub.setdefault("dependencies", {}).setdefault("runtime", [])
            sub["dependencies"]["runtime"] += [C(d, "used by the maintainer scripts") for d in self.script_deps]
        if scripts:
            sub["scriptlets"] = scripts
        test = self.test_section(b, None, None, main=False)
        if test:
            sub["test"] = test
        return sub

    def update_section(self, source, native, version_var):
        if native:
            return {"enabled": False,
                    "manual": True,
                    "exclude-reason": "Debian-native package; bump {} by hand".format(
                        "the version (debian/rules {})".format(version_var) if version_var else "the version")}
        watch = self.read("watch") or ""
        m = re.search(r"github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/(?:tags|releases)", watch)
        if not m and getattr(self, "git_source", None):
            m = re.match(r"https://github\.com/([^/]+)/([^/]+)$", self.git_source[0])
        if m:
            github = {"identifier": "{}/{}".format(m.group(1), m.group(2))}
            prefix = self.git_source[1] if self.git_source else "v"
            if prefix:
                github["strip-prefix"] = prefix
            if self.git_source:
                github["use-tag"] = True
            return {"enabled": True, "github": github}
        if getattr(self, "git_source", None):
            git = {"strip-prefix": self.git_source[1]} if self.git_source[1] else {}
            return {"enabled": True, "git": git}
        m = re.match(r"https?://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", source.get("homepage", ""))
        if m:
            # A tarball (e.g. from PyPI) with its sources on GitHub: follow the tags.
            github = {"identifier": "{}/{}".format(m.group(1), m.group(2))}
            tag = resolve_tag(m.group(0).rstrip("/"), self.version)[0] if self.args.download else None
            if tag is None:
                self.notes.append("update: check the tag format of {} (assumed v{})".format(m.group(0), self.version))
            prefix = tag[:-len(self.version)] if tag else "v"
            if prefix:
                github["strip-prefix"] = prefix
            github["use-tag"] = True
            return {"enabled": True, "github": github}
        project = None
        if self.args.download:
            # the Debian name, then the upstream name in the Homepage (metacpan, PyPI, GitHub ...)
            names = [source.get("source", "")]
            hm = re.search(r"/([\w.-]+?)/?$", source.get("homepage", ""))
            if hm and hm.group(1) not in names:
                names.append(hm.group(1))
            project = next((p for p in (release_monitoring_id(n, self.version) for n in names) if p), None)
        if project:
            return {"enabled": True, "release-monitor": {"identifier": project}}
        return {"enabled": True,
                "release-monitor": {"identifier": C(0, "{}: set the release-monitoring.org project id".format(TODO))}}

    def autopkgtests(self, name):
        """debian/tests/control -> melange test pipeline steps and packages."""
        control = self.read("tests/control")
        if not control:
            return [], []
        steps, packages = [], []
        aliases = dict(ESSENTIAL_ALIASES)
        for i, para in enumerate(parse_deb822(control)):
            restrictions = para.get("restrictions", "").replace(",", " ").split()
            for r in restrictions:
                if r in ("isolation-machine", "breaks-testbed", "needs-reboot"):
                    self.notes.append("autopkgtest restriction '{}' cannot be honoured by melange test".format(r))
            deps = [d for d in parse_relations(para.get("depends", "@")) if d[0] not in ("@", "@builddeps@")]
            if "@" in [d[0] for d in parse_relations(para.get("depends", "@"))]:
                # "@" installs the package with its Depends, debconf included
                deps += [alts for alts in parse_relations(self.main_depends)
                         if any(a in ("debconf", "ucf") for a in alts)]
            mapped = self.map_deps(deps, "test")
            missing = [d for d in mapped if isinstance(d, Comment)]
            if missing:
                what = para.get("test-command", "").split("\n")[0][:60] or para.get("tests", "")
                self.notes.append("autopkgtest '{}' left out: it needs packages that are not in Wolfi".format(what))
                steps.append(Comment("{}: autopkgtest '{}' left out; it needs packages that are not in Wolfi".format(TODO, what)))
                continue
            for d in mapped:
                if d not in packages:
                    packages.append(d)
            for alts in deps:
                wolfi = self.map_deps([alts[:1]], "test")
                if wolfi and not isinstance(wolfi[0], Comment):
                    aliases.setdefault(alts[0], wolfi[0].value if isinstance(wolfi[0], C) else wolfi[0])
            for e in ESSENTIAL:
                if e not in [p.value if isinstance(p, C) else p for p in packages]:
                    packages.append(C(e, "Essential in Debian, so on every testbed"))
            if any((d.value if isinstance(d, C) else d).startswith("py3-") for d in mapped) and "python3" not in packages:
                packages.append("python3")  # py3-supported-* do not provide the python3 command
            if "@builddeps@" in para.get("depends", ""):
                self.notes.append("autopkgtest uses @builddeps@; add the build dependencies to the test environment")
            env = 'export AUTOPKGTEST_TMP="$(mktemp -d)"\n'
            def guard(cmd):
                if "flaky" not in restrictions:
                    return cmd
                # Restrictions: flaky -- a failure is reported, not fatal
                return "(\n{}) || echo 'autopkgtest marked flaky failed (ignored)'\n".format(cmd)
            if "test-command" in para:
                steps.append({"name": "autopkgtest: {}".format(para["test-command"].split("\n")[0][:60]),
                              "runs": env + guard(para["test-command"].strip() + "\n")})
            for test in para.get("tests", "").split():
                script = self.read(os.path.join(para.get("tests-directory", "tests"), test))
                if script is None:
                    continue
                shell = "bash" if script.startswith("#!/bin/bash") or script.startswith("#!/usr/bin/env bash") else "sh"
                if shell == "bash" and "bash" not in packages:
                    packages.append("bash")
                steps.append({"name": "autopkgtest: " + test,
                              "runs": env + guard(script.split("\n", 1)[1 if script.startswith("#!") else 0].strip() + "\n")})
        real = [st for st in steps if not isinstance(st, Comment)]
        if real:
            self.notes.append("autopkgtests converted to the test pipeline ({} steps)".format(len(real)))
            steps.insert(0, dpkg_database_step(aliases, self.main_package))
            if self.source_steps:
                # autopkgtest runs in the unpacked source tree
                steps = [dict(st) for st in self.source_steps] + steps
        return steps, packages

    def test_section(self, binary, name, conffile, main=True):
        cmds = []
        inst = self.pkgfile(binary["package"], "install", main) or ""
        for line in inst.splitlines():
            parts = line.split()
            if line.lstrip().startswith("#") or not parts:
                continue
            dest = (parts[-1] if len(parts) > 1 else os.path.dirname(parts[0])).strip("/")
            if not re.match(r"^(usr/)?s?bin(/|$)", dest):
                continue
            tool = os.path.basename(dest) if "=>" in parts else os.path.basename(parts[0])
            path = "/usr/bin/" + tool  # usr-merged, sbin merged into bin
            if re.search(r"[*?\[]", tool):
                # a glob: names are only known after the build; usr/bin/* says nothing
                if tool.strip("*"):
                    cmds.append("ls {} >/dev/null".format(path))
                continue
            if re.search(r"(^|/)scripts?/|\.(sh|pl|py|tcl|tk)$", parts[0]) or re.match(r"^(usr/)?sbin", dest):
                # scripts may need interpreters that are only suggested;
                # system tools (sbin) often need root, a tty or hardware
                cmds.append("test -x " + path)
            else:
                # some tools print their usage with a non-zero status
                cmds.append("{0} --version || ({0} --help 2>&1 || true) | grep -qi -e usage -e {0}".format(tool))
        if not main and not cmds:
            return None
        if main and self.license_files():
            cmds.append("test -f /usr/share/licenses/{}/{}".format(name, self.license_files()[0]))
        elif main:
            cmds.append("test -f /usr/share/doc/{}/copyright".format(name))
        if conffile:
            cmds.append("test -f {}".format(conffile))
        test = {"environment": {"contents": {"packages": ["busybox"]}},
                "pipeline": [{"runs": "\n".join(cmds) + "\n"}]}
        if binary.get("architecture", "any") != "all":
            test["pipeline"].append({"uses": "test/tw/ldd-check"})
        cpan = re.match(r"https?://metacpan\.org/(?:release|dist)/([\w-]+)", getattr(self, "homepage", ""))
        if main and cpan and getattr(self, "bs", None) == "perl_makemaker":
            test["environment"]["contents"]["packages"].append("perl")
            # the Debian Perl team names it for autopkgtest-pkg-perl; else metacpan's main module
            module = (self.read("tests/pkg-perl/use-name") or "").split("\n")[0].strip() \
                or getattr(self, "cpan_module", None) or cpan.group(1).replace("-", "::")
            test["pipeline"].append({"name": "Load the module", "runs": "perl -M{} -e1\n".format(module)})
        if main and getattr(self, "python_module", None):
            test["environment"]["contents"]["packages"].append("python3")
            test["pipeline"].append({"uses": "python/import", "with": {"imports": "import " + self.python_module}})
        if main:
            steps, packages = self.autopkgtests(name)
            have = list(test["environment"]["contents"]["packages"])
            for p in packages:
                key = p.value if isinstance(p, C) else p
                if key != "busybox" and key not in [h.value if isinstance(h, C) else h for h in have]:
                    have.append(p)
            test["environment"]["contents"]["packages"] = have
            test["pipeline"] += steps
        return test


ARCHIVE_EXTS = (".tar.gz", ".tar.xz", ".tar.bz2", ".tgz", ".zip")


def regex_group(text, start):
    """End index (exclusive) of the parenthesised group opening at text[start]."""
    depth, i = 0, start
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i + 1
        i += 1
    return None


def watch_tarball_urls(watch, source, version):
    """Candidate tarball URLs for `version` from a debian/watch (v3/v4) line.

    Only plain URLs whose file name holds the version group are handled
    (no page scraping). Several candidates when the extension is a pattern."""
    body = re.sub(r"\\\n", " ", watch)
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("version="):
            continue
        toks = [t for t in line.split() if not t.startswith("opts=")]
        toks = [t for t in toks if t not in ("debian", "uupdate", "same", "ignore")]
        if not toks or not toks[0].startswith("http"):
            continue
        if len(toks) > 1 and "/" not in toks[1]:
            # <directory> <file pattern>; a web page to scrape (foo.html) is not handled
            if not (toks[0].endswith("/") or "." not in toks[0].rsplit("/", 1)[-1]):
                continue
            url = toks[0].rstrip("/") + "/" + toks[1]
        else:
            url = toks[0]
        url = url.replace("@PACKAGE@", source).replace("@ANY_VERSION@", "(VERSION)")
        exts = [""]
        if url.endswith("@ARCHIVE_EXT@"):
            url, exts = url[:-len("@ARCHIVE_EXT@")], list(ARCHIVE_EXTS)
        m = re.search(r"\\\.\(\?:", url)
        if m and regex_group(url, m.start() + 2) == len(url):
            url, exts = url[:m.start()], list(ARCHIVE_EXTS)  # \.(?:zip|tgz|tar\.(?:gz|xz)...)
        m = re.search(r"(?<!\\)\((?!\?)", url)
        end = regex_group(url, m.start()) if m else None
        if not end:
            continue
        url = url[:m.start()] + version + url[end:]
        url = url.replace("\\.", ".")
        if re.search(r"[()\[\]*+?|^$\\]", url):
            continue
        # pypi.python.org/packages/source is an alias of files.pythonhosted.org
        url = url.replace("://pypi.python.org/packages/source/", "://files.pythonhosted.org/packages/source/")
        m = re.match(r"https?://pypi\.debian\.net/([^/]+)/(.+)$", url)
        if m:
            url = "https://files.pythonhosted.org/packages/source/{}/{}/{}".format(m.group(1)[0], m.group(1), m.group(2))
        return [url + e for e in exts]
    return []


def resolve_tag(url, version, prefixes=("v", "")):
    """Return (tag, commit) for the first existing tag of a git repository, or (None, None)."""
    for prefix in prefixes:
        tag = prefix + version
        try:
            out = subprocess.run(
                ["git", "ls-remote", url,
                 "refs/tags/{0}".format(tag), "refs/tags/{0}^{{}}".format(tag)],
                capture_output=True, text=True, timeout=60).stdout
        except (OSError, subprocess.TimeoutExpired):
            return None, None
        refs = dict(reversed(line.split("\t")) for line in out.splitlines() if "\t" in line)
        commit = refs.get("refs/tags/{}^{{}}".format(tag)) or refs.get("refs/tags/" + tag)
        if commit:
            return tag, commit
    return None, None


def resolve_github_tag(owner, repo, version, prefixes=("v", "")):
    return resolve_tag("https://github.com/{}/{}".format(owner, repo), version, prefixes)


def git_snapshot_step(url, date, resolve=False):
    """git-checkout of the default branch at the last commit of `date` (YYYYMMDD).

    Returns (steps, notes)."""
    branch, commit = "master", None
    if resolve:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:none", url, tmp],
                               check=True, capture_output=True, timeout=300)
                branch = subprocess.run(["git", "-C", tmp, "symbolic-ref", "--short", "HEAD"],
                                        capture_output=True, text=True).stdout.strip() or branch
                day = "{}-{}-{} 23:59:59".format(date[:4], date[4:6], date[6:])
                commit = subprocess.run(["git", "-C", tmp, "rev-list", "-1", "--before=" + day, branch],
                                        capture_output=True, text=True).stdout.strip() or None
            except (OSError, subprocess.SubprocessError):
                pass
    step = {"uses": "git-checkout", "with": {
        "repository": url, "branch": branch, "expected-commit": commit or "0" * 40}}
    if commit:
        return [step], []
    msg = "set expected-commit to the {} commit of {} {} (re-run with --download)".format(date, url, branch)
    return [Comment("{}: {}".format(TODO, msg)), step], [msg]


def git_url_checkout_step(url, version, tag_prefix=None, resolve=False, todo=None):
    """A git-checkout step pinned to a commit, the Wolfi convention for git sources.

    Returns (steps, notes)."""
    prefixes = (tag_prefix,) if tag_prefix is not None else ("v", "")
    tag, commit = resolve_tag(url, version, prefixes) if resolve else (None, None)
    prefix = tag[:-len(version)] if tag else prefixes[0]
    step = {"uses": "git-checkout", "with": {
        "repository": url,
        "tag": prefix + "${{package.version}}",
        "expected-commit": commit or "0" * 40}}
    if commit:
        return [step], []
    msg = "set expected-commit for tag {}{} (re-run with --download, or git ls-remote)".format(prefix, version)
    return [Comment("{}: {}".format(todo or TODO, msg)), step], [msg]


def git_checkout_step(owner, repo, version, tag_prefix=None, resolve=False, todo=None):
    """git_url_checkout_step for a GitHub repository."""
    return git_url_checkout_step("https://github.com/{}/{}".format(owner, repo), version,
                                 tag_prefix, resolve, todo)


def verify_build(recipe_path, source_dir, melange="melange", arch=None, keep=False, extra=()):
    """Build a generated recipe with melange; return (ok, log_tail)."""
    import platform
    arch = arch or {"aarch64": "aarch64", "arm64": "aarch64"}.get(platform.machine(), "x86_64")
    work = tempfile.mkdtemp(prefix="melange-verify-")
    key = os.path.join(work, "verify.rsa")
    cmd_key = [melange, "keygen", key]
    cmd = [melange, "build", recipe_path, "--arch", arch, "--runner", "bubblewrap",
           "--source-dir", source_dir, "--out-dir", os.path.join(work, "out"),
           "--signing-key", key, "--keyring-append", key + ".pub",
           "--repository-append", "https://packages.wolfi.dev/os",
           "--keyring-append", "https://packages.wolfi.dev/os/wolfi-signing.rsa.pub"]
    pipelines = os.path.join(HERE, "..", "..", "pipelines")  # this repository's shared pipelines
    if os.path.isdir(pipelines):
        cmd += ["--pipeline-dir", os.path.abspath(pipelines)]
    cmd += list(extra)
    try:
        subprocess.run(cmd_key, capture_output=True, check=True)
        res = subprocess.run(cmd, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        return False, "cannot run melange: {}".format(exc)
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)
    tail = "\n".join((res.stdout + res.stderr).splitlines()[-25:])
    return res.returncode == 0, tail


def report_build(args, name):
    """--build: verify the recipe that was just written. Returns an exit code."""
    if not getattr(args, "build", False) or args.stdout:
        return 0
    import shlex
    ok, tail = verify_build(os.path.join(args.out, name + ".yaml"), args.out, args.melange,
                            extra=shlex.split(getattr(args, "melange_opts", "") or ""))
    print("melange build: {}".format("OK" if ok else "FAILED"), file=sys.stderr)
    if not ok:
        print(tail, file=sys.stderr)
    return 0 if ok else 3


def spdx_header(license_id, author):
    """SPDX lines for the recipe file, as the recipes in this repository have."""
    if not license_id:
        return []
    if not author:
        name, mail = os.environ.get("DEBFULLNAME"), os.environ.get("DEBEMAIL")
        author = "{} <{}>".format(name, mail) if name and mail else name
    lines = ["SPDX-License-Identifier: " + license_id]
    if author:
        lines.append("SPDX-FileCopyrightText: {} {}".format(time.strftime("%Y"), author))
    return lines + [""]


def write_output(name, recipe, header, aux, out, to_stdout):
    text = "\n".join(["# " + l if l else "#" for l in header]) + "\n"
    text += "\n".join(emit(recipe)) + "\n"
    if to_stdout:
        sys.stdout.write(text)
        return text
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, name + ".yaml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if aux:
        auxdir = os.path.join(out, name)
        os.makedirs(auxdir, exist_ok=True)
        for fname, content in aux.items():
            mode = "wb" if isinstance(content, bytes) else "w"
            with open(os.path.join(auxdir, fname), mode, **({} if mode == "wb" else {"encoding": "utf-8"})) as fh:
                fh.write(content)
    print("wrote {}{}".format(path, " and {}/".format(os.path.join(out, name)) if aux else ""), file=sys.stderr)
    return text


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="debian-to-melange",
        description="Convert Debian source packaging (debian/) to a melange recipe.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--debian-dir", help="path to a debian/ directory or to a source tree containing one")
    src.add_argument("--from-debian", metavar="NAME[=VERSION]",
                     help="fetch the packaging from sources.debian.org")
    p.add_argument("--out", default="packages", help="output directory (default: packages)")
    p.add_argument("--stdout", action="store_true", help="print the recipe instead of writing files")
    p.add_argument("--name", help="override the package name")
    p.add_argument("--version", help="override the package version")
    p.add_argument("--version-var", help="debian/rules variable holding the version (native packages)")
    p.add_argument("--upstream-url", help="upstream tarball URL (the version is templated automatically)")
    p.add_argument("--download", action="store_true", help="download the tarball to compute expected-sha256")
    p.add_argument("--check-wolfi", action="store_true", default=True,
                   help="verify mapped dependency names against the Wolfi APKINDEX (default)")
    p.add_argument("--no-check-wolfi", dest="check_wolfi", action="store_false",
                   help="do not download the Wolfi APKINDEX (offline)")
    p.add_argument("--spdx-license",
                   help="license of the recipe itself, written as an SPDX header (e.g. GPL-3.0-or-later)")
    p.add_argument("--author", default=None,
                   help="copyright holder for the SPDX header (default: $DEBFULLNAME <$DEBEMAIL>)")
    p.add_argument("--strict", action="store_true", help="exit 1 if anything needs manual review")
    p.add_argument("--build", action="store_true",
                   help="build the generated recipe with melange (bubblewrap runner) and report the result")
    p.add_argument("--melange", default="melange", help="melange binary for --build (default: melange)")
    p.add_argument("--melange-opts", default="", help="extra options for melange build (e.g. \"--cache-dir DIR\")")
    p.add_argument("-V", "--tool-version", action="version", version="%(prog)s " + __version__)
    args = p.parse_args(argv)

    tmp = None
    try:
        if args.from_debian:
            tmp = tempfile.mkdtemp(prefix="debian-to-melange-")
            tree, top, _ver = fetch_from_debian(args.from_debian, tmp)
        else:
            path = os.path.abspath(args.debian_dir)
            tree = os.path.dirname(path) if os.path.basename(path) == "debian" else path
            top = None
        conv = Converter(tree, top, args, WolfiIndex(args.check_wolfi))
        name, recipe, header = conv.convert()
        header = spdx_header(args.spdx_license, args.author) + header
        text = write_output(name, recipe, header, conv.aux, args.out, args.stdout)
        for n in conv.notes:
            print("note: " + n, file=sys.stderr)
        built = report_build(args, name)
        if built:
            return built
        return 1 if args.strict and TODO in text else 0
    except urllib.error.URLError as exc:
        print("error: network: {} ({})".format(exc, getattr(exc, "url", None) or getattr(exc, "filename", "")), file=sys.stderr)
        return 2
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
