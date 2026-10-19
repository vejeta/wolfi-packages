#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""melange-to-debian: generate a debian/ directory from a melange recipe.

    melange-to-debian packages/libxmlb.yaml --out ~/src/libxmlb
    melange-to-debian packages/stremio.yaml --maintainer "Name <me@example.org>"

Writes control, rules, changelog, copyright (DEP-5), watch, source/format,
upstream/metadata, patches/ with series, one .install file per binary
package and autopkgtests from the recipe's test pipelines.

The result is a starting point for an ITP, not a finished package: things
that cannot be derived from a melange recipe (copyright holders, long
descriptions, SONAME-based library package names) are marked with
"TODO(melange-to-debian)" and listed on stderr.

Needs PyYAML (python3-yaml). Shares the Debian <-> Wolfi name and license
tables of tools/debian-to-melange.
"""

import argparse
import datetime
import email.utils
import importlib.util
import os
import re
import shutil
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("error: PyYAML is required (apt install python3-yaml)")

__version__ = "0.1.0"

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "debian_to_melange", os.path.join(HERE, "..", "debian-to-melange", "debian-to-melange.py"))
d2m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d2m)

_pc_spec = importlib.util.spec_from_file_location(
    "pkg_check", os.path.join(HERE, "..", "pkg-check", "pkg-check.py"))
pkg_check = importlib.util.module_from_spec(_pc_spec)
_pc_spec.loader.exec_module(pkg_check)

TODO = "TODO(melange-to-debian)"
STANDARDS_VERSION = "4.7.2"
DEBHELPER_COMPAT = "13"

# ==========================================================================
# Wolfi -> Debian names
# ==========================================================================

# Implicit in a Debian build (build-essential) or not needed.
DROP = {"build-base", "busybox", "wolfi-base", "cargo-auditable", "ca-certificates-bundle",
        "glib-gir", "posix-libc-utils", "coreutils"}

# Preferred Debian name where the reverse of debian-to-melange's table is
# ambiguous or missing.
PREFERRED = {
    "pkgconf-dev": "pkgconf",
    "pkgconf": "pkgconf",
    "ninja": "ninja-build",
    "rust": "cargo",
    "go": "golang-go",
    "glib-dev": "libglib2.0-dev",
    "glib": "libglib2.0-bin",
    "gobject-introspection-dev": "gobject-introspection",
    "gtk-4-dev": "libgtk-4-dev",
    "gtk-3-dev": "libgtk-3-dev",
    "mesa-dev": "libgl-dev",
    "mesa-gbm": "libgbm1",
    "openssl-dev": "libssl-dev",
    "curl-dev": "libcurl4-openssl-dev",
    "zlib-dev": "zlib1g-dev",
    "xz-dev": "liblzma-dev",
    "bzip2-dev": "libbz2-dev",
    "util-linux-dev": "uuid-dev",
    "ffmpeg-dev": "libavcodec-dev",
    "python3": "python3",
    "python3-dev": "python3-dev",
    "ca-certificates": "ca-certificates",
    "wayland-dev": "libwayland-dev",
    "gtk-4-compiled-gschemas": None,  # Debian compiles schemas with a trigger
    "openjdk-25-default-jdk": "default-jdk",
    "openjdk-25-default-jvm": "default-jre",
    "mpv-dev": "libmpv-dev",
    "libadwaita-dev": "libadwaita-1-dev",
    "libsoup3-dev": "libsoup-3.0-dev",
    "libsecret-dev": "libsecret-1-dev",
    "libgcrypt-dev": "libgcrypt20-dev",
    "libxslt-dev": "libxslt1-dev",
    "gstreamer-dev": "libgstreamer1.0-dev",
    "gst-plugins-base-dev": "libgstreamer-plugins-base1.0-dev",
    "gst-plugins-bad-dev": "libgstreamer-plugins-bad1.0-dev",
    "enchant2-dev": "libenchant-2-dev",
    "openjpeg-dev": "libopenjp2-7-dev",
    "pango-dev": "libpango1.0-dev",
    "woff2-dev": "libwoff-dev",
    "lcms2-dev": "liblcms2-dev",
    "harfbuzz-dev": "libharfbuzz-dev",
    "webkitgtk-6.0-dev": "libwebkitgtk-6.0-dev",
    "libxml2-dev": "libxml2-dev",
    "gnutls-dev": "libgnutls28-dev",
    "ldd-check": None,  # melange test helper
}

# Tools that are already named the same in both distributions.
SAME = {"meson", "cmake", "make", "autoconf", "automake", "libtool", "gettext", "bison", "flex",
        "perl", "nodejs", "npm", "git", "gperf", "patch", "wayland-protocols", "xz", "zstd",
        "bubblewrap", "xdg-dbus-proxy", "unzip", "ruby", "clang", "lld", "llvm", "unifdef",
        "dbus", "glib-networking", "python3-dev"}


def _reverse_name_map():
    rev = {}
    for deb, wolfi in d2m.NAME_MAP.items():
        # a Debian package may map to several Wolfi ones (xvfb -> xvfb-run, xkbcomp, ...)
        for w in (wolfi if isinstance(wolfi, list) else [wolfi]):
            rev.setdefault(w, deb)
    return rev


REVERSE = _reverse_name_map()


def debian_name(wolfi):
    """Return (debian_name or None, how) for a Wolfi package name."""
    name = re.split(r"[=<>~]", wolfi, maxsplit=1)[0].strip()
    if name in DROP:
        return None, "dropped"
    if name in PREFERRED:
        return PREFERRED[name], "table"
    if name in SAME:
        return name, "same"
    if name in REVERSE:
        return REVERSE[name], "table"
    m = re.match(r"^openjdk-(\d+)(?:-default-jdk)?$", name)
    if m:
        return "openjdk-{}-jdk".format(m.group(1)), "table"
    m = re.match(r"^py3-(.+)$", name)
    if m:
        return "python3-" + m.group(1), "rule"
    m = re.match(r"^perl-(.+)$", name)
    if m:
        return "lib{}-perl".format(m.group(1)), "rule"
    m = re.match(r"^ruby-[\d.]+$", name)
    if m:
        return "ruby", "rule"
    if name.endswith("-dev") and not name.startswith("lib"):
        return "lib" + name, "guess"
    if name.startswith("lib") and name.endswith("-dev"):
        return name, "same-name"
    return name, "guess"


# ==========================================================================
# Licenses: SPDX -> Debian short names (DEP-5)
# ==========================================================================

DEBIAN_LICENSE = {
    "GPL-1.0-only": "GPL-1", "GPL-1.0-or-later": "GPL-1+",
    "GPL-2.0-only": "GPL-2", "GPL-2.0-or-later": "GPL-2+",
    "GPL-3.0-only": "GPL-3", "GPL-3.0-or-later": "GPL-3+",
    "LGPL-2.0-only": "LGPL-2", "LGPL-2.0-or-later": "LGPL-2+",
    "LGPL-2.1-only": "LGPL-2.1", "LGPL-2.1-or-later": "LGPL-2.1+",
    "LGPL-3.0-only": "LGPL-3", "LGPL-3.0-or-later": "LGPL-3+",
    "AGPL-3.0-only": "AGPL-3", "AGPL-3.0-or-later": "AGPL-3+",
    "MIT": "Expat", "BSD-2-Clause": "BSD-2-clause", "BSD-3-Clause": "BSD-3-clause",
    "Apache-2.0": "Apache-2.0", "MPL-1.1": "MPL-1.1", "MPL-2.0": "MPL-2.0",
    "ISC": "ISC", "Zlib": "Zlib", "Artistic-1.0-Perl": "Artistic", "CC0-1.0": "CC0-1.0",
    "WTFPL": "WTFPL", "BSL-1.0": "BSL-1.0", "Unlicense": "Unlicense",
}

# Licenses whose text is in /usr/share/common-licenses on every Debian system.
COMMON_LICENSES = {
    "GPL-1": "GPL-1", "GPL-1+": "GPL-1", "GPL-2": "GPL-2", "GPL-2+": "GPL-2",
    "GPL-3": "GPL-3", "GPL-3+": "GPL-3", "LGPL-2": "LGPL-2", "LGPL-2+": "LGPL-2",
    "LGPL-2.1": "LGPL-2.1", "LGPL-2.1+": "LGPL-2.1", "LGPL-3": "LGPL-3", "LGPL-3+": "LGPL-3",
    "Apache-2.0": "Apache-2.0", "MPL-1.1": "MPL-1.1", "MPL-2.0": "MPL-2.0",
    "CC0-1.0": "CC0-1.0", "Artistic-1.0-Perl": "Artistic",
}


def wrap(text, width=79, indent=" "):
    words, lines, line = text.split(), [], ""
    for w in words:
        if line and len(line) + 1 + len(w) > width - len(indent):
            lines.append(indent + line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        lines.append(indent + line)
    return "\n".join(lines)


LICENSE_TEXT = {
    "Expat": wrap(
        "Permission is hereby granted, free of charge, to any person obtaining a copy of this "
        "software and associated documentation files (the \"Software\"), to deal in the Software "
        "without restriction, including without limitation the rights to use, copy, modify, "
        "merge, publish, distribute, sublicense, and/or sell copies of the Software, and to "
        "permit persons to whom the Software is furnished to do so, subject to the following "
        "conditions:") + "\n .\n" + wrap(
        "The above copyright notice and this permission notice shall be included in all copies "
        "or substantial portions of the Software.") + "\n .\n" + wrap(
        "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, "
        "INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A "
        "PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT "
        "HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF "
        "CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE "
        "OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."),
    "ISC": wrap(
        "Permission to use, copy, modify, and/or distribute this software for any purpose with "
        "or without fee is hereby granted, provided that the above copyright notice and this "
        "permission notice appear in all copies.") + "\n .\n" + wrap(
        "THE SOFTWARE IS PROVIDED \"AS IS\" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD "
        "TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO "
        "EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL "
        "DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER "
        "IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN "
        "CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE."),
}


def to_debian_license(spdx):
    """Convert an SPDX expression to a DEP-5 expression."""
    out = []
    for tok in re.split(r"(\s+(?:AND|OR|WITH)\s+|[()])", spdx.strip()):
        t = tok.strip()
        if t in ("AND", "OR", "WITH"):
            out.append(" {} ".format(t.lower()))
        elif t in ("(", ")"):
            out.append(t)
        elif t:
            out.append(DEBIAN_LICENSE.get(t, t))
    return "".join(out)


def license_names(expr):
    return [t for t in re.split(r"\s+(?:and|or|with)\s+|[()]", expr) if t.strip()]


# ==========================================================================
# Recipe helpers
# ==========================================================================

def substitute(text, recipe):
    pkg = recipe.get("package", {})
    vars_ = dict(recipe.get("vars") or {})
    text = str(text)
    text = text.replace("${{package.version}}", str(pkg.get("version", "")))
    text = text.replace("${{package.name}}", str(pkg.get("name", "")))
    for k, v in vars_.items():
        text = text.replace("${{vars.%s}}" % k, str(v))
    return text


def github_repo(recipe):
    """Return 'owner/repo' if the upstream is on GitHub."""
    gh = (recipe.get("update") or {}).get("github") or {}
    if gh.get("identifier"):
        return gh["identifier"]
    for step in recipe.get("pipeline") or []:
        w = step.get("with") or {}
        url = w.get("repository") or w.get("uri") or ""
        m = re.match(r"https://github\.com/([^/]+)/([^/.]+)", url)
        if m:
            return "{}/{}".format(m.group(1), m.group(2))
    return None


def homepage(recipe):
    gh = github_repo(recipe)
    if gh:
        return "https://github.com/" + gh
    for step in recipe.get("pipeline") or []:
        url = (step.get("with") or {}).get("uri") or (step.get("with") or {}).get("repository")
        if url:
            m = re.match(r"(https?://[^/]+)", url)
            if m:
                return m.group(1)
    return None


def patch_files(recipe, recipe_dir):
    """Patch paths from 'uses: patch' steps, relative to the recipe directory."""
    out = []
    for step in recipe.get("pipeline") or []:
        if step.get("uses") != "patch":
            continue
        w = step.get("with") or {}
        patches = w.get("patches") or w.get("series") or ""
        if isinstance(patches, str):
            patches = patches.split()
        for p in patches:
            out.append(os.path.join(recipe_dir, p))
    return out


DESTDIR_RE = re.compile(r"\$\{\{targets\.(?:destdir|contextdir)\}\}/?([^\s\"']*)")


def paths_in(script):
    """Paths below the install root that a melange script touches."""
    return [p.rstrip("/") for p in DESTDIR_RE.findall(script or "") if p.strip("/")]


# ==========================================================================
# Converter
# ==========================================================================

BUILDSYSTEMS = {
    "meson/configure": "meson",
    "cmake/configure": "cmake",
    "autoconf/configure": "autoconf",
    "cargo/build": "cargo",
    "go/build": "golang",
    "py/pip-build-install": "pybuild",
}

SKIPPED_USES = {"fetch", "git-checkout", "patch", "strip", "meson/compile", "meson/install",
                "cmake/build", "cmake/install", "autoconf/make", "autoconf/make-install"}

GENERATED = {"control", "rules", "copyright", "changelog", "watch", "source", "tests", "patches"}

CONTROL_KEYWORDS = re.compile(r"^\s*(if|for|while|case|until)\b|\(\)\s*\{\s*$")


class Converter:
    def __init__(self, recipe, recipe_path, maintainer, check_debian=False):
        self.recipe = recipe
        self.recipe_dir = os.path.splitext(recipe_path)[0]
        self.recipe_base = os.path.dirname(os.path.abspath(recipe_path))
        self.pkg = recipe["package"]
        self.name = self.pkg["name"]
        self.version = str(self.pkg["version"])
        self.maintainer = maintainer
        self.check_debian = check_debian
        self.debian_cache = {}
        self.notes = []
        self.files = {}
        self.copies = {}

    def note(self, msg):
        if msg not in self.notes:
            self.notes.append(msg)

    # -- dependencies -----------------------------------------------------

    def in_debian(self, name):
        if name not in self.debian_cache:
            args = argparse.Namespace(cache=True, debian_suite="unstable", verbose=False)
            res = pkg_check.check_debian(name, args)
            self.debian_cache[name] = None if res.error else res.found
        return self.debian_cache[name]

    def own_binaries(self):
        return {self.name} | {s.get("name") for s in self.recipe.get("subpackages") or []}

    def map_deps(self, names, what):
        out = []
        own = self.own_binaries()
        for n in names or []:
            base = re.split(r"[=<>~]", str(n), maxsplit=1)[0].strip()
            if base in own:
                if what == "runtime dependency":
                    out.append("{} (= ${{binary:Version}})".format(base))
                continue  # tests get the package's own binaries through "@"
            deb, how = debian_name(str(n))
            if deb is None:
                continue
            if self.check_debian and how != "table":
                found = self.in_debian(deb)
                if found is False:
                    self.note("{} '{}' -> '{}': not found in Debian".format(what, n, deb))
            elif how == "guess":
                self.note("{} '{}' mapped to '{}' by name only; check it exists in Debian".format(what, n, deb))
            if deb not in out:
                out.append(deb)
        return out

    def buildsystem(self):
        for step in self.recipe.get("pipeline") or []:
            bs = BUILDSYSTEMS.get(step.get("uses", ""))
            if bs:
                return bs, step
        return None, None

    # -- control ----------------------------------------------------------

    def binary_packages(self):
        """[(name, kind, description, recipe_subpackage or None)]"""
        out = [(self.name, "main", self.pkg.get("description", ""), None)]
        for sub in self.recipe.get("subpackages") or []:
            sname = sub.get("name", "")
            uses = [s.get("uses", "") for s in sub.get("pipeline") or []]
            if "split/debug" in uses or sname.endswith("-dbg"):
                self.note("subpackage {}: debug symbols come from Debian's automatic -dbgsym".format(sname))
                continue
            if "split/locales" in uses or sname.endswith("-lang"):
                self.note("subpackage {}: translations stay in {} (Debian rarely splits them)".format(sname, self.name))
                continue
            if sname.endswith("-dev") or "split/dev" in uses:
                kind = "dev"
            elif sname.endswith("-doc") or any(u in ("split/manpages", "split/alldocs") for u in uses):
                kind = "doc"
            else:
                kind = "other"
            out.append((sname, kind, sub.get("description", ""), sub))
        return out

    def control(self, binaries, build_deps):
        bs, _ = self.buildsystem()
        bd = ["debhelper-compat (= {})".format(DEBHELPER_COMPAT)]
        extra = {"cargo": ["dh-cargo"], "golang": ["dh-golang", "golang-any"],
                 "pybuild": ["dh-python", "python3-all", "pybuild-plugin-pyproject"]}.get(bs, [])
        for d in extra + build_deps:
            if d not in bd:
                bd.append(d)
        lines = ["Source: " + self.name,
                 "Section: misc",
                 "Priority: optional",
                 "Maintainer: " + self.maintainer,
                 "Build-Depends:"]
        lines += [" {},".format(d) for d in bd[:-1]] + [" " + bd[-1]]
        lines += ["Standards-Version: " + STANDARDS_VERSION]
        hp = homepage(self.recipe)
        if hp:
            lines.append("Homepage: " + hp)
        lines += ["Vcs-Browser: https://salsa.debian.org/debian/" + self.name,
                  "Vcs-Git: https://salsa.debian.org/debian/{}.git".format(self.name),
                  "Rules-Requires-Root: no"]
        runtime = self.map_deps((self.pkg.get("dependencies") or {}).get("runtime"), "runtime dependency")
        for name, kind, desc, _ in binaries:
            lines += ["", "Package: " + name]
            if kind == "dev":
                lines += ["Section: libdevel", "Architecture: any", "Multi-Arch: same",
                          "Depends: {} (= ${{binary:Version}}), ${{misc:Depends}}".format(self.name)]
            elif kind == "doc":
                lines += ["Section: doc", "Architecture: all", "Multi-Arch: foreign",
                          "Depends: ${misc:Depends}"]
            else:
                deps = ["${shlibs:Depends}", "${misc:Depends}"] + (runtime if kind == "main" else [])
                lines += ["Architecture: any", "Depends: " + ", ".join(deps)]
            lines.append("Description: " + (desc or TODO))
            lines.append(" {} long description.".format(TODO))
        if any(k == "dev" for _, k, _, _ in binaries) and self.name.startswith("lib"):
            self.note("library package '{}' should be named after its SONAME (e.g. {}1)".format(self.name, self.name))
        return "\n".join(lines) + "\n"

    # -- rules ------------------------------------------------------------

    def local_files(self, script):
        """Files of packages/NAME/ used by a script -> copy to debian/, rewrite the path."""
        prefix = os.path.basename(self.recipe_dir) + "/"
        for m in re.findall(r"(?<![\w./-])" + re.escape(prefix) + r"([\w.+-]+)", script):
            src = os.path.join(self.recipe_dir, m)
            if os.path.isfile(src) and not m.endswith((".patch", ".diff")) and m not in GENERATED:
                self.copies[m] = src
                script = re.sub(r"(?<![\w./-])" + re.escape(prefix + m), "debian/" + m, script)
        return script

    def make_lines(self, script):
        """Melange shell -> make recipe lines (returns None if it needs a manual port)."""
        script = self.local_files(substitute(script, self.recipe))
        script = re.sub(r"\$\{\{targets\.(?:destdir|contextdir)\}\}", "$(DESTDIR)", script)
        if "${{" in script or any(CONTROL_KEYWORDS.search(l) for l in script.splitlines()):
            return None
        out = []
        for line in script.splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            if re.search(r"usr/share/doc/[^/\s]+/copyright", line):
                continue  # dh_installdocs installs debian/copyright
            line = line.replace("$", "$$").replace("$$(DESTDIR)", "$(DESTDIR)")
            out.append("\t" + line.strip())
        return out

    def rules(self, multi):
        bs, step = self.buildsystem()
        dh_opts = {"meson": " --buildsystem=meson", "cmake": " --buildsystem=cmake",
                   "cargo": " --buildsystem=cargo", "golang": " --builddirectory=_build --buildsystem=golang",
                   "pybuild": " --buildsystem=pybuild"}.get(bs, "")
        out = ["#!/usr/bin/make -f", "",
               "export DEB_BUILD_MAINT_OPTIONS = hardening=+all", "",
               "DESTDIR = $(CURDIR)/debian/{}".format("tmp" if multi else self.name), "",
               "%:", "\tdh $@" + dh_opts, ""]
        if bs in ("meson", "cmake", "autoconf"):
            opts = substitute((step.get("with") or {}).get("opts", ""), self.recipe).split()
            if opts:
                out += ["override_dh_auto_configure:",
                        "\tdh_auto_configure -- \\"]
                out += ["\t\t{} \\".format(o) for o in opts[:-1]] + ["\t\t" + opts[-1], ""]
        if bs == "cargo":
            self.note("Rust: Debian builds against librust-*-dev packages (dh-cargo), not Cargo.lock")
        if bs == "golang":
            self.note("Go: Debian builds against golang-*-dev packages (dh-golang), not vendored modules")
        build, install, manual = [], [], []
        self.files_excluded = []
        stage = "build"
        for st in self.recipe.get("pipeline") or []:
            uses = st.get("uses")
            if uses in BUILDSYSTEMS or uses in SKIPPED_USES:
                if uses in ("meson/install", "cmake/install", "autoconf/make-install"):
                    stage = "install"
                continue
            if uses:
                self.note("pipeline 'uses: {}' has no dh equivalent; port it by hand".format(uses))
                continue
            runs = st.get("runs")
            if not runs:
                continue
            removed = re.findall(r"^\s*rm -rf? ([^\s;&|$]+)\s*$", runs, re.M)
            if removed and len(removed) == len([l for l in runs.splitlines() if l.strip()]) \
                    and not build and not install:
                self.files_excluded += removed
                continue
            if re.search(r"\bcargo\b", runs):
                self.note("Rust: Debian builds against librust-*-dev packages (dh-cargo), not Cargo.lock")
            name = (st.get("name") or "").lower()
            if "install" in name or "${{targets." in runs:
                stage = "install"
            lines = self.make_lines(runs)
            if lines is None:
                manual.append(st.get("name") or "step")
                continue
            (install if stage == "install" else build).extend(lines)
        if build:
            out += ["override_dh_auto_build:"] + (["\tdh_auto_build"] if bs else []) + build + [""]
        if install:
            out += ["override_dh_auto_install:"] + (["\tdh_auto_install"] if bs else []) + install + [""]
        for m in manual:
            out.append("# {}: port the melange step '{}' (shell control flow or melange variables)".format(TODO, m))
            self.note("rules: step '{}' needs a manual port".format(m))
        return "\n".join(out).rstrip() + "\n"

    # -- install files ----------------------------------------------------

    INSTALL_DEFAULTS = {
        "dev": ["usr/include", "usr/lib/*/lib*.so", "usr/lib/*/pkgconfig", "usr/share/pkgconfig",
                "usr/share/gir-1.0", "usr/share/aclocal", "usr/share/vala"],
        "doc": ["usr/share/doc", "usr/share/man", "usr/share/gtk-doc", "usr/share/info"],
    }

    def install_files(self, binaries):
        if len(binaries) == 1:
            return {}
        out = {}
        for name, kind, _, sub in binaries:
            if kind == "main":
                out[name] = ["usr/bin", "usr/lib/*/lib*.so.*", "usr/libexec", "usr/share"]
                continue
            paths = list(self.INSTALL_DEFAULTS.get(kind, []))
            for st in (sub or {}).get("pipeline") or []:
                for p in paths_in(st.get("runs", "")):
                    p = re.sub(r"^usr/lib/", "usr/lib/*/", p)
                    if p not in paths:
                        paths.append(p)
            if not paths:
                paths = ["{} files of {}".format(TODO, name)]
                self.note("{}: list its files in debian/{}.install".format(name, name))
            out[name] = paths
        self.note("check the .install files against 'find debian/tmp' after the first build")
        return out

    # -- copyright, watch, changelog --------------------------------------

    def copyright(self):
        entries = self.pkg.get("copyright") or [{"license": TODO}]
        hp = homepage(self.recipe) or TODO
        out = ["Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/",
               "Upstream-Name: " + self.name, "Source: " + hp]
        if self.files_excluded:
            out.append("Files-Excluded:")
            out += ["  " + f for f in self.files_excluded]
            self.note("Files-Excluded: repack the upstream tarball (+ds) with uscan")
        out.append("")
        used = []
        main = None
        for e in entries:
            lic = to_debian_license(str(e.get("license", TODO)))
            used += [l for l in license_names(lic) if l not in used]
            files = " ".join(e.get("paths") or ["*"])
            if files == "*":
                main = lic
            out += ["Files: " + files, "Copyright: {} upstream copyright holders".format(TODO),
                    "License: " + lic, ""]
        self.note("debian/copyright: fill in the upstream copyright holders")
        out += ["Files: debian/*", "Copyright: {} {}".format(
            email.utils.formatdate()[12:16], re.sub(r"\s*<.*", "", self.maintainer)),
                "License: " + (main or used[0] if used else TODO), ""]
        for lic in used:
            out.append("License: " + lic)
            common = COMMON_LICENSES.get(lic)
            if lic in LICENSE_TEXT:
                out.append(LICENSE_TEXT[lic])
            elif common:
                out.append(" On Debian systems, the complete text of this license can be found in")
                out.append(" /usr/share/common-licenses/{}.".format(common))
            else:
                out.append(" {}: paste the license text.".format(TODO))
                self.note("debian/copyright: paste the text of {}".format(lic))
            out.append("")
        return "\n".join(out).rstrip() + "\n"

    def watch(self):
        gh = github_repo(self.recipe)
        upd = self.recipe.get("update") or {}
        prefix = re.escape((upd.get("github") or {}).get("strip-prefix", ""))
        if gh:
            return ("version=4\n"
                    "opts=\"filenamemangle=s%(?:.*?)?v?@ANY_VERSION@(@ARCHIVE_EXT@)%@PACKAGE@-$1$2%\" \\\n"
                    "  https://github.com/{}/tags \\\n"
                    "  (?:.*?/)?{}@ANY_VERSION@@ARCHIVE_EXT@\n").format(gh, prefix or "v?")
        for step in self.recipe.get("pipeline") or []:
            uri = (step.get("with") or {}).get("uri", "")
            if step.get("uses") == "fetch" and "${{package.version}}" in uri:
                base, _, fname = uri.rpartition("/")
                if "${{package.version}}" in base:
                    break
                pattern = re.escape(substitute(fname, dict(self.recipe, package=dict(
                    self.pkg, version="@@V@@")))).replace("@@V@@", "@ANY_VERSION@")
                pattern = re.sub(r"\\\.tar\\\.(?:gz|xz|bz2|zst)$", "@ARCHIVE_EXT@", pattern)
                return "version=4\n{}/ {}\n".format(substitute(base, self.recipe), pattern)
        self.note("debian/watch: write it by hand (no GitHub upstream or versioned tarball URL)")
        return "version=4\n# {}: upstream release URL and pattern\n".format(TODO)

    def changelog(self):
        return ("{} ({}-1) UNRELEASED; urgency=medium\n\n"
                "  * Initial release. (Closes: #{})\n\n"
                " -- {}  {}\n").format(self.name, self.version, "NNNNNN", self.maintainer,
                                        email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc)))

    def upstream_metadata(self):
        gh = github_repo(self.recipe)
        if not gh:
            return None
        return ("---\nBug-Database: https://github.com/{0}/issues\n"
                "Bug-Submit: https://github.com/{0}/issues/new\n"
                "Repository: https://github.com/{0}.git\n"
                "Repository-Browse: https://github.com/{0}\n").format(gh)

    # -- autopkgtest ------------------------------------------------------

    def tests(self):
        test = self.recipe.get("test") or {}
        steps = test.get("pipeline") or []
        env = ((self.recipe.get("environment") or {}).get("contents") or {}).get("packages") or []
        dev_stems = {str(p)[:-4].split("-")[0] for p in env if str(p).endswith("-dev")}
        # Libraries the package links against come through shlibs:Depends.
        # Commands the tests run are kept.
        scripts_text = "\n".join(st.get("runs", "") for st in steps)
        wanted = [p for p in ((test.get("environment") or {}).get("contents") or {}).get("packages") or []
                  if str(p).split("-")[0] not in dev_stems
                  or re.search(r"(^|[\s;|&(])" + re.escape(str(p)) + r"\s", scripts_text, re.M)]
        deps = self.map_deps(wanted, "test dependency")
        stanzas, scripts = [], {}
        for i, st in enumerate(steps, 1):
            if st.get("uses"):
                self.note("test 'uses: {}' not converted (melange test pipeline)".format(st["uses"]))
                continue
            runs = substitute(st.get("runs", ""), self.recipe)
            if not runs.strip():
                continue
            name = re.sub(r"[^a-z0-9]+", "-", (st.get("name") or "test-{}".format(i)).lower()).strip("-")
            scripts[name] = "#!/bin/sh\nset -e\n" + runs.rstrip() + "\n"
            restr = "superficial" if re.search(r"^\s*(test|\[) ", runs, re.M) and \
                not re.search(r"--version|--help|\|", runs) else None
            stanza = ["Tests: " + name, "Depends: " + ", ".join(["@"] + deps)]
            if restr:
                stanza.append("Restrictions: " + restr)
            stanzas.append("\n".join(stanza))
        if not stanzas:
            return None, {}
        return "\n\n".join(stanzas) + "\n", scripts

    # -- driver -----------------------------------------------------------

    def convert(self):
        binaries = self.binary_packages()
        env = ((self.recipe.get("environment") or {}).get("contents") or {}).get("packages")
        build_deps = self.map_deps(env, "build dependency")
        f = self.files
        f["control"] = self.control(binaries, build_deps)
        f["rules"] = self.rules(len(binaries) > 1)
        f["changelog"] = self.changelog()
        f["copyright"] = self.copyright()
        f["watch"] = self.watch()
        f["source/format"] = "3.0 (quilt)\n"
        meta = self.upstream_metadata()
        if meta:
            f["upstream/metadata"] = meta
        for name, paths in self.install_files(binaries).items():
            f["{}.install".format(name)] = "\n".join(paths) + "\n"
        control, scripts = self.tests()
        if control:
            f["tests/control"] = control
            for name, body in scripts.items():
                f["tests/" + name] = body
        patches = patch_files(self.recipe, self.recipe_base)
        copies = dict(self.copies)
        if patches:
            series = []
            for p in patches:
                base = os.path.basename(p)
                copies["patches/" + base] = p
                series.append(base)
            f["patches/series"] = "\n".join(series) + "\n"
            self.note("patches: add DEP-3 headers (Description, Forwarded) to debian/patches/*")
        return f, copies


def write_tree(out, files, copies, force=False):
    debian = os.path.join(out, "debian")
    if os.path.exists(debian) and not force:
        sys.exit("error: {} exists (use --force to overwrite)".format(debian))
    for rel, text in files.items():
        path = os.path.join(debian, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        if rel == "rules" or (rel.startswith("tests/") and rel != "tests/control"):
            os.chmod(path, 0o755)
    for rel, src in copies.items():
        path = os.path.join(debian, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(src):
            shutil.copyfile(src, path)
    return debian


def default_maintainer():
    name, mail = os.environ.get("DEBFULLNAME"), os.environ.get("DEBEMAIL")
    if name and mail:
        return "{} <{}>".format(name, mail)
    return "{} <maintainer@example.org>".format(TODO)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("recipe", help="melange recipe (packages/NAME.yaml)")
    ap.add_argument("--out", help="directory to create debian/ in (default ./NAME)")
    ap.add_argument("--maintainer", help='"Name <email>" (default $DEBFULLNAME <$DEBEMAIL>)')
    ap.add_argument("--force", action="store_true", help="overwrite an existing debian/")
    ap.add_argument("--check-debian", action="store_true",
                    help="look up mapped dependency names in Debian unstable (uses pkg-check)")
    ap.add_argument("--strict", action="store_true", help="exit 1 if anything needs manual review")
    ap.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = ap.parse_args(argv)

    with open(args.recipe, encoding="utf-8") as fh:
        recipe = yaml.safe_load(fh)
    conv = Converter(recipe, args.recipe, args.maintainer or default_maintainer(), args.check_debian)
    files, copies = conv.convert()
    debian = write_tree(args.out or conv.name, files, copies, args.force)
    print("wrote {} ({} files)".format(debian, len(files) + len(copies)))
    for n in conv.notes:
        print("note: " + n, file=sys.stderr)
    if conv.notes:
        print("{} item(s) to review; grep -rn '{}' {}".format(len(conv.notes), TODO, debian), file=sys.stderr)
    return 1 if args.strict and conv.notes else 0


if __name__ == "__main__":
    sys.exit(main())
