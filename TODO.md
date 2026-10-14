# TODO

Roadmap for the contributor tooling (`tools/`). Items marked ✅ are done;
the rest are open, roughly in priority order. Issues and pull requests that
take any of them are welcome.

## Converters (debian-to-melange, alpine-to-melange)

### Verification

- ✅ `--build`: build the generated recipe with melange right after converting
  and report the result (both converters).
- [ ] Feed the build log back into the conversion report: map common failures
  (missing `pkg-config` module, missing command, `.la` linter, unstripped
  binaries) to the dependency or step that fixes them.
- [ ] `--test`: run `melange test` after a successful build.
- [ ] CI job that converts a fixed corpus and builds the results (nightly),
  to catch regressions against current Debian/Alpine/Wolfi.

### Sources

- ✅ GitHub sources become `git-checkout` with `tag` and `expected-commit`
  (the Wolfi convention); the commit is resolved with `git ls-remote` when
  network lookups are allowed (`--download`).
- [ ] Tarballs whose entries start with `./` need `strip-components: 2`:
  detect it when the tarball is downloaded.
- [ ] Non-GitHub `debian/watch` (GitLab, PyPI, crates.io, generic HTML pages)
  and `debian/watch` v5 templates.
- [ ] `update:` from Debian's `debian/upstream/metadata` (`Repository`,
  `Bug-Database`).

### Tests

- ✅ autopkgtest (`debian/tests/control`) → melange `test:` pipeline:
  `Test-Command`, `Tests` scripts, `Depends` mapped to Wolfi names.
- [ ] Alpine `check()` → `test:` when it only exercises installed files.
- [ ] Generate a `test/tw/ver-check` for binaries that print their version.

### Name mapping

- [ ] Resolve dependencies through `pc:` and `so:` provides in the Wolfi
  index (Debian `libfoo-dev` → whatever provides `pc:foo`), instead of the
  curated table and name heuristics.
- [ ] Learn mappings from previous conversions (`--map-file`), so a
  maintainer's corrections are reused.

### Debian build systems

- [ ] Corpus of ~10 real Debian packages as test cases. Done: stremio
  (Rust), stremio-server-installer (debconf), dh-scala (Perl), scala-2.13
  (self-hosting JVM compiler). Missing: Go with vendored modules, Python
  (pybuild), CMake with several binary packages, Node.js, a library with a
  symbols file.
- ✅ Build profiles (`<pkg.x.stage0>`, `<!nocheck>`) evaluated for a normal build.
- ✅ Perl (`libfoo-perl` → `perl-foo`) and JDK names; Java libraries flagged
  (Wolfi uses Maven Central); `libjs-*` and Debian Java helpers dropped.
- ✅ `debian/watch` v5 in git mode → `git-checkout`.
- ✅ Self-hosting packages (build-depend on themselves) are reported.
- [ ] `debian/*.poms` (maven-repo-helper) → install jars under
  `/usr/share/java` with the same names.
- [ ] Ported `debian/rules` recipes that use make functions (`$(firstword
  ...)`, `$(subst ...)`): evaluate the common ones.
- [ ] `dh-sequence-*` / `--with` add-ons that map to melange pipelines
  (python3, golang, nodejs).
- [ ] `debian/*.symbols` → `so:` provides check in the test section.
- [ ] `debian/*.service`, `*.tmpfiles`, `*.sysusers` → Wolfi equivalents.
- [ ] Multi-arch `Architecture:` restrictions → `target-architecture`.

### Scala / JVM

- [ ] A melange `scala/build` pipeline equivalent to dh-scala, reading the
  same `debian/scala-build` file, so dh-scala packages convert directly.
- [ ] `scala-2.13-stage0` recipe from upstream binaries, then `scala-2.13`
  built from source (Wolfi has scala 3.8 and sbt, not 2.12/2.13).

### Alpine

- [ ] Evaluate simple top-level `case "$CARCH"` blocks for x86_64/aarch64.
- [ ] Convert `triggers=` into documented notes or `scriptlets: trigger`.
- [ ] Detect bundled meson subprojects that need `--force-fallback-for`.

## New direction: melange → Debian (`melange-to-debian`)

Many packages exist in Wolfi but not in Debian. An initial `debian/`
directory generated from a melange recipe would speed up ITPs:

- [ ] `debian/control` from `package`, `dependencies`, `environment`
  (Wolfi → Debian name mapping, the reverse of the converters' tables).
- [ ] `debian/copyright` (DEP-5) from the SPDX `copyright` entries.
- [ ] `debian/rules` with `dh` and the buildsystem detected from the
  pipelines (`meson/*`, `cmake/*`, `autoconf/*`, `go/build`, `cargo/build`).
- [ ] `debian/watch` from `update:` (GitHub, release-monitor).
- [ ] `debian/patches/` + `series` from `uses: patch`.
- [ ] Subpackages (`split/dev`, `-doc`) → binary packages and `.install` files.

With the three converters, melange becomes a pivot format between Debian,
Alpine and Wolfi.

## Distribution of the tools

- [ ] Publish the converters as a standalone project (PyPI and a Debian
  package, e.g. `melange-converters`), GPL-3.0-or-later.
- [ ] Man pages for the three tools.
- [ ] `pkg-check --target debian` against a configurable suite (stable,
  testing, unstable).

## Repository / CI

- ✅ Build only changed recipes, in dependency waves (`scripts/build-order.py`).
- [ ] aarch64 builds with the wave workflow.
- [ ] Publish from the wave workflow automatically after merge, with a
  summary of what changed in the index.
