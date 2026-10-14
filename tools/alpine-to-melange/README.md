# alpine-to-melange

Convert an Alpine `APKBUILD` into a [melange](https://github.com/chainguard-dev/melange)
recipe for Wolfi.

melange used to ship an experimental `melange convert apkbuild`; it is gone
from current releases (checked against v0.62.1). This tool fills that gap.

Standard library only (Python ≥ 3.9). Shares the YAML emitter, Wolfi index
lookup and test conventions of [`debian-to-melange`](../debian-to-melange/).

## Usage

```bash
# From aports (searches main, community, testing on the given branch)
tools/alpine-to-melange/alpine-to-melange.py --from-alpine libass --check-wolfi

# From a local aports checkout
tools/alpine-to-melange/alpine-to-melange.py --apkbuild-dir ~/aports/community/zimg
```

Output: `packages/<name>.yaml` plus `packages/<name>/` with local sources
(patches, config files), like every other recipe in this repository.

| Option | Purpose |
|--------|---------|
| `--from-alpine NAME` / `--branch` | Fetch the aport from gitlab.alpinelinux.org |
| `--apkbuild-dir PATH` | Use a local directory with an APKBUILD |
| `--out DIR` / `--stdout` | Output directory (default `packages`) or print the recipe |
| `--name`, `--version` | Override name / version |
| `--with-check` | Run `check()` as part of the build |
| `--check-wolfi` | Verify dependency names against the Wolfi APKINDEX |
| `--strict` | Exit 1 if any `TODO(alpine-to-melange)` remains |

## Approach

The APKBUILD is **parsed, never executed**. Top-level assignments are
evaluated with a small implementation of the shell parameter expansions
APKBUILDs use (`${v%x}`, `${v%%x}`, `${v#x}`, `${v##x}`, `${v/a/b}`,
`${v//a/b}`, `${v:-d}`), checked against a real shell in the test suite.

`prepare()`, `build()` and `package()` bodies are kept **verbatim**. Instead
of rewriting them, each step gets a short preamble that defines what abuild
would have provided, only for what the body actually uses:

| abuild | melange step preamble |
|---------|-----------------------|
| `$pkgname`, `$pkgver` | `${{package.name}}`, `${{package.version}}` |
| `$pkgdir`, `$subpkgdir` | `${{targets.destdir}}`, `${{targets.contextdir}}` |
| `$srcdir`, `$builddir` | `/home/build/_srcdir`, `/home/build` (melange workspace) |
| `$CBUILD`, `$CHOST`, `$CARCH`, `$JOBS` | `${{host.triplet.gnu}}`, `${{build.arch}}`, `$(nproc)` |
| `_helper` variables | Re-declared, with their dependencies, in order |
| `abuild-meson`, `amove`, `want_check` | Equivalent shell functions |
| `local x=…` | `x=…` (the body no longer runs inside a function) |

## What is converted

| APKBUILD | melange |
|----------|---------|
| `pkgname`, `pkgver`, `pkgdesc`, `license` | `package.*` (license is already SPDX) |
| `arch` | `target-architecture` when it is not `all`/`noarch` |
| `depends`, `provides`, `replaces` | `dependencies.*` (`so:`, `cmd:`, `pc:` and `!conflicts` dropped) |
| `makedepends*` (+ `checkdepends` with `--with-check`) | `environment.contents.packages`; musl-only packages dropped, `samurai` → `ninja` |
| `source` + `sha512sums` | `fetch` with `expected-sha512`; the main tarball is extracted into the workspace, others into `_srcdir` |
| `_pkgver=${pkgver/_rc/-rc}` used in a URL | `var-transforms` + `${{vars.mangled-pkgver}}`, and the inverse `update.version-transform` |
| Local `*.patch` | Copied next to the recipe + `uses: patch` |
| Other local files | Copied next to the recipe, available in `$srcdir` |
| `install=` scripts | `scriptlets` (apk semantics are the same, copied as is) |
| `-dev`, `-doc`, `-static`, `-libs`, `-lang`, `-*-completion` | `split/dev` (+ `depends_dev`, `test/pkgconf`), `split/alldocs`, `split/static`, `split/lib`, `split/locales`, `amove` |
| `name:func` subpackages | The function body (with `amove`), its `pkgdesc` and `depends` |
| `-openrc`, `-pyc`, `-dbg` | Skipped, with a note |
| GitHub source URL | `update.github` (tag prefix detected); otherwise `release-monitor` TODO |
| Test | `test/tw/ldd-check` for the package, `test/pkgconf` for `-dev` |

## Known limitations

- Top-level `case`/`if` blocks are not evaluated (reported as notes), e.g.
  per-architecture `options`.
- `triggers=` and git sources are reported, not converted.
- OpenRC files installed by `package()` are reported; Wolfi does not use OpenRC.
- Build flags tuned for musl may need review on glibc.
- Dependencies that exist in Alpine but not in Wolfi are flagged by
  `--check-wolfi`; they have to be packaged (or dropped) first.

## Verified

With melange v0.62.1 (bubblewrap runner), the converted `mujs` recipe builds
and passes `melange test` (ldd-check, pkgconf) unedited. It produces the same
split as Alpine (`mujs`, `-libs`, `-dev`, `-static`) and the same
`libmujs.so.3.9` with soname `libmujs.so.3`, and the binary runs.

## Tests

```bash
python3 -m unittest discover -s tools/alpine-to-melange -v
UPDATE_SNAPSHOTS=1 python3 -m unittest discover -s tools/alpine-to-melange   # after an intended change
```

`testdata/<case>/aport/` holds the input and `expected/` the converter output.
Real aports (from aports `master`, 2026-10): `libass` (autoconf,
`depends_dev`), `mujs` (make, helper variables, `local`), `zimg` (two sources,
`prepare()`, `$CARCH` case), `rubberband` (`abuild-meson`, top-level `case`),
`libplacebo` (local patch, `_pkgver`). `foobar` is synthetic: rc version with
`var-transforms`, install scripts, `name:func` subpackage with `amove`,
`-openrc`, local files in `$srcdir`, `arch` restriction, musl-only
dependencies.
