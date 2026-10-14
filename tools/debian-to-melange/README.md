# debian-to-melange

Convert Debian source packaging (`debian/`) into a [melange](https://github.com/chainguard-dev/melange)
recipe for Wolfi.

The goal is a recipe that builds with little or no editing, and an explicit
list of everything that could not be converted mechanically. Nothing is
silently dropped: unconverted pieces appear as `TODO(debian-to-melange)`
comments in the recipe and as `note:` lines on stderr.

Standard library only (Python ≥ 3.9). Validated against melange v0.62.1.

## Usage

```bash
# From sources.debian.org (latest version, or NAME=VERSION)
tools/debian-to-melange/debian-to-melange.py --from-debian stremio-server-installer --check-wolfi

# From a local checkout (path to debian/ or to the source tree)
tools/debian-to-melange/debian-to-melange.py --debian-dir ~/src/foo/debian

# Non-native package: give the upstream tarball and compute its checksum
tools/debian-to-melange/debian-to-melange.py --debian-dir foo/debian \
  --upstream-url https://example.org/foo-1.2.3.tar.gz --download
```

Output: `packages/<name>.yaml` plus `packages/<name>/` with patches, the
Debian copyright file and any generated configuration file — the same layout
used by every other recipe in this repository.

| Option | Purpose |
|--------|---------|
| `--from-debian NAME[=VERSION]` | Fetch `debian/` from sources.debian.org |
| `--debian-dir PATH` | Use a local `debian/` directory |
| `--out DIR` / `--stdout` | Output directory (default `packages`) or print the recipe |
| `--name`, `--version` | Override package name / version |
| `--version-var VAR` | `debian/rules` variable that holds the version (native packages) |
| `--upstream-url URL` | Upstream tarball; the version is templated as `${{package.version}}` |
| `--download` | Download the tarball to fill in `expected-sha256` |
| `--check-wolfi` | Verify mapped dependency names against the Wolfi APKINDEX (uses `pkg-check`); names only published by this repository are labelled `Wolfi Community Packages` |
| `--strict` | Exit 1 if anything needs manual review (for CI) |
| `--build` | Build the generated recipe with melange (bubblewrap runner, this repository's pipelines) and report the result; exit 3 if it fails |
| `--melange PATH`, `--melange-opts "..."` | melange binary and extra `melange build` options for `--build` (e.g. `--cache-dir`) |

Recommended workflow:

```bash
python3 tools/pkg-check/pkg-check.py -t wolfi -p foo        # 1. not already in Wolfi?
tools/debian-to-melange/debian-to-melange.py --from-debian foo --check-wolfi   # 2. convert
grep -n 'TODO(debian-to-melange)' packages/foo.yaml          # 3. review
melange build packages/foo.yaml --arch x86_64 ...            # 4. build and test
```

## What is converted

| Debian | melange |
|--------|---------|
| `debian/control` `Package`, `Description` | `package.name`, `package.description` |
| `debian/changelog` | `package.version` (epoch, revision and `+dfsg` stripped) |
| `debian/rules` `*VERSION` variable (native packages) | `package.version` |
| `debian/copyright` (DEP-5) | `package.copyright` with SPDX ids (`GPL-2+` → `GPL-2.0-or-later`, `Expat` → `MIT`, …) and per-path entries |
| `Depends` / `Pre-Depends` | `dependencies.runtime`, names mapped to Wolfi |
| `Recommends` | Comment (apk has no recommends) |
| `Build-Depends{,-Indep,-Arch}` | `environment.contents.packages`, names mapped to Wolfi (`librust-*-dev` dropped: cargo fetches crates). Names not found are kept with a TODO, never dropped |
| `dh $@ --buildsystem=…` or detected build files | `cmake/*`, `meson/*`, `autoconf/*`, `py/pip-build-install`, `go/build`, `cargo/build`, plain `make` |
| `override_dh_auto_configure: dh_auto_configure -- ARGS` | `with: opts: ARGS` on the configure step |
| `override_dh_auto_build`, `override_dh_auto_install` | `runs` steps with the same commands (`debian/<pkg>/` → `${{targets.destdir}}/`, `debian/<file>` copied next to the recipe, `target/$(DEB_HOST_RUST_TYPE)/` → `target/`); TODO if make or debhelper constructs remain |
| `export VAR = value` in `rules` | `environment.environment` (`$(CURDIR)` → `/home/build`; `DEB_*`, `PATH`, `CARGO_HOME`, compiler flags skipped) |
| `Files-Excluded` in `debian/copyright` | `rm -rf` step after `fetch`, so the pristine tarball matches Debian's repack |
| `debian/watch` (GitHub) | `git-checkout` with `tag` and `expected-commit` (resolved with `git ls-remote` when `--download` is given), and `update.github` |
| `debian/tests/control` (autopkgtest) | `test:` steps: `Test-Command` and `Tests` scripts (inlined, run in `$AUTOPKGTEST_TMP`); `Depends` mapped to Wolfi names |
| `debian/patches/series` | Patches copied next to the recipe + `uses: patch` |
| Extra binary packages + `*.install` | `subpackages` that move their files from `destdir` |
| Main package `*.install` when nothing is installed by the build system (cargo, go, overridden `dh_auto_install`) | Copied from the source tree |
| `*.dirs`, `*.links`, `*.docs`, `*.manpages` | `mkdir`, `ln -s`, `install` |
| Multiarch paths (`usr/lib/*/`, `$(DEB_HOST_MULTIARCH)`) | `usr/lib/` |
| `preinst` / `postinst` / `prerm` / `postrm` | `scriptlets` (see below) |
| `debian/foo.in` + `sed s/#X#/$(VAR)/` in `rules` | Script with `${{package.version}}` / `${{vars.x}}`; `VAR` becomes a melange `vars` entry |
| debconf `templates` + `db_get` | `/etc/<name>.conf` with documented defaults; `db_get` reads from it |

### Maintainer scripts

dpkg and apk call maintainer scripts with different arguments. Each Debian
script is kept verbatim inside a subshell function and called with the
arguments dpkg would have passed:

| Debian | apk scriptlet | Called as |
|--------|---------------|-----------|
| `postinst` | `post-install` | `configure` |
| `postinst` | `post-upgrade` | `configure <old-version>` |
| `preinst` | `pre-install` / `pre-upgrade` | `install` / `upgrade <old-version>` |
| `prerm` | `pre-deinstall` | `remove` |
| `postrm` | `post-deinstall` | `remove` |

`#DEBHELPER#` is removed. Debian-only helpers (`update-alternatives`,
`deb-systemd-helper`, `dpkg-maintscript-helper`, `ucf`, …) are flagged with a
TODO. Note that **apko does not run install scripts**; images built with apko
must run that logic explicitly.

### debconf

Questions from `debian/templates` (boolean, string, select) become variables
in `/etc/<name>.conf`, named `<PACKAGE>_<QUESTION>` and documented with the
template text. `. /usr/share/debconf/confmodule` is replaced by sourcing that
file, and `db_get pkg/question` by `RET="${VAR:-default}"`. Set the value
before installing to change the behaviour non-interactively.

## Known limitations

- Other `debian/rules` logic (`override_dh_*` beyond configure, build and
  install, or recipes that still need make/debhelper) is listed as a TODO with
  the original commands.
- Package name mapping is a curated table plus heuristics; use `--check-wolfi`
  to confirm names exist.
- Non-GitHub `debian/watch` files are not interpreted; pass `--upstream-url`.
- `dh --with` add-ons are reported, not converted.
- Debian-repacked tarballs (`+dfsg`/`+ds`) without a `Files-Excluded` field
  are reported for review.
- Debian-specific patches (e.g. relaxing crate versions to match Debian's
  `librust-*` packages) are copied as is; drop the ones that only make sense
  inside Debian.

## Tests

```bash
python3 -m unittest discover -s tools/debian-to-melange -v
UPDATE_SNAPSHOTS=1 python3 -m unittest discover -s tools/debian-to-melange   # after an intended change
```

Each `testdata/<case>/` holds a `debian/` input, the converter's `expected/`
output, and an optional `args` file. Cases:

- `stremio-server-installer` — real Debian contrib package: native, debconf,
  templated `postinst`. Its output is published as
  [`packages/stremio-server-installer.yaml`](../../packages/stremio-server-installer.yaml).
- `stremio` — real Debian package (1.2.0+ds-1): Rust/cargo, `override_dh_auto_build`
  and `override_dh_auto_install`, exported variables, `Files-Excluded`,
  `*.install` and `*.manpages` from the source tree, a wrapper script in `debian/`.
- `libfoo` — synthetic cmake library: multiple binaries, multiarch paths,
  patches, configure options, DEP-5 per-path licenses, GitHub watch,
  `update-alternatives` in a subpackage `postinst`.
