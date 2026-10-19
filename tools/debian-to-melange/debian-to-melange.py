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
import hashlib
import importlib.util
import json
import os
import re
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
    "pkg-config": "pkgconf-dev",
    "mawk": "gawk",
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
    "npm": "npm",
}


def python_name(binary):
    """Wolfi names Python modules py3-foo, Debian python3-foo."""
    m = re.match(r"^python3-(.+)$", binary)
    return "py3-" + m.group(1) if m and not binary.endswith("-dev") else binary


def dep_candidates(name):
    """Ordered Wolfi name candidates for a Debian package name."""
    if name in NAME_MAP:
        return [NAME_MAP[name]]
    cands = [name]
    m = re.match(r"^openjdk-(\d+)-(jdk|jre)(?:-headless)?$", name)
    if m:
        return ["openjdk-{}".format(m.group(1)) if m.group(2) == "jdk" else "openjdk-{}-jre".format(m.group(1))]
    m = re.match(r"^lib(.+)-perl$", name)
    if m:
        return ["perl-" + m.group(1), name]
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


class WolfiIndex:
    """Optional lookup of package names in the Wolfi APKINDEX (via pkg-check).

    Names published by this repository are tracked separately, so a
    dependency that only exists here can be labelled as such.
    """

    def __init__(self, enabled, arch="x86_64"):
        self.names = None
        self.community = set()
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

    @staticmethod
    def _load(mod, url):
        names = set()
        for e in mod.parse_apkindex(mod.fetch(url, True)):
            names.add(e.get("P"))
            for prov in e.get("p", "").split():
                names.add(re.split(r"[=<>~]", prov, maxsplit=1)[0])
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
    return re.split(r"[+~](?:dfsg|ds|repack)", v)[0]


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


def parse_copyright(text):
    """Return [(spdx, [paths])] for non-debian/* paragraphs, main first."""
    if not text or "Format:" not in text.split("\n", 1)[0] + text[:200]:
        return []
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


class Rules:
    """Minimal debian/rules (Makefile) model: variables, dh line, overrides."""

    def __init__(self, text):
        self.vars = {}
        self.exports = []
        self.targets = {}
        self.dh_args = ""
        lines = self._join_continuations(text.splitlines())
        target = None
        for line in lines:
            if line.startswith("\t"):
                if target is not None:
                    self.targets[target].append(line[1:])
                continue
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
                target = m.group(1).strip()
                self.targets[target] = []
        for recipe in self.targets.get("%", []):
            m = re.search(r"\bdh\s+\$@(.*)$", recipe)
            if m:
                self.dh_args = m.group(1).strip()

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

    def expand(self, value, depth=0):
        if depth > 10:
            return value
        def repl(m):
            name = m.group(1) or m.group(2)
            return self.expand(self.vars.get(name, m.group(0)), depth + 1)
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
    path = re.sub(r"(^|/)lib/(?:\*|\$[({]DEB_HOST_MULTIARCH[)}]|[a-z0-9_]+-linux-gnu[a-z]*)(/|$)",
                  r"\1lib\2", path).rstrip("/")
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


def url_exists(url, tries=2):
    for _ in range(tries):
        try:
            http_get(url)
            return True
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
    prefix = name[:4] if name.startswith("lib") else name[0]
    tree = os.path.join(dest, "{}-{}".format(name, version))

    def walk(path):
        listing = json.loads(http_get(SOURCES_API.format(name=name, version=version, path=path)))
        for item in listing.get("content", []):
            sub = (path + "/" if path else "") + item["name"]
            if item["type"] == "directory":
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

DEBIAN_ONLY_TOOLS = [
    "deb-systemd-helper", "deb-systemd-invoke", "update-alternatives",
    "dpkg-maintscript-helper", "dpkg-divert", "dpkg-statoverride",
    "update-rc.d", "invoke-rc.d", "ucf", "ucfr", "dpkg-trigger", "py3compile", "py3clean",
]


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


def convert_script(text, kind, pkg, templates, conffile, notes):
    """Rewrite a Debian maintainer script body for apk."""
    names = {t["name"]: env_name(pkg, t["name"]) for t in templates}
    body = []
    uses_debconf = False
    for line in text.splitlines():
        s = line.strip()
        if s == "#DEBHELPER#":
            continue
        if re.match(r"^\.\s+/usr/share/debconf/confmodule\s*$", s):
            uses_debconf = True
            body.append("# debconf replaced by {}".format(conffile))
            body.append('[ -r "{0}" ] && . "{0}"'.format(conffile))
            continue
        if re.match(r"^db_(stop|go|capb|title|version)\b", s):
            continue
        m = re.match(r"^(\s*)db_get\s+(\S+)(.*)$", line)
        if m and m.group(2) in names:
            indent, q = m.group(1), m.group(2)
            t = next(t for t in templates if t["name"] == q)
            body.append('{}RET="${{{}:-{}}}"'.format(indent, names[q], t["default"]))
            continue
        if re.match(r"^\s*db_\w+", line):
            notes.append("{}: debconf call not converted: {}".format(kind, s))
            body.append("# {}: {}".format(TODO, s))
            continue
        for tool in DEBIAN_ONLY_TOOLS:
            if re.search(r"\b{}\b".format(re.escape(tool)), line):
                notes.append("{}: uses Debian-only tool '{}'".format(kind, tool))
                body.append("# {}: '{}' does not exist on Wolfi".format(TODO, tool))
                break
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
    ("Makefile", "makefile"),
]

BUILD_PIPELINES = {
    "cmake": ["cmake/configure", "cmake/build", "cmake/install"],
    "meson": ["meson/configure", "meson/compile", "meson/install"],
    "autoconf": ["autoconf/configure", "autoconf/make", "autoconf/make-install"],
    "pybuild": ["py/pip-build-install"],
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
                auto = self.dh_auto_command(rules.expand(line))
                if auto:
                    out.append(auto)
                    continue
                if re.match(r"^dh_auto_|^dh_(install|link)\b", line):
                    return None
                continue  # debhelper bookkeeping (Built-Using, substvars...)
            line = rules.expand(line)
            line = re.sub(r"(^|/|\s)(usr/lib)/\$[({]DEB_HOST_MULTIARCH[)}]", r"\1\2", line)
            for pkg, target in self.rename.items():
                if pkg != deb_pkg:
                    # files for another binary package: its melange output directory
                    line = re.sub(r"(?<![\w/])debian/{}/".format(re.escape(pkg)),
                                  "${{{{targets.outdir}}}}/{}/".format(target), line)
            for pkg in (deb_pkg, "tmp"):
                line = re.sub(r"\$\(CURDIR\)/debian/{}(/|\b)".format(re.escape(pkg)), "${{targets.destdir}}/", line)
                line = re.sub(r"(?<![\w/])debian/{}/".format(re.escape(pkg)), "${{targets.destdir}}/", line)
            line = re.sub(r"target/\$\(DEB_HOST_RUST_TYPE\)/", "target/", line)
            line = line.replace("$(CURDIR)/", "").replace("$(CURDIR)", ".")
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
            out.append(line)
        return out

    def dh_auto_command(self, line):
        """dh_auto_build/dh_auto_install [-- ARGS] for make-based builds, as shell."""
        sub = re.search(r"\s(?:-D\s*|--sourcedir(?:ectory)?[= ])(\S+)", line)
        if sub:
            line = line[:sub.start()] + line[sub.end():]
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
            chosen = None
            for alt in alts:
                if alt in DROP or alt.startswith(DROP_PREFIXES) or alt.startswith("${"):
                    chosen = ""
                    break
                if alt in self.rename:
                    chosen = (self.rename[alt], self.rename[alt], True)
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
            if chosen is None:
                # Nothing matched in the index: keep the best guess, flagged.
                chosen = (dep_candidates(alts[0])[0], alts[0], False)
            if not chosen:
                continue
            cand, alt, found = chosen
            if any(o == cand or (isinstance(o, C) and o.value == cand) for o in out):
                continue
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
            elif self.wolfi.community_only(cand):
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
        if not binaries:
            raise SystemExit("error: no binary package in debian/control")

        src_name, deb_version = parse_changelog(self.read("changelog") or "")
        src_name = src_name or source.get("source")
        fmt = (self.read("source/format") or "").strip()
        native = "native" in fmt or (deb_version is not None and "-" not in deb_version)
        rules = Rules(self.read("rules") or "")

        main = next((b for b in binaries if b["package"] == src_name), binaries[0])
        name = a.name or python_name(main["package"])
        self.rename = {b["package"]: b["package"] for b in binaries}
        if name != main["package"] and name == python_name(main["package"]):
            # python3-foo -> py3-foo, and python-foo-doc -> py3-foo-doc
            base = main["package"][len("python3-"):]
            for b in binaries:
                m = re.match(r"^python3?-{}(-.+)?$".format(re.escape(base)), b["package"])
                if m:
                    self.rename[b["package"]] = name + (m.group(1) or "")
        self.rename[main["package"]] = name
        self.recipe_dir = name
        if deb_version and re.search(r"[+~](dfsg|ds|repack)", deb_version) \
                and not files_excluded(self.read("copyright")):
            self.notes.append("Debian repacks the upstream tarball ({}); check debian/copyright "
                              "Files-Excluded before using the pristine upstream source".format(deb_version))

        # ---- version -----------------------------------------------------
        version_var = a.version_var
        if not version_var and native and not a.version:
            cands = [v for v in rules.vars if re.match(r"^[A-Z0-9_]*VERSION$", v)]
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

        runtime = self.map_deps(parse_relations(main.get("depends")) + parse_relations(main.get("pre-depends")), "runtime")
        if "${python3:Depends}" in (main.get("depends") or ""):
            reqs = python_requirements(self.tree)
            if reqs:
                self.notes.append("${python3:Depends} from upstream's requirements: " + ", ".join(reqs))
                runtime += self.map_deps([["python3-" + r] for r in reqs], "runtime")
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
        conffile = "/etc/{}.conf".format(name)
        scripts, uses_debconf = self.scriptlets(main, True, name, templates, conffile, templated, var_refs)
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
        if not bs:
            bs = next((b for f, b in BUILDSYSTEM_FILES if f in self.top), None)
        base = ["build-base", "busybox"] if bs else ["busybox"]
        if bs == "pybuild":
            base += ["python3", "py3-pip", "py3-wheel"]
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
        if not native:
            pipeline += self.fetch_step(source, version)
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
        self.python_module = rules.vars.get("PYBUILD_NAME") if bs == "pybuild" else None
        if bs == "pybuild" and not self.python_module:
            self.python_module = re.sub(r"^(py3|python3?)-", "", name).replace("-", "_")
        ported = {}
        for target in ("override_dh_auto_build", "override_dh_auto_install"):
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
        build_override = ported.get("override_dh_auto_build")
        install_override = ported.get("override_dh_auto_install")
        # cargo and go builds install nothing into debian/tmp; an
        # override_dh_auto_install replaces upstream's install step, and when
        # it installs into destdir the *.install files are already satisfied.
        self.upstream_installs = bs not in ("cargo", "golang") and (
            "override_dh_auto_install" not in overrides
            or bool(install_override and any("${{targets.destdir}}" in l or l == self.PIPELINE_MARK
                                             for l in install_override)))
        if bs in BUILD_PIPELINES and (build_override or install_override) and bs in ("cmake", "meson", "autoconf"):
            # configure as dh_auto_configure would, then the overrides
            if bs == "autoconf" and self.needs_autoreconf(source):
                pipeline.append({"runs": "autoreconf -fi\n"})
            opts = rules.configure_opts()
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
            opts = rules.configure_opts()
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
                cmds.append('make install DESTDIR="${{targets.destdir}}" PREFIX=/usr')
            if cmds:
                pipeline.append({"runs": "\n".join(cmds) + "\n"})
        elif bs and bs not in BUILD_PIPELINES:
            pipeline.append(self.todo("unsupported Debian build system '{}'".format(bs)))

        for with_ in rules.dh_with():
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
            if target.startswith(("override_dh_auto_test", "override_dh_strip", "override_dh_shlibdeps",
                                  "override_dh_makeshlibs", "override_dh_gencontrol", "override_dh_builddeb",
                                  "override_dh_dwz", "override_dh_installchangelogs", "override_dh_compress",
                                  "override_dh_missing", "override_dh_update_autotools_config",
                                  "override_dh_fixperms", "override_dh_lintian", "override_dh_usrlocal",
                                  "override_dh_installsystemd", "override_dh_installinit")):
                continue
            pipeline.append(self.todo("port debian/rules {}: {}".format(
                target, " && ".join(l.strip() for l in recipe if l.strip())[:200])))

        pipeline.append(self.install_step(main, True, native, name))
        if templates and uses_debconf:
            pipeline[-1]["runs"] += 'install -Dm644 {0}/{0}.conf "${{{{targets.destdir}}}}"{1}\n'.format(name, conffile)
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
    # build tree as <name>/, where they can clash with what upstream builds
    # (a program called <name>), so they are moved aside after the checkout.
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
        at = 0
        for i, st in enumerate(steps):
            if isinstance(st, dict) and st.get("uses") in ("fetch", "git-checkout"):
                at = i + 1
        return steps[:at] + [move] + steps[at:]

    # -- sections -----------------------------------------------------------

    def scriptlets(self, binary, is_main, name, templates, conffile, templated, var_refs):
        """Convert the maintainer scripts of one binary package."""
        scripts, uses_debconf = {}, False
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
            label = kind if is_main else "{}.{}".format(binary["package"], kind)
            body, dc = convert_script(text, label, name, templates if is_main else [], conffile, self.notes)
            if dc and not is_main:
                self.notes.append("{}: debconf in a subpackage is not converted".format(label))
            uses_debconf |= dc
            for target, argv in targets:
                scripts[target] = wrap_script(label, body, argv)
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
            repo, prefix = None, None
            if m:
                repo = "https://github.com/{}/{}".format(m.group(1), m.group(2))
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
                steps, notes = git_url_checkout_step(repo, version, prefix, resolve=self.args.download)
                tag = next(st["with"]["tag"] for st in steps if isinstance(st, dict))
                self.git_source = (repo, tag.replace("${{package.version}}", ""))
                self.notes += notes
                if not notes:
                    self.notes.append("upstream from debian/watch ({}), pinned to the tag's commit".format(
                        "GitHub" if gh else "git"))
                return steps
        if not url:
            cands = watch_tarball_urls(self.read("watch") or "", source.get("source", ""), version)
            if cands and self.args.download:
                # the first that exists
                url = next((c for c in cands if url_exists(c)), None)
            elif cands:
                url = cands[0]
            if url:
                self.notes.append("upstream tarball from debian/watch")
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
                src = self.debian_file(src)
                target = '"{}/{}/{}"'.format(destdir, dst, rename) if rename else '"{}/{}/"'.format(destdir, dst)
                if from_tree:
                    cmds.append('mkdir -p "{0}/{1}"\ncp -a {2} {3}'.format(destdir, dst, src, target))
                else:
                    cmds.append('mkdir -p "{0}/{1}"\nmv {2} {3}'.format(
                        destdir, dst, shell_path("${{targets.destdir}}", src), target))
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
            parts = line.split()
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
        for line in (self.pkgfile(binary["package"], "docs", main) or "").splitlines():
            doc = line.split("#", 1)[0].strip()
            if doc and native:
                cmds.append('install -Dm644 {} -t "{}"'.format(doc, docdir))
            elif doc:
                # dh_installdocs takes them from the source tree; may be directories
                cmds.append('mkdir -p "{0}"\ncp -a {1} "{0}/"'.format(docdir, doc))
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
        if cmds:
            sub["pipeline"] = [{"runs": "\n".join(cmds) + "\n"}]
        elif b["package"].endswith("-dev"):
            sub["pipeline"] = [{"uses": "split/dev"}]
        elif b["package"].endswith("-doc") and self.bs not in ("pybuild",):
            sub["pipeline"] = [{"uses": "split/manpages"}]
        else:
            sub["pipeline"] = [self.todo("no debian/{}.install; define which files go to this subpackage".format(b["package"])),
                               {"runs": "true\n"}]
        deps = self.map_deps(parse_relations(b.get("depends")), "runtime")
        if deps:
            sub["dependencies"] = {"runtime": deps}
        scripts, _ = self.scriptlets(b, False, name, [], "", {}, {})
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
        project = release_monitoring_id(source.get("source", ""), self.version) if self.args.download else None
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
        for i, para in enumerate(parse_deb822(control)):
            restrictions = para.get("restrictions", "").replace(",", " ").split()
            for r in restrictions:
                if r in ("isolation-machine", "breaks-testbed", "needs-reboot"):
                    self.notes.append("autopkgtest restriction '{}' cannot be honoured by melange test".format(r))
            deps = [d for d in parse_relations(para.get("depends", "@")) if d[0] not in ("@", "@builddeps@")]
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
            if "@builddeps@" in para.get("depends", ""):
                self.notes.append("autopkgtest uses @builddeps@; add the build dependencies to the test environment")
            env = 'export AUTOPKGTEST_TMP="$(mktemp -d)"\n'
            if "test-command" in para:
                steps.append({"name": "autopkgtest: {}".format(para["test-command"].split("\n")[0][:60]),
                              "runs": env + para["test-command"].strip() + "\n"})
            for test in para.get("tests", "").split():
                script = self.read(os.path.join(para.get("tests-directory", "tests"), test))
                if script is None:
                    continue
                shell = "bash" if script.startswith("#!/bin/bash") or script.startswith("#!/usr/bin/env bash") else "sh"
                if shell == "bash" and "bash" not in packages:
                    packages.append("bash")
                steps.append({"name": "autopkgtest: " + test,
                              "runs": env + 'cd "$AUTOPKGTEST_TMP"\n' + script.split("\n", 1)[1 if script.startswith("#!") else 0].strip() + "\n"})
        real = [st for st in steps if not isinstance(st, Comment)]
        if real:
            self.notes.append("autopkgtests converted to the test pipeline ({} steps)".format(len(real)))
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
        url = toks[0].rstrip("/") + "/" + toks[1] if len(toks) > 1 and "/" not in toks[1] else toks[0]
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
        print("error: network: {}".format(exc), file=sys.stderr)
        return 2
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
