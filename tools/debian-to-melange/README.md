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
| `--download` | Allow network lookups: tarball checksum, git commits, Debian virtual packages, release-monitoring.org ids |
| `--no-check-wolfi` | Do not download the Wolfi APKINDEX. By default mapped names are checked against it (uses `pkg-check`), and names only published by this repository, or defined by its recipes, are labelled `Wolfi Community Packages` |
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
| `debian/control` `Package`, `Description` | `package.name`, `package.description`; `libfoo1` is named after the source (`libfoo`); udebs are left out |
| `debian/changelog` | `package.version` (epoch, revision and `+dfsg` stripped, `+git20170224` → `_git20170224`, `~rc1` → `_rc1`) |
| `debian/rules` `*VERSION` variable (native packages) | `package.version` |
| `debian/copyright` (DEP-5) | `package.copyright` with SPDX ids (`GPL-2+` → `GPL-2.0-or-later`, `Expat` → `MIT`, …) and per-path entries; for free-form files, the license is read from the GPL/LGPL/MIT/BSD/Apache notice |
| `Depends` / `Pre-Depends` | `dependencies.runtime`, names mapped to Wolfi |
| `Recommends` | Comment (apk has no recommends); installed for autopkgtests that depend on `@`, as autopkgtest does |
| `Build-Depends{,-Indep,-Arch}` | `environment.contents.packages`, names mapped to Wolfi (`librust-*-dev` dropped: cargo fetches crates). Virtual packages are resolved through packages.debian.org; bundles (`x11-apps`, `x11-utils`, `x11-xserver-utils`) become the programs Wolfi has. Names not in Wolfi are left out as a TODO comment, so the environment still resolves |
| Build profiles (`<!nocheck>`, `<pkg.foo.stage0>`) | Evaluated for a normal build: dependencies only needed under a profile are left out |
| `libfoo-perl`, `openjdk-N-jdk`, `default-jdk` | `perl-foo`, `openjdk-N`, `openjdk-25-default-jdk`; `lib*-java` flagged (Wolfi fetches jars from Maven Central); `libjs-*` and Debian Java helpers dropped |
| autoconf with debhelper ≥ 10 and no generated `configure` (git checkouts), or Debian patches changing `configure.ac`, `*.am`, `*.m4` or `*.mk` | `autoreconf -fi` step, with `autoconf`, `automake` (and `libtool`, `gettext-dev` when `configure.ac` uses them) |
| Upstream `COPYING`, `LICENSE`, … | Installed in `/usr/share/licenses/<name>`, and checked by the test |
| Architecture-dependent binaries | `strip` step and a `test/tw/ldd-check` test |
| `dh $@ --buildsystem=…` or detected build files | `cmake/*`, `meson/*`, `autoconf/*`, `py/pip-build-install`, `go/build`, `cargo/build`, `scala/build` (dh-scala, with `debian/scala-build` copied next to the recipe), plain `make` |
| `libfoo-perl` (Makefile.PL) | `perl-<CPAN distribution>`; `perl/make`, `autoconf/make`, `autoconf/make-install`, `perl/cleanup`; sources from CPAN; Debian's `usr/share/perl5` and `usr/lib/*/perl5` are Wolfi's `vendor_perl`; a test that loads the module named in `debian/tests/pkg-perl/use-name` |
| Debian-native programs (ucf, debconf, init-system-helpers) | Source from the Debian archive; perl and dpkg-dev in the build, as debhelper brings them |
| `python3-foo` (pybuild, `Architecture: all`) | The Wolfi layout: empty `py3-foo`, one `py3.X-foo` per supported Python (those with all the dependencies), `py3-supported-foo`; `${python3:Depends}` from upstream's `install_requires`/`dependencies`; `python/import` tests |
| `override_dh_update_autotools_config`, `override_dh_autoreconf` (e.g. `./autogen.sh`) | A step before configure, with autoconf, automake and libtool |
| `override_dh_auto_configure: dh_auto_configure -- ARGS` | `with: opts: ARGS` on the configure step |
| `override_dh_auto_build`, `override_dh_auto_install` | `runs` steps with the same commands (`debian/<pkg>/` → `${{targets.destdir}}/`, `debian/<other-pkg>/` → `${{targets.outdir}}/<other-pkg>/`, `debian/<file>` copied next to the recipe, `target/$(DEB_HOST_RUST_TYPE)/` → `target/`). `dh_auto_build`/`dh_auto_install` become `make` (`-D dir` → `-C dir`, `-- ARGS` kept) or the build system's pipeline; the `-B` build of a udeb is dropped. TODO if make or debhelper constructs remain |
| `export VAR = value` in `rules` | `environment.environment` (`$(CURDIR)` → `/home/build`; `DEB_*`, `PATH`, `CARGO_HOME`, compiler flags skipped) |
| `Files-Excluded` in `debian/copyright` | `rm -rf` step after `fetch`, so the pristine tarball matches Debian's repack |
| `debian/watch` (GitHub, git mode on any forge) | `git-checkout` with `tag` and `expected-commit` (resolved with `git ls-remote` when `--download` is given), and `update.github` or `update.git`. A `+gitYYYYMMDD` snapshot is pinned to the last commit of that day |
| `debian/watch` with a plain tarball URL (PyPI, `@ARCHIVE_EXT@`) | `fetch` of the first URL that exists; `update.github` when the Homepage is on GitHub, otherwise the release-monitoring.org project with that name |
| `debian/tests/control` (autopkgtest) | `test:` steps: the upstream source is checked out first (autopkgtest runs in the source tree), then `Test-Command` and `Tests` scripts (inlined, run in the source tree with `$AUTOPKGTEST_TMP` set); `Restrictions: flaky` failures are reported, not fatal; `Depends` mapped to Wolfi names, plus Debian's Essential packages (bash, coreutils, dpkg, …) that every testbed has. A test whose dependencies are not in Wolfi is left out as a TODO comment. The testbed is emulated: a dpkg database lists the installed apk packages (also under the Debian names of the test's dependencies, with the package's debconf templates), `debian/` of a non-native package is fetched when a test reads it, `AUTOPKGTEST_NORMAL_USER` is `build`, and commands the scripts call (`runuser`, `dpkg-parsechangelog`, …) are added. `mmdebstrap --mode=fakechroot` of a Debian chroot is left out (Wolfi's glibc is newer than the chroot's), the rest of that test kept |
| `debian/patches/series` | Patches copied next to the recipe + `uses: patch` |
| Extra binary packages + `*.install` | `subpackages` that move their files from `destdir` |
| Main package `*.install` when nothing is installed by the build system (cargo, go, overridden `dh_auto_install`) | Copied from the source tree |
| dh-exec `src => dest` in `*.install` | Copied under the new name |
| `*.dirs`, `*.links`, `*.docs`, `*.examples`, `*.manpages`, `*.service` | `mkdir`, `ln -s`, `cp`, `install`; units in `/usr/lib/systemd/system` |
| `*.xmlcatalogs` (`dh_installxmlcatalogs`) | The package's catalog installed, and scriptlets that add (and remove) its delegate entries in `/etc/xml/catalog` with libxml2's `xmlcatalog` (Wolfi has no xml-core) |
| Build-depends on `libncurses-dev` | Debian's `include/ncursesw/` header directory (symlinks), in the build and the tests |
| Shell scripts with `#!/bin/bash` in the source | `bash` in the build environment (Essential in Debian) |
| `getopt`, `setpriv` in the source's shell scripts | `util-linux-misc`, `setpriv` (busybox's lack options of Debian's Essential util-linux): runtime dependencies, and in the tests |
| Build-depends on fontconfig or Xft | Runtime dependency on `ttf-dejavu` (Debian's fontconfig always brings a font; Wolfi's does not) |
| `usr/sbin`, `sbin`, `bin`, `lib` destinations | `usr/bin`, `usr/lib` (Wolfi is usr-merged, with sbin merged into bin) |
| Multiarch paths (`usr/lib/*/`, `$(DEB_HOST_MULTIARCH)`) | `usr/lib/` |
| `preinst` / `postinst` / `prerm` / `postrm` | `scriptlets` (see below); commands they call (`update-alternatives`, `ucf`, `invoke-rc.d`, …) become runtime dependencies on the package that has them; the links `update-alternatives --install` would make (highest priority, slaves included) are shipped in the package, since apko does not run the scripts |
| Target-specific variables of `-arch`/`-indep` overrides | The `-indep` value (a full build runs both, `-indep` last) |
| Other `override_dh_*` / `execute_*_dh_*` targets | Their own commands, after the build or on the installed files (`$(DEB_VERSION)`, `$$`, `$(RM)` expanded) |
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

`#DEBHELPER#` is removed. `update-alternatives` and the other dpkg tools come
from Wolfi's dpkg; `ucf`, `invoke-rc.d` and `deb-systemd-helper` from this
repository's ucf and init-system-helpers. Note that **apko does not run install scripts**; images built with apko
must run that logic explicitly.

### debconf

Questions from `debian/templates` (boolean, string, select) become variables
in `/etc/<name>.conf`, named `<PACKAGE>_<QUESTION>` and documented with the
template text. `. /usr/share/debconf/confmodule` is replaced by sourcing that
file, and `db_get pkg/question` by `RET="${VAR:-default}"`. Set the value
before installing to change the behaviour non-interactively.

### debian/rules details

- `override_dh_x-arch` and `-indep` are merged into one step (one melange build makes
  both), with their target-specific variables (`target: VAR=value`) joined.
- `override_dh_install` is split at its `dh_install` call: commands before it run
  before the install step, those after it on the installed files; other overrides
  follow dh's sequence (dh_install, dh_installdocs, ..., dh_installman, ...).
- `dh_install -pPKG -Xpattern` excludes are honoured; `dh_installman FILES` installs them.
- `dh_gencontrol -Vname=value` substvars are put into Depends; a value chosen with
  `$(shell test -e /usr/bin/X && echo A || echo B)` is A when X is a build dependency.
- `dh --buildsystem=cmake+ninja` uses the cmake pipelines; CMake projects whose Debian
  `.install` files use `usr/lib/<package>/` get `-DCMAKE_INSTALL_LIBEXECDIR=lib`.
- Runtime dependencies Debian leaves implicit are added: `${perl:Depends}` (perl, and
  perl-ph-headers when the Perl code requires `*.ph`), Essential packages named in
  Breaks/Conflicts (libapt-pkg: dpkg), GNU `getopt` used by shell scripts
  (util-linux-misc), and libraries with an unversioned soname (libdb-5.3.so), for which
  melange derives no `so:` dependency.
- `update-alternatives --install` in a postinst becomes the links themselves (the
  highest priority wins), since apko does not run maintainer scripts.

## Known limitations

- Other `debian/rules` logic (`override_dh_*` beyond configure, build and
  install, or recipes that still need make/debhelper) is listed as a TODO with
  the original commands.
- Package name mapping is a curated table plus heuristics, checked against
  the Wolfi index unless `--no-check-wolfi` is given.
- `debian/watch` files that scrape a download page are not interpreted; with `--download`
  the converter falls back to Debian's copy of the upstream tarball, or CPAN for Perl modules.
- `dh --with` add-ons are reported, not converted.
- Debian-repacked tarballs (`+dfsg`/`+ds`) without a `Files-Excluded` field
  are reported for review; without a `debian/watch`, Debian's repack is the
  source (docbook-xsl).
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
- `pyte` — real package (Debian Python team): pybuild, `python3-pyte` →
  `py3-pyte` in the Wolfi Python layout, requirements from `setup.py`,
  PyPI tarball from `debian/watch`, Sphinx documentation subpackage.
- `libfoo` — synthetic cmake library: multiple binaries, multiarch paths,
  patches, configure options, DEP-5 per-path licenses, GitHub watch,
  `update-alternatives` in a subpackage `postinst`.
