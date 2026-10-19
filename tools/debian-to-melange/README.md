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
tools/debian-to-melange/debian-to-melange.py --from-debian stremio-server-installer

# From a local checkout (path to debian/ or to the source tree)
tools/debian-to-melange/debian-to-melange.py --debian-dir ~/src/foo/debian

# Non-native package: give the upstream tarball and compute its checksum
tools/debian-to-melange/debian-to-melange.py --debian-dir foo/debian \
  --upstream-url https://example.org/foo-1.2.3.tar.gz --download
```

Output: `packages/<name>.yaml` plus `packages/<name>/` with patches and any
generated configuration file — the same layout used by every other recipe in
this repository. The Debian copyright file is copied there only when upstream
has no license file to install.

| Option | Purpose |
|--------|---------|
| `--from-debian NAME[=VERSION]` | Fetch `debian/` from sources.debian.org |
| `--debian-dir PATH` | Use a local `debian/` directory |
| `--out DIR` / `--stdout` | Output directory (default `packages`) or print the recipe |
| `--name`, `--version` | Override package name / version |
| `--version-var VAR` | `debian/rules` variable that holds the version (native packages) |
| `--upstream-url URL` | Upstream tarball; the version is templated as `${{package.version}}` |
| `--download` | Download the tarball to fill in `expected-sha256` |
| `--no-check-wolfi` | Do not download the Wolfi APKINDEX. By default mapped names are checked against it (uses `pkg-check`), and names only published by this repository are labelled `Wolfi Community Packages` |
| `--spdx-license ID` | Write an SPDX header for the recipe itself, with `--author` (default `$DEBFULLNAME <$DEBEMAIL>`) |
| `--strict` | Exit 1 if anything needs manual review (for CI) |
| `--build` | Build the generated recipe with melange (bubblewrap runner, this repository's pipelines) and report the result; exit 3 if it fails |
| `--melange PATH`, `--melange-opts "..."` | melange binary and extra `melange build` options for `--build` (e.g. `--cache-dir`) |

Recommended workflow:

```bash
python3 tools/pkg-check/pkg-check.py -t wolfi -p foo        # 1. not already in Wolfi?
tools/debian-to-melange/debian-to-melange.py --from-debian foo   # 2. convert
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
| `Build-Depends{,-Indep,-Arch}` | `environment.contents.packages`, names mapped to Wolfi (`librust-*-dev` dropped: cargo fetches crates). Names not in Wolfi are left out as a TODO comment, so the environment still resolves |
| Build profiles (`<!nocheck>`, `<pkg.foo.stage0>`) | Evaluated for a normal build: dependencies only needed under a profile are left out |
| `libfoo-perl`, `openjdk-N-jdk`, `default-jdk` | `perl-foo`, `openjdk-N`, `openjdk-25-default-jdk`; `lib*-java` flagged (Wolfi fetches jars from Maven Central); `libjs-*` and Debian Java helpers dropped |
| autoconf with debhelper ≥ 10 and no generated `configure` (git checkouts) | `autoreconf -fi` step, with `autoconf`, `automake` (and `libtool`, `gettext-dev` when `configure.ac` uses them) |
| Upstream `COPYING`, `LICENSE`, … | Installed in `/usr/share/licenses/<name>`, and checked by the test |
| Architecture-dependent binaries | `strip` step and a `test/tw/ldd-check` test |
| `dh $@ --buildsystem=…` or detected build files | `cmake/*`, `meson/*`, `autoconf/*`, `py/pip-build-install`, `go/build`, `cargo/build`, `scala/build` (dh-scala, with `debian/scala-build` copied next to the recipe), plain `make` |
| `override_dh_auto_configure: dh_auto_configure -- ARGS` | `with: opts: ARGS` on the configure step |
| `override_dh_auto_build`, `override_dh_auto_install` | `runs` steps with the same commands (`debian/<pkg>/` → `${{targets.destdir}}/`, `debian/<file>` copied next to the recipe, `target/$(DEB_HOST_RUST_TYPE)/` → `target/`); TODO if make or debhelper constructs remain |
| `export VAR = value` in `rules` | `environment.environment` (`$(CURDIR)` → `/home/build`; `DEB_*`, `PATH`, `CARGO_HOME`, compiler flags skipped) |
| `Files-Excluded` in `debian/copyright` | `rm -rf` step after `fetch`, so the pristine tarball matches Debian's repack |
| `debian/watch` (GitHub, or v5 git mode on any forge) | `git-checkout` with `tag` and `expected-commit` (resolved with `git ls-remote` when `--download` is given), and `update.github` or `update.git` |
| `debian/tests/control` (autopkgtest) | `test:` steps: `Test-Command` and `Tests` scripts (inlined, run in `$AUTOPKGTEST_TMP`); `Depends` mapped to Wolfi names. A test whose dependencies are not in Wolfi is left out as a TODO comment |
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
- Package name mapping is a curated table plus heuristics, checked against
  the Wolfi index unless `--no-check-wolfi` is given.
- Tarball `debian/watch` files on sites other than GitHub are not interpreted; pass `--upstream-url`.
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
- `dh-scala` — real package (Debian Java team): Perl, two binary packages,
  `libfoo-perl` → `perl-foo`, `default-jdk-headless` → `openjdk-25-default-jdk`,
  five autopkgtests.
- `scala-2.13` — real package (Debian Java team): self-hosting compiler with
  build profiles (`<pkg.scala.stage0>`), `debian/watch` v5 in git mode, Java
  library dependencies, `update-alternatives` in maintainer scripts.
- `xwpe` — real package (same maintainer in Debian and upstream):
  `debian/watch` v5 in git mode on Codeberg, autopkgtests with X11 tools.
- `libfoo` — synthetic cmake library: multiple binaries, multiarch paths,
  patches, configure options, DEP-5 per-path licenses, GitHub watch,
  `update-alternatives` in a subpackage `postinst`.
