#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
"""alpine-to-melange: convert an Alpine APKBUILD to a melange recipe.

    alpine-to-melange --from-alpine libass --check-wolfi
    alpine-to-melange --apkbuild-dir ~/aports/community/zimg --out packages/

Reads the APKBUILD statically (it is never executed), maps metadata,
sources and sha512sums, subpackages and install scripts, and carries the
prepare()/build()/package() bodies over almost verbatim: abuild's variables
and helpers ($pkgdir, $srcdir, $CHOST, abuild-meson, amove, ...) are
provided by a small preamble, so the upstream build logic is preserved.

Everything that cannot be converted mechanically is reported on stderr and
left as a "TODO(alpine-to-melange)" comment in the generated recipe.

Standard library only. Shares the YAML emitter, Wolfi index lookup and test
conventions of tools/debian-to-melange.
"""

import argparse
import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

__version__ = "0.1.0"

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "debian_to_melange", os.path.join(HERE, "..", "debian-to-melange", "debian-to-melange.py"))
d2m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(d2m)
C, Comment, emit = d2m.C, d2m.Comment, d2m.emit

TODO = "TODO(alpine-to-melange)"
USER_AGENT = "alpine-to-melange/{} (+https://github.com/vejeta/wolfi-packages)".format(__version__)
APORTS_API = "https://gitlab.alpinelinux.org/api/v4/projects/alpine%2Faports/repository"
APORTS_REPOS = ["main", "community", "testing"]

WORKSPACE = "/home/build"           # melange build workspace
SRCDIR = WORKSPACE + "/_srcdir"     # stands in for abuild's $srcdir

# Alpine/musl-only build dependencies that have no meaning on Wolfi (glibc).
DROP = {
    "abuild", "alpine-sdk", "musl-dev", "musl-utils", "musl-fts-dev", "fts-dev",
    "argp-standalone", "libucontext-dev", "libexecinfo-dev", "gettext-tiny",
    "gettext-tiny-dev", "musl-obstack-dev", "musl-libintl", "libc-dev", "gcompat",
}
NAME_MAP = {
    "samurai": "ninja",
    "ca-certificates": "ca-certificates-bundle",
    "gtk4.0": "gtk-4",
    "gtk4.0-dev": "gtk-4-dev",
    "gtk+3.0": "gtk-3",
    "gtk+3.0-dev": "gtk-3-dev",
    "py3-setuptools": "py3-setuptools",
    "linux-headers": "linux-headers",
}

# abuild default subpackage handlers -> melange pipelines
SPLIT_DEFAULTS = {
    "dev": [{"uses": "split/dev"}],
    "doc": [{"uses": "split/alldocs"}],
    "static": [{"uses": "split/static"}],
    "libs": [{"uses": "split/lib"}],
    "lang": [{"uses": "split/locales"}],
    "bash-completion": [{"runs": "amove usr/share/bash-completion/completions\n"}],
    "zsh-completion": [{"runs": "amove usr/share/zsh/site-functions\n"}],
    "fish-completion": [{"runs": "amove usr/share/fish/vendor_completions.d\n"}],
}
SKIP_SUFFIXES = {
    "openrc": "OpenRC init scripts are not used on Wolfi",
    "pyc": "precompiled Python bytecode is not shipped on Wolfi",
    "dbg": "debug symbols: use melange's split/debug if needed",
}
SCRIPT_KINDS = ["pre-install", "post-install", "pre-upgrade", "post-upgrade",
                "pre-deinstall", "post-deinstall"]


# ==========================================================================
# Static APKBUILD parser
# ==========================================================================

class ApkBuild:
    """Static model of an APKBUILD: top-level variables and functions."""

    def __init__(self, text):
        self.text = text
        self.vars = {"srcdir": SRCDIR, "pkgdir": "$pkgdir", "startdir": WORKSPACE}
        self.raw = {}               # name -> unexpanded value
        self.order = []             # assignment order of top-level variables
        self.assignments = []       # (name, value as written), in order
        self.functions = {}         # name -> body (list of lines)
        self.skipped = []           # top-level constructs that were not evaluated
        self._parse(text)

    def _parse(self, text):
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            s = line.strip()
            if not s or s.startswith("#"):
                i += 1
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{?\s*$", s)
            if m:
                i = self._read_function(m.group(1), lines, i)
                continue
            if re.match(r"^(case|if|for|while)\b", s):
                end = {"case": "esac", "if": "fi", "for": "done", "while": "done"}[s.split()[0]]
                start = i
                depth = 0
                while i < len(lines):
                    w = lines[i].strip().split()
                    if w and w[0] in ("case", "if", "for", "while"):
                        depth += 1
                    if w and w[0] == end or lines[i].strip().endswith(" " + end) or lines[i].strip() == end:
                        depth -= 1
                        if depth <= 0:
                            break
                    i += 1
                self.skipped.append("\n".join(lines[start:i + 1]))
                i += 1
                continue
            # one or more assignments on a line: a=1; b=${a%x}
            consumed = self._read_assignments(lines, i)
            if consumed:
                i += consumed
                continue
            self.skipped.append(s)
            i += 1

    def _read_function(self, name, lines, i):
        body = []
        if not lines[i].rstrip().endswith("{"):
            i += 1                              # "{" on its own line
        i += 1
        depth = 1
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped == "}" and depth == 1 and not line.startswith(("\t\t", "    ")):
                break
            depth += line.count("{") - line.count("}") if not stripped.startswith("#") else 0
            if depth <= 0:
                break
            body.append(line)
            i += 1
        self.functions[name] = body
        return i + 1

    def _read_assignments(self, lines, i):
        text = lines[i]
        n = 1
        # a quoted value may span lines
        while text.count('"') % 2 == 1 and i + n < len(lines):
            text += "\n" + lines[i + n]
            n += 1
        pos, found = 0, False
        pattern = re.compile(r'\s*(?:local\s+|export\s+)?([A-Za-z_][A-Za-z0-9_]*)=("(?:[^"\\]|\\.)*"|\'[^\']*\'|[^\s;]*)\s*(?:;|$|#.*$)', re.S)
        while pos < len(text):
            m = pattern.match(text, pos)
            if not m:
                break
            name, val = m.group(1), m.group(2)
            self.assignments.append((name, val))
            if val.startswith("'"):
                val = val[1:-1]
                expanded = val
            else:
                if val.startswith('"'):
                    val = val[1:-1]
                expanded = self.expand(val)
            self.raw[name] = val
            self.vars[name] = expanded
            if name not in self.order:
                self.order.append(name)
            pos = m.end()
            found = True
        return n if found and not text[pos:].strip() else (n if found else 0)

    # -- shell parameter expansion (the subset APKBUILDs use) --------------

    def expand(self, value):
        def param(m):
            expr = m.group(1) or m.group(2)
            return self._param(expr)
        value = re.sub(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)", param, value)
        return value

    def _param(self, expr):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(.*)$", expr, re.S)
        if not m:
            return "${" + expr + "}"
        name, op = m.groups()
        if name not in self.vars:
            return "${" + expr + "}" if op else "$" + name
        v = self.vars[name]
        if not op:
            return v
        for prefix, greedy, from_end in (("%%", True, True), ("%", False, True),
                                         ("##", True, False), ("#", False, False)):
            if op.startswith(prefix):
                return self._strip(v, self.expand(op[len(prefix):]), greedy, from_end)
        m = re.match(r"^(//?)([^/]*)/?(.*)$", op)
        if m:
            pat, rep = self.expand(m.group(2)), self.expand(m.group(3))
            return re.sub(glob_regex(pat), lambda _m: rep, v, count=0 if m.group(1) == "//" else 1)
        m = re.match(r"^:?-(.*)$", op)
        if m:
            return v or self.expand(m.group(1))
        return "${" + expr + "}"

    @staticmethod
    def _strip(v, pat, greedy, from_end):
        idx = range(len(v) + 1)
        rx = re.compile(glob_regex(pat), re.S)
        if from_end:
            cands = [i for i in idx if rx.fullmatch(v[i:])]
            if cands:
                i = min(cands) if greedy else max(cands)
                return v[:i]
        else:
            cands = [i for i in idx if rx.fullmatch(v[:i])]
            if cands:
                i = max(cands) if greedy else min(cands)
                return v[i:]
        return v

    def get(self, name, default=""):
        return self.vars.get(name, default)

    def words(self, name):
        return self.get(name).split()


def apk_unglob(regex):
    """Literal text of a regex made only of escaped characters."""
    return re.sub(r"\\(.)", r"\1", regex)


def glob_regex(pattern):
    """Shell glob -> regex (no anchors), for ${var/pattern/replacement}."""
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        elif ch == "[":
            j = pattern.find("]", i + 1)
            if j == -1:
                out.append(re.escape(ch))
            else:
                body = pattern[i + 1:j]
                out.append("[" + ("^" + body[1:] if body.startswith("!") else body) + "]")
                i = j
        else:
            out.append(re.escape(ch))
        i += 1
    return "".join(out)


# ==========================================================================
# Conversion
# ==========================================================================

def parse_sources(apk):
    """[(filename, url_or_None)] from source=, in order."""
    out = []
    for entry in apk.words("source"):
        if "::" in entry:
            fname, url = entry.split("::", 1)
        elif re.match(r"^[a-z+]+://", entry):
            url = entry
            fname = os.path.basename(urllib.parse.urlparse(url).path)
        else:
            fname, url = entry, None
        out.append((fname, url))
    return out


def parse_checksums(apk):
    sums = {}
    words = apk.words("sha512sums")
    for i in range(0, len(words) - 1, 2):
        sums[words[i + 1]] = words[i]
    return sums


def glob_to_re(pattern, greedy):
    rx = glob_regex(pattern)
    return rx if greedy else rx.replace(".*", ".*?")


def var_transform(name, raw):
    """'${pkgver/_rc/-rc}' -> melange var-transform (or None)."""
    m = re.match(r"^\$\{pkgver(//?|%%|%|##|#)(.*)\}$", raw.strip('"'))
    if not m:
        return None
    op, rest = m.groups()
    if op in ("/", "//"):
        pat, _, repl = rest.partition("/")
        match, replace = glob_regex(pat), repl.replace("$", "$$")
    elif op == "%":
        match, replace = "^(.*)" + glob_to_re(rest, False) + "$", "${1}"
    elif op == "%%":
        match, replace = "^(.*?)" + glob_to_re(rest, True) + "$", "${1}"
    elif op == "#":
        match, replace = "^" + glob_to_re(rest, False) + "(.*)$", "${1}"
    else:
        match, replace = "^" + glob_to_re(rest, True) + "(.*?)$", "${1}"
    key = name.lstrip("_").replace("_", "-") or "pkgver"
    return {"from": "${{package.version}}", "match": match, "replace": replace,
            "to": "mangled-" + key}


def template_version(url, apk, transforms):
    """Replace literal versions in a URL by melange variables."""
    subs = [(apk.get(n), "${{vars.%s}}" % t["to"]) for n, t in transforms.items()]
    subs.append((apk.get("pkgver"), "${{package.version}}"))
    out = url
    for literal, ref in sorted(subs, key=lambda x: len(x[0]), reverse=True):
        if literal and literal != apk.get("pkgver") or ref == "${{package.version}}":
            out = out.replace(literal, ref) if literal else out
    return out


def github_update(url):
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/(?:archive|releases)/(?:refs/tags/|download/)?([^/]*?)\$\{\{(?:package\.version|vars\.[\w-]+)\}\}", url or "")
    if not m:
        return None
    up = {"enabled": True, "github": {"identifier": "{}/{}".format(m.group(1), m.group(2))}}
    prefix = m.group(3).rstrip("/")
    if prefix:
        up["github"]["strip-prefix"] = prefix
    if "/releases/" in url:
        up["github"]["use-tag"] = True
    return up


PREAMBLE_VARS = [
    ("pkgname", "${{package.name}}"),
    ("pkgver", "${{package.version}}"),
    ("pkgdir", "${{targets.destdir}}"),
    ("subpkgdir", "${{targets.contextdir}}"),
    ("srcdir", SRCDIR),
    ("builddir", WORKSPACE),
    ("startdir", WORKSPACE),
    ("CARCH", "${{build.arch}}"),
    ("CBUILD", "${{host.triplet.gnu}}"),
    ("CHOST", "${{host.triplet.gnu}}"),
    ("CTARGET", "${{host.triplet.gnu}}"),
    ("JOBS", "$(nproc)"),
]

HELPERS = {
    "abuild-meson": (
        "abuild_meson() {\n"
        "\tmeson setup --prefix=/usr --libdir=/usr/lib --libexecdir=/usr/libexec \\\n"
        "\t\t--bindir=/usr/bin --sbindir=/usr/sbin --includedir=/usr/include \\\n"
        "\t\t--datadir=/usr/share --mandir=/usr/share/man --infodir=/usr/share/info \\\n"
        "\t\t--localedir=/usr/share/locale --sysconfdir=/etc --localstatedir=/var \\\n"
        "\t\t--sharedstatedir=/var/lib --buildtype=plain --auto-features=auto \\\n"
        "\t\t--wrap-mode=nofallback -Db_staticpic=true -Db_pie=true \\\n"
        "\t\t-Dpython.bytecompile=0 \"$@\"\n"
        "}"),
    "amove": (
        "amove() {\n"
        "\tfor _p in \"$@\"; do\n"
        "\t\t_p=${_p#/}\n"
        "\t\tfor _f in \"$pkgdir\"/$_p; do\n"
        "\t\t\t[ -e \"$_f\" ] || [ -L \"$_f\" ] || continue\n"
        "\t\t\t_d=${_f#\"$pkgdir\"/}\n"
        "\t\t\tmkdir -p \"$subpkgdir/${_d%/*}\"\n"
        "\t\t\tmv \"$_f\" \"$subpkgdir/${_d%/*}/\"\n"
        "\t\tdone\n"
        "\tdone\n"
        "}"),
    "want_check": "want_check() { return 1; }",
}


class Converter:

    def __init__(self, apk, files, args, wolfi):
        self.apk = apk
        self.files = files          # local files next to the APKBUILD: name -> bytes
        self.args = args
        self.wolfi = wolfi
        self.notes = []
        self.aux = {}

    def todo(self, msg):
        self.notes.append(msg)
        return Comment("{}: {}".format(TODO, msg))

    # -- dependencies --------------------------------------------------------

    def map_deps(self, names, kind):
        out = []
        for name in names:
            if name.startswith(("!", "so:", "cmd:", "pc:", "/")) or "$" in name:
                continue
            if ":" in name:  # virtual provider such as dbus:org.freedesktop.Secrets
                self.notes.append("{} dependency '{}' is an Alpine virtual name; not converted".format(kind, name))
                continue
            base = re.split(r"[<>=~]", name, maxsplit=1)[0]
            if base in DROP:
                continue
            cand = NAME_MAP.get(base, base)
            found = self.wolfi.has(cand)
            if any((o.value if isinstance(o, C) else o) == cand for o in out):
                continue
            if found is False:
                self.notes.append("{} dependency '{}' not found in Wolfi".format(kind, cand))
                out.append(C(cand, "{}: not in Wolfi".format(TODO)))
            elif cand != base:
                out.append(C(cand, "Alpine: {}".format(base)))
            else:
                out.append(cand)
        return out

    # -- function bodies -----------------------------------------------------

    def body(self, fname, drop_default=None):
        lines = list(self.apk.functions.get(fname, []))
        if drop_default:
            lines = [l for l in lines if l.strip() != drop_default]
        text = "\n".join(lines)
        text = re.sub(r"(?m)^\s*cd\s+\"?\$\{?builddir\}?\"?\s*$\n?", "", text)
        text = textwrap_dedent(text).strip("\n")
        return text

    def runs(self, text):
        """Prefix a body with the abuild environment it relies on."""
        if not text.strip():
            return None
        text = re.sub(r"(?m)^(\s*)local\s+", r"\1", text)   # no longer inside a function
        refs = lambda t: set(re.findall(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)", t))
        used = refs(text)
        # helper variables (_foo) and everything they reference, transitively
        helpers = [(n, v) for n, v in self.apk.assignments if n.startswith("_")]
        needed, changed = set(), True
        while changed:
            changed = False
            for n, v in helpers:
                if (n in used or n in needed) and not refs(v) <= (used | needed):
                    needed |= refs(v)
                    changed = True
                if n in used and n not in needed:
                    needed.add(n)
                    changed = True
        used |= needed
        funcs = [code for helper, code in HELPERS.items()
                 if re.search(r"(^|[\s;(|&]){}\b".format(re.escape(helper)), text)]
        for code in funcs:  # helpers use abuild variables too ($pkgdir, $subpkgdir)
            used |= refs(code)
        text = re.sub(r"(^|[\s;(|&])abuild-meson\b", r"\1abuild_meson", text)
        pre = ['{}="{}"'.format(n, v) for n, v in PREAMBLE_VARS if n in used]
        pre += ["{}={}".format(n, v) for n, v in helpers if n in used]
        pre += funcs
        if "srcdir" in used and self.local_payload():
            pre.append('mkdir -p "$srcdir"')
            for f in self.local_payload():
                pre.append('cp -a {}/{}/{} "$srcdir"/'.format(WORKSPACE, self.name, f))
        return ("\n".join(pre) + "\n\n" if pre else "") + text + "\n"

    def local_payload(self):
        return [f for f in self.local_files if not f.endswith(".patch")]

    # -- main ----------------------------------------------------------------

    def convert(self):
        apk, a = self.apk, self.args
        self.name = name = a.name or apk.get("pkgname")
        version = a.version or apk.get("pkgver")
        if not name or not version:
            raise SystemExit("error: APKBUILD has no pkgname/pkgver")
        desc = apk.get("pkgdesc")
        pkg = {"name": name, "version": version, "epoch": 0, "description": desc[:1].upper() + desc[1:]}
        pkg["copyright"] = [{"license": apk.get("license") or "NOASSERTION"}]
        if not apk.get("license"):
            pkg["copyright"].insert(0, self.todo("APKBUILD has no license"))

        arch = apk.words("arch")
        if arch and not set(arch) & {"all", "noarch"}:
            targets = [x for x in arch if x in ("x86_64", "aarch64")]
            if targets:
                pkg["target-architecture"] = targets
            else:
                self.notes.append("arch='{}' excludes x86_64 and aarch64".format(" ".join(arch)))
        elif any(x in ("!x86_64", "!aarch64") for x in arch):
            pkg["target-architecture"] = [x for x in ("x86_64", "aarch64") if "!" + x not in arch]

        runtime = self.map_deps(apk.words("depends"), "runtime")
        if runtime:
            pkg["dependencies"] = {"runtime": runtime}
        provides = [p for p in apk.words("provides") if not p.startswith(("so:", "cmd:", "pc:"))]
        if provides:
            pkg.setdefault("dependencies", {})["provides"] = provides
        replaces = apk.words("replaces")
        if replaces:
            pkg.setdefault("dependencies", {})["replaces"] = replaces

        # ---- version transforms ------------------------------------------
        transforms = {}
        for n, raw in apk.assignments:
            if n.startswith("_") and "pkgver" in raw:
                t = var_transform(n, raw)
                if t and apk.get(n) != apk.get("pkgver"):
                    transforms[n] = t

        # ---- sources -----------------------------------------------------
        sources = parse_sources(apk)
        sums = parse_checksums(apk)
        self.local_files = [f for f, u in sources if u is None]
        for f in self.local_files:
            if f in self.files:
                self.aux[f] = self.files[f]
            else:
                self.notes.append("local source '{}' not found next to the APKBUILD".format(f))

        scripts = self.install_scripts(name)
        if scripts:
            pkg["scriptlets"] = scripts

        options = apk.words("options")
        if "net" in options:
            self.notes.append("options=net: the build needs network access")
        if apk.get("triggers"):
            self.notes.append("triggers= not converted: " + apk.get("triggers"))

        # ---- environment -------------------------------------------------
        build_names = apk.words("makedepends") + apk.words("makedepends_build") + apk.words("makedepends_host")
        if a.with_check:
            build_names += apk.words("checkdepends")
        env_pkgs = ["build-base", "busybox"] + [
            d for d in self.map_deps(build_names, "build")
            if (d.value if isinstance(d, C) else d) not in ("build-base", "busybox")]
        plain = [d.value if isinstance(d, C) else d for d in env_pkgs]
        if "gobject-introspection-dev" in plain and "glib-gir" not in plain:
            # Alpine ships GLib's .gir files in glib-dev; Wolfi splits them out.
            env_pkgs.append(C("glib-gir", "GLib .gir files (part of glib-dev on Alpine)"))
        environment = {"contents": {
            "keyring": ["https://packages.wolfi.dev/os/wolfi-signing.rsa.pub"],
            "repositories": ["https://packages.wolfi.dev/os"],
            "packages": env_pkgs,
        }}

        # ---- pipeline ----------------------------------------------------
        pipeline = []
        remote = [(f, u) for f, u in sources if u]
        main_url = None
        builddir = apk.get("builddir") or "{}/{}-{}".format(SRCDIR, name, version)
        for idx, (fname, url) in enumerate(remote):
            url = apk.expand(url)
            if url.startswith(("git+", "git://")) or url.endswith(".git"):
                pipeline.append(self.todo("git source not converted: " + url))
                continue
            gh = re.match(r"^https://github\.com/([^/]+)/([^/]+)/archive/(?:refs/tags/)?(.+?)\.tar\.gz$", url)
            if idx == 0 and gh and gh.group(3).endswith(version):
                # Wolfi pins GitHub sources with git-checkout + expected-commit.
                prefix = gh.group(3)[:-len(version)]
                steps, notes = d2m.git_checkout_step(gh.group(1), gh.group(2), version, prefix,
                                                     resolve=getattr(a, "download", False), todo=TODO)
                self.notes += notes
                pipeline += steps
                main_url = template_version(url, apk, transforms)
                continue
            step = {"uses": "fetch", "with": {"uri": template_version(url, apk, transforms)}}
            if fname in sums:
                step["with"]["expected-sha512"] = sums[fname]
            else:
                step["with"]["expected-sha256"] = "0" * 64
                pipeline.append(self.todo("no checksum for {}".format(fname)))
            if idx == 0:
                main_url = step["with"]["uri"]
                if not builddir.startswith(SRCDIR + "/") or "/" in builddir[len(SRCDIR) + 1:]:
                    self.notes.append("builddir={} is not the top directory of the main tarball; review".format(builddir))
            else:
                step["with"]["strip-components"] = 0
                step["with"]["directory"] = SRCDIR[len(WORKSPACE) + 1:]
                if not re.search(r"\.(tar(\.\w+)?|tgz|tbz2|txz|zip)$", fname):
                    step["with"]["extract"] = False
            pipeline.append(step)
        if not remote:
            pipeline.append(self.todo("APKBUILD has no remote source"))

        patches = [f for f in self.local_files if f.endswith(".patch")]
        if patches:
            pipeline.append({"uses": "patch", "with": {"patches": " ".join(
                "{}/{}".format(name, p) for p in patches)}})

        for fname, label, default in (("prepare", "Prepare", "default_prepare"),
                                      ("build", "Build", None), ("package", "Install", None)):
            if fname not in apk.functions:
                continue
            text = self.body(fname, default)
            step = self.runs(text)
            if step:
                pipeline.append({"name": label, "runs": step})
        if "check" in apk.functions:
            if a.with_check:
                pipeline.insert(len(pipeline) - 1, {"name": "Check", "runs": self.runs(self.body("check"))})
            else:
                self.notes.append("check() not run (pass --with-check to add it to the build)")
        if "package" not in apk.functions:
            pipeline.append(self.todo("APKBUILD has no package() function"))
        else:
            # abuild deletes libtool archives and strips binaries after
            # package(); melange does neither on its own.
            if "libtool" not in options:
                pipeline.append({"name": "Remove libtool archives (abuild does this by default)",
                                 "runs": 'find "${{targets.destdir}}" -name "*.la" -delete\n'})
            if "!strip" not in options:
                pipeline.append({"uses": "strip"})

        # ---- subpackages -------------------------------------------------
        subpackages = [s for s in (self.subpackage(entry, name) for entry in apk.words("subpackages")) if s]

        # ---- update / test -----------------------------------------------
        update = github_update(main_url)
        if update:
            for t in transforms.values():
                if "${{vars.%s}}" % t["to"] in main_url and t["replace"] != "${1}":
                    update["version-transform"] = [{"match": re.escape(t["replace"].replace("$$", "$")),
                                                    "replace": apk_unglob(t["match"])}]
        update = update or {
            "enabled": True,
            "release-monitor": {"identifier": C(0, "{}: set the release-monitoring.org project id".format(TODO))}}
        test = {"environment": {"contents": {"packages": ["busybox"]}},
                "pipeline": [{"uses": "test/tw/ldd-check"}]}

        recipe = {"package": pkg}
        used_t = [t for t in transforms.values()
                  if any("${{vars.%s}}" % t["to"] in str(st.get("with", {}).get("uri", ""))
                         for st in pipeline if isinstance(st, dict))]
        if used_t:
            recipe["var-transforms"] = used_t
        recipe.update({"environment": environment, "pipeline": pipeline})
        if re.search(r"/etc/(init\.d|conf\.d)/", "\n".join(apk.functions.get("package", []))):
            self.notes.append("package() installs OpenRC files (/etc/init.d, /etc/conf.d); Wolfi does not use OpenRC")
        if subpackages:
            recipe["subpackages"] = subpackages
        recipe["update"] = update
        recipe["test"] = test
        for skipped in apk.skipped:
            if "options" in skipped or "secfixes" in skipped:
                continue
            first = skipped.splitlines()[0]
            self.notes.append("top-level shell not evaluated: {}{}".format(
                first, " ..." if "\n" in skipped else ""))
        return name, recipe, self.header()

    def header(self):
        lines = ["Generated by alpine-to-melange {} from the Alpine APKBUILD of {} {}-r{}.".format(
            __version__, self.apk.get("pkgname"), self.apk.get("pkgver"), self.apk.get("pkgrel", "0"))]
        if self.args.from_alpine:
            lines.append("https://gitlab.alpinelinux.org/alpine/aports/-/tree/master/{}".format(self.args.aports_path))
        if self.apk.get("url"):
            lines.append("Upstream: " + self.apk.get("url"))
        if self.notes:
            lines += ["", "Conversion notes:"] + ["- " + n for n in self.notes]
        return lines

    def install_scripts(self, pkgname):
        scripts = {}
        declared = self.apk.words("install")
        for kind in SCRIPT_KINDS:
            fname = "{}.{}".format(pkgname, kind)
            if fname in declared:
                if fname in self.files:
                    text = self.files[fname].decode("utf-8", "replace")
                    if not text.startswith("#!"):
                        text = "#!/bin/sh\n" + text
                    scripts[kind] = text
                else:
                    self.notes.append("install script {} not found".format(fname))
        return scripts

    def subpackage(self, entry, name):
        parts = entry.split(":")
        sub = parts[0]
        func = parts[1] if len(parts) > 1 and parts[1] else None
        orig = self.apk.get("pkgname") or name
        if orig != name and sub.startswith(orig + "-"):
            sub = name + sub[len(orig):]  # --name renames the subpackages too
        suffix = sub[len(name) + 1:] if sub.startswith(name + "-") else sub
        if func is None:
            func = suffix.replace("-", "_") if suffix.replace("-", "_") in self.apk.functions else None
        if suffix in SKIP_SUFFIXES and not func:
            self.notes.append("subpackage {} skipped: {}".format(sub, SKIP_SUFFIXES[suffix]))
            return None
        out = {"name": sub.replace("$pkgname", name)}
        if func and func in self.apk.functions:
            body = self.body(func)
            body_lines = [l for l in body.splitlines() if l.strip()]
            defaults = [l.strip() for l in body_lines if re.match(r"^default_\w+$", l.strip())]
            rest = "\n".join(l for l in body.splitlines() if l.strip() not in defaults)
            rest = re.sub(r'(?m)^\s*(pkgdesc|depends|replaces|provides|install_if)=.*$', "", rest).strip()
            pipeline = []
            for d in defaults:
                key = d[len("default_"):]
                pipeline += SPLIT_DEFAULTS.get(key, [self.todo("abuild helper {} in {}()".format(d, func))])
            if rest:
                pipeline.append({"runs": self.runs(rest)})
            out["pipeline"] = pipeline or [{"runs": "true\n"}]
            m = re.search(r'(?m)^\s*pkgdesc="([^"]*)"', body)
            desc = self.apk.expand(m.group(1)) if m else None
            m = re.search(r'(?m)^\s*depends="([^"]*)"', body)
            fdeps = []
            for d in (self.apk.expand(m.group(1)).split() if m else []):
                base = re.split(r"[<>=~]", d, maxsplit=1)[0]
                fdeps.append(base)
        elif suffix in SPLIT_DEFAULTS:
            out["pipeline"] = [dict(p) for p in SPLIT_DEFAULTS[suffix]]
            if "runs" in out["pipeline"][0]:
                out["pipeline"][0]["runs"] = self.runs(out["pipeline"][0]["runs"])
            desc = None
        else:
            out["pipeline"] = [self.todo("no function for subpackage {}".format(sub)), {"runs": "true\n"}]
            desc = None
        if not (func and func in self.apk.functions):
            fdeps = []
        desc = desc or "{} ({})".format(self.apk.get("pkgdesc"), suffix)
        out = {"name": out["name"], "description": desc[:1].upper() + desc[1:], "pipeline": out["pipeline"]}
        own = {name} | {e.split(":")[0] for e in self.apk.words("subpackages")}
        deps = [d for d in fdeps if d in own] + self.map_deps([d for d in fdeps if d not in own], "runtime")
        if deps:
            out["dependencies"] = {"runtime": deps}
        if suffix == "dev":
            deps = self.map_deps(self.apk.words("depends_dev"), "runtime")
            if deps:
                out.setdefault("dependencies", {}).setdefault("runtime", []).extend(deps)
            out["test"] = {"environment": {"contents": {"packages": ["busybox"]}},
                           "pipeline": [{"uses": "test/pkgconf"}]}
        scripts = self.install_scripts(out["name"])
        if scripts:
            out["scriptlets"] = scripts
        return out


def textwrap_dedent(text):
    """Dedent tab- or space-indented function bodies."""
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return text
    tabs = min(len(l) - len(l.lstrip("\t")) for l in lines)
    if tabs:
        return "\n".join(l[tabs:] if l.startswith("\t" * tabs) else l for l in text.splitlines())
    import textwrap
    return textwrap.dedent(text)


# ==========================================================================
# Input
# ==========================================================================

def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def fetch_from_alpine(name, branch):
    """Return (aports path, {filename: bytes}) for an aport."""
    for repo in APORTS_REPOS:
        path = "{}/{}".format(repo, name)
        url = "{}/tree?path={}&ref={}&per_page=100".format(APORTS_API, urllib.parse.quote(path), branch)
        try:
            listing = json.loads(http_get(url))
        except urllib.error.HTTPError:
            continue
        if not isinstance(listing, list) or not listing:
            continue
        files = {}
        for item in listing:
            if item["type"] != "blob":
                continue
            fpath = urllib.parse.quote(item["path"], safe="")
            files[item["name"]] = http_get("{}/files/{}/raw?ref={}".format(APORTS_API, fpath, branch))
        return path, files
    raise SystemExit("error: '{}' not found in aports ({})".format(name, ", ".join(APORTS_REPOS)))


def read_dir(path):
    files = {}
    for fname in sorted(os.listdir(path)):
        full = os.path.join(path, fname)
        if os.path.isfile(full):
            with open(full, "rb") as fh:
                files[fname] = fh.read()
    return files


def main(argv=None):
    p = argparse.ArgumentParser(prog="alpine-to-melange",
                                description="Convert an Alpine APKBUILD to a melange recipe.")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--apkbuild-dir", help="directory containing an APKBUILD and its local files")
    src.add_argument("--from-alpine", metavar="NAME", help="fetch the aport from gitlab.alpinelinux.org")
    p.add_argument("--branch", default="master", help="aports branch (default: master)")
    p.add_argument("--out", default="packages", help="output directory (default: packages)")
    p.add_argument("--stdout", action="store_true", help="print the recipe instead of writing files")
    p.add_argument("--name", help="override the package name")
    p.add_argument("--version", help="override the package version")
    p.add_argument("--with-check", action="store_true", help="run check() as part of the build")
    p.add_argument("--check-wolfi", action="store_true",
                   help="verify dependency names against the Wolfi APKINDEX")
    p.add_argument("--strict", action="store_true", help="exit 1 if anything needs manual review")
    p.add_argument("--download", action="store_true",
                   help="allow network lookups to pin sources (git ls-remote for GitHub tags)")
    p.add_argument("--build", action="store_true",
                   help="build the generated recipe with melange (bubblewrap runner) and report the result")
    p.add_argument("--melange", default="melange", help="melange binary for --build (default: melange)")
    p.add_argument("--melange-opts", default="", help="extra options for melange build (e.g. \"--cache-dir DIR\")")
    p.add_argument("-V", "--tool-version", action="version", version="%(prog)s " + __version__)
    args = p.parse_args(argv)
    args.aports_path = None

    try:
        if args.from_alpine:
            args.aports_path, files = fetch_from_alpine(args.from_alpine, args.branch)
        else:
            files = read_dir(args.apkbuild_dir)
        if "APKBUILD" not in files:
            raise SystemExit("error: no APKBUILD found")
        apk = ApkBuild(files["APKBUILD"].decode("utf-8", "replace"))
        conv = Converter(apk, files, args, d2m.WolfiIndex(args.check_wolfi))
        name, recipe, header = conv.convert()
    except urllib.error.URLError as exc:
        print("error: network: {}".format(exc), file=sys.stderr)
        return 2
    text = d2m.write_output(name, recipe, header, conv.aux, args.out, args.stdout)
    for n in conv.notes:
        print("note: " + n, file=sys.stderr)
    built = d2m.report_build(args, name)
    if built:
        return built
    return 1 if args.strict and TODO in text else 0


if __name__ == "__main__":
    sys.exit(main())
