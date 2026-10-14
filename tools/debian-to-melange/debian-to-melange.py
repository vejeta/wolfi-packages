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
import sys
import tempfile
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
    "sensible-utils", "base-files", "base-passwd",
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
    "pkgconf": "pkgconf-dev",
    "ca-certificates": "ca-certificates-bundle",
    "golang-go": "go",
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
    "libglib2.0-bin": "glib",
    "adduser": "shadow",
    "procps": "procps",
    "xz-utils": "xz",
    "bzip2": "bzip2",
    "openssl": "openssl",
    "nodejs": "nodejs",
    "npm": "npm",
}


def dep_candidates(name):
    """Ordered Wolfi name candidates for a Debian package name."""
    if name in NAME_MAP:
        return [NAME_MAP[name]]
    cands = [name]
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
        self.names = self._load(mod, mod.WOLFI_INDEX.format(arch=arch))
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
            out.append(SPDX_MAP.get(low, tok.strip()))
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
            target = None
            if not line.strip() or line.lstrip().startswith("#"):
                continue
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


def norm_path(path):
    """Debian multiarch paths -> Wolfi paths (usr/lib/<triplet>/ -> usr/lib/)."""
    path = path.strip("/")
    return re.sub(r"(^|/)lib/(?:\*|\$[({]DEB_HOST_MULTIARCH[)}]|[a-z0-9_]+-linux-gnu[a-z]*)(/|$)",
                  r"\1lib\2", path).rstrip("/")


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


def fetch_from_debian(spec, dest):
    """Download debian/ of a source package from sources.debian.org into dest.

    Returns (source_tree_dir, top-level file names, version).
    """
    name, _, version = spec.partition("=")
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

BUILDSYSTEM_FILES = [
    ("meson.build", "meson"),
    ("CMakeLists.txt", "cmake"),
    ("configure.ac", "autoconf"),
    ("configure", "autoconf"),
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
                if re.match(r"^dh_auto_|^dh_(install|link)\b", line):
                    return None
                continue  # debhelper bookkeeping (Built-Using, substvars...)
            line = rules.expand(line)
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

    SKIP_EXPORTS = {"PATH", "CARGO_HOME", "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS",
                    "DH_VERBOSE", "PYBUILD_NAME", "GOCACHE", "GOPATH", "HOME"}

    def ported_exports(self, rules):
        env = {}
        for var in rules.exports:
            if var.startswith(("DEB_", "DH_")) or var in self.SKIP_EXPORTS or var not in rules.vars:
                continue
            value = rules.expand(rules.vars[var]).replace("$(CURDIR)", "/home/build")
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
                for cand in dep_candidates(alt):
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
            if found is False:
                self.notes.append("{} dependency '{}' (Debian '{}') not found in Wolfi".format(kind, cand, alt))
                out.append(C(cand, "{}: not in Wolfi (Debian: {})".format(TODO, alt)))
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
        name = a.name or main["package"]
        self.rename = {b["package"]: b["package"] for b in binaries}
        self.rename[main["package"]] = name
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
                else:
                    key = var.lower().replace("_", "-")
                    melange_vars[key] = rules.expand(rules.vars.get(var, ""))
                    var_refs[var] = "${{vars.%s}}" % key

        # ---- package ------------------------------------------------------
        desc = main.get("description", "").split("\n", 1)[0].strip()
        desc = desc[:1].upper() + desc[1:]
        pkg = {"name": name, "version": version, "epoch": 0, "description": desc}
        lics = parse_copyright(self.read("copyright"))
        if lics:
            pkg["copyright"] = []
            for lic, files in lics:
                entry = {"license": lic}
                if files != ["*"]:
                    entry["paths"] = files
                pkg["copyright"].append(entry)
        else:
            pkg["copyright"] = [{"license": "NOASSERTION"}]
            pkg["copyright"].insert(0, self.todo("debian/copyright is not machine-readable (DEP-5); set the SPDX license"))

        runtime = self.map_deps(parse_relations(main.get("depends")) + parse_relations(main.get("pre-depends")), "runtime")
        recommends = [x[0] for x in parse_relations(main.get("recommends"))]
        if runtime or recommends:
            deps = {"runtime": runtime} if runtime else {}
            if recommends:
                deps = dict(deps)
                deps.setdefault("runtime", [])
                deps["runtime"].append(Comment("Debian Recommends (not supported by apk): " + ", ".join(recommends)))
            pkg["dependencies"] = deps

        # ---- maintainer scripts + debconf ----------------------------------
        templates = parse_templates(self.read("templates"))
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
        bs = rules.buildsystem()
        if not bs:
            bs = next((b for f, b in BUILDSYSTEM_FILES if f in self.top), None)
        base = ["build-base", "busybox"] if bs else ["busybox"]
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
        # cargo and go builds install nothing into debian/tmp, and an
        # override_dh_auto_install replaces upstream's install step.
        self.upstream_installs = bs not in ("cargo", "golang") and "override_dh_auto_install" not in overrides
        ported = {}
        for target in ("override_dh_auto_build", "override_dh_auto_install"):
            if target in overrides:
                ported[target] = self.port_recipe(rules, overrides[target], name, main["package"])
        build_override = ported.get("override_dh_auto_build")
        if build_override:
            pipeline.append({"name": "Build (from debian/rules override_dh_auto_build)",
                             "runs": "\n".join(build_override) + "\n"})
        elif bs in BUILD_PIPELINES:
            opts = rules.configure_opts()
            for i, step in enumerate(BUILD_PIPELINES[bs]):
                entry = {"uses": step}
                if i == 0 and opts:
                    entry["with"] = {"opts": " ".join(opts)}
                pipeline.append(entry)
            if bs in ("pybuild", "golang", "cargo") and "override_dh_auto_build" not in overrides:
                pipeline.append(self.todo("review the {} pipeline inputs (Debian used dh --buildsystem={})".format(BUILD_PIPELINES[bs][0], bs)))
        elif bs == "makefile":
            pipeline.append({"runs": 'make -j$(nproc)\nmake install DESTDIR="${{targets.destdir}}" PREFIX=/usr\n'})
        elif bs:
            pipeline.append(self.todo("unsupported Debian build system '{}'".format(bs)))

        for with_ in rules.dh_with():
            self.notes.append("dh --with {} has no direct melange equivalent; review".format(with_))
        skip_overrides = {"override_dh_installdeb", "override_dh_clean", "override_dh_auto_configure",
                          "override_dh_auto_clean"}
        for target, recipe in overrides.items():
            if target in skip_overrides and (target != "override_dh_installdeb" or templated):
                continue
            if ported.get(target):
                if target == "override_dh_auto_install":
                    pipeline.append({"name": "Install (from debian/rules override_dh_auto_install)",
                                     "runs": "\n".join(ported[target]) + "\n"})
                continue
            if target.startswith(("override_dh_auto_test", "override_dh_strip", "override_dh_shlibdeps",
                                  "override_dh_makeshlibs", "override_dh_gencontrol", "override_dh_builddeb",
                                  "override_dh_dwz")):
                continue
            pipeline.append(self.todo("port debian/rules {}: {}".format(
                target, " && ".join(l.strip() for l in recipe if l.strip())[:200])))

        pipeline.append(self.install_step(main, True, native, name))
        if templates and uses_debconf:
            pipeline[-1]["runs"] += 'install -Dm644 {0}/{0}.conf "${{{{targets.destdir}}}}"{1}\n'.format(name, conffile)

        # ---- subpackages --------------------------------------------------
        subpackages = []
        for b in binaries:
            if b is main:
                continue
            subpackages.append(self.subpackage(b, name, main))

        # ---- copy debian/copyright for /usr/share/doc --------------------
        if self.read("copyright") is not None:
            self.aux["copyright"] = self.read("copyright")

        # ---- update -------------------------------------------------------
        update = self.update_section(source, native, version_var)

        # ---- test ---------------------------------------------------------
        test = self.test_section(main, name, conffile if (templates and uses_debconf) else None)

        recipe = {"package": pkg}
        if melange_vars:
            recipe["vars"] = melange_vars
        recipe["environment"] = environment
        recipe["pipeline"] = [p for p in pipeline if p]
        if subpackages:
            recipe["subpackages"] = subpackages
        recipe["update"] = update
        recipe["test"] = test
        return name, recipe, self.header(src_name, deb_version, source, native, fmt)

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
            if m:
                url = "https://github.com/{}/{}/archive/refs/tags/v${{{{package.version}}}}.tar.gz".format(m.group(1), m.group(2))
                self.notes.append("upstream URL guessed from debian/watch (GitHub); verify the tag format")
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
        if inst and main and not native and not self.upstream_installs:
            # Nothing was installed by the upstream build system, so dh_install
            # takes these paths from the source tree.
            for line in inst.splitlines():
                parts = line.split("#", 1)[0].split()
                if not parts:
                    continue
                src = norm_path(parts[0])
                dst = os.path.dirname(src) if len(parts) == 1 else norm_path(parts[-1])
                cmds.append('mkdir -p "{0}/{1}"\ncp -a {2} "{0}/{1}/"'.format(destdir, dst, src))
            inst = None
        # Upstream builds install straight into destdir; only subpackages
        # (and native packages, which copy from the source tree) move files.
        if inst and (native or not main):
            for line in inst.splitlines():
                parts = line.split("#", 1)[0].split()
                if not parts:
                    continue
                if len(parts) == 1:
                    src = norm_path(parts[0])
                    dst = os.path.dirname(src)
                else:
                    src, dst = (parts[0] if native else norm_path(parts[0])), norm_path(parts[-1])
                if native:
                    cmds.append('mkdir -p "{0}/{1}"\ncp -a {2} "{0}/{1}/"'.format(destdir, dst, src))
                else:
                    cmds.append('mkdir -p "{0}/{1}"\nmv {2} "{0}/{1}/"'.format(
                        destdir, dst, shell_path("${{targets.destdir}}", src)))
        for line in (self.pkgfile(binary["package"], "manpages", main) or "").splitlines():
            page = line.split("#", 1)[0].strip()
            m = re.search(r"\.(\d)\w*(\.gz)?$", page)
            if page and m:
                cmds.append('install -Dm644 {0} -t "{1}/usr/share/man/man{2}"'.format(page, destdir, m.group(1)))
        for line in (self.pkgfile(binary["package"], "dirs", main) or "").splitlines():
            if line.strip():
                cmds.append('mkdir -p "{}/{}"'.format(destdir, norm_path(line)))
        for line in (self.pkgfile(binary["package"], "links", main) or "").splitlines():
            parts = line.split()
            if len(parts) == 2:
                target, link = norm_path(parts[0]), norm_path(parts[1])
                cmds.append('mkdir -p "{0}/{2}"\nln -sf /{1} "{0}/{3}"'.format(
                    destdir, target, os.path.dirname(link), link))
        for line in (self.pkgfile(binary["package"], "docs", main) or "").splitlines():
            if line.strip() and native:
                cmds.append('install -Dm644 {} -t "{}/usr/share/doc/{}"'.format(line.strip(), destdir, binary["package"]))
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

    def install_step(self, binary, main, native, name):
        dest = "${{targets.destdir}}"
        cmds = self.install_lines(binary, main, native, dest)
        cmds.append('install -Dm644 {0}/copyright "{1}"/usr/share/doc/{0}/copyright'.format(name, dest))
        return {"name": "Install files", "runs": "\n".join(cmds) + "\n"}

    def subpackage(self, b, name, main):
        desc = b.get("description", "").split("\n", 1)[0].strip()
        sub = {"name": b["package"], "description": desc[:1].upper() + desc[1:]}
        cmds = self.install_lines(b, False, False, "${{targets.contextdir}}")
        if cmds:
            sub["pipeline"] = [{"runs": "\n".join(cmds) + "\n"}]
        elif b["package"].endswith("-dev"):
            sub["pipeline"] = [{"uses": "split/dev"}]
        elif b["package"].endswith("-doc"):
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
        if m:
            return {"enabled": True, "github": {"identifier": "{}/{}".format(m.group(1), m.group(2)),
                                                "strip-prefix": "v"}}
        return {"enabled": True,
                "release-monitor": {"identifier": C(0, "{}: set the release-monitoring.org project id".format(TODO))}}

    def test_section(self, binary, name, conffile, main=True):
        cmds = []
        inst = self.pkgfile(binary["package"], "install", main) or ""
        for line in inst.splitlines():
            parts = line.split()
            if parts and ("usr/bin/" in line or "usr/sbin/" in line):
                tool = os.path.basename(parts[0])
                cmds.append("{0} --version || {0} --help".format(tool))
        if not main and not cmds:
            return None
        if main:
            cmds.append("test -f /usr/share/doc/{}/copyright".format(name))
        if conffile:
            cmds.append("test -f {}".format(conffile))
        return {"environment": {"contents": {"packages": ["busybox"]}},
                "pipeline": [{"runs": "\n".join(cmds) + "\n"}]}


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
    p.add_argument("--check-wolfi", action="store_true",
                   help="verify mapped dependency names against the Wolfi APKINDEX")
    p.add_argument("--strict", action="store_true", help="exit 1 if anything needs manual review")
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
        text = write_output(name, recipe, header, conv.aux, args.out, args.stdout)
        for n in conv.notes:
            print("note: " + n, file=sys.stderr)
        return 1 if args.strict and TODO in text else 0
    except urllib.error.URLError as exc:
        print("error: network: {}".format(exc), file=sys.stderr)
        return 2
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
