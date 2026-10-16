# Design notes

Decisions that are not obvious from the recipes alone.

## Build waves in CI

Some recipes build-depend on packages from other recipes in this
repository (for example, `stremio` needs `webkitgtk-6.0`, which needs
`libsoup3`). `scripts/build-order.py` sorts the selected recipes into
waves. Each wave downloads the packages built by earlier waves in the same
run, indexes them, and adds them as a local repository.

This allows a dependency chain to be built and tested in one run, without
first publishing the intermediate packages. Pull requests rebuild only the
changed recipes. A new push to a pull request cancels the build of the
previous commit.

A change to `pipelines/` or to the build workflows selects every recipe,
but a recipe whose version and epoch are already published for an
architecture is not rebuilt; three small canary recipes (mujs, libxmlb and
appstream, which uses the other two across waves) always are. This keeps
such changes from rebuilding qt5-qtwebengine, about three hours. A manual
run of the workflow without a filter rebuilds everything.

A source download that fails with a network error (DNS, or a runner without
an IPv6 route) is retried once. Other failures are not retried.

## Architectures

x86_64 and aarch64 are built on GitHub's native runners
(`ubuntu-24.04-arm` for aarch64, without emulation). qt5-qtwebengine does not
finish on an ARM runner within the 6-hour job limit. It is listed in
`packages/CI-SKIP` instead of being limited with `target-architecture`, so
the recipe still builds for aarch64 elsewhere (Cirrus CI, see
`.cirrus.yml.disabled`, or locally). stremio-qt5 for aarch64 is skipped as
well, because it needs that qt5-qtwebengine. The publish workflow only
downloads Cirrus artifacts while `.cirrus.yml` exists.

The aarch64 builds of both published earlier came from Cirrus and need
`libvpx.so.11`, which Wolfi no longer has. They are retired for aarch64;
they can be rebuilt on request.

## Rust: crates from `Cargo.lock`

Debian builds Rust programs against its packaged `librust-*` crates. Wolfi
builds from crates.io with the versions pinned in upstream's `Cargo.lock`,
using `cargo auditable` so the dependency list is embedded in the binary
and visible to vulnerability scanners. This repository follows the Wolfi
convention, so Debian's patches that change crate versions are not
applied to `stremio`.

## stremio and stremio-qt5

Upstream replaced the Qt5 shell (4.x) with a GTK4/WebKitGTK client (1.x).
The new client is packaged as `stremio`, matching upstream and Debian. The
Qt5 shell remains available as `stremio-qt5`, which installs
`/usr/bin/stremio-qt5` so both can be installed at the same time.

`data/server.js` is removed from the source because it is not free
software, as in Debian's `+ds` tarball. `stremio-server-installer`
downloads it at install time.

## GSettings schema for stremio

Wolfi provides no install trigger to recompile the shared GSettings
schema cache. The `stremio` schema is therefore compiled at build time
into `/usr/share/stremio/schemas`, and the `/usr/bin/stremio` wrapper adds
that directory to `GSETTINGS_SCHEMA_DIR`. No shared file is modified.

## WebKitGTK options

WebKitGTK is built with clang and lld and without debug information.
Otherwise the build tree does not fit on a standard CI runner.
These features are disabled because their dependencies are not available
in Wolfi: gamepad (libmanette), speech synthesis (flite), hyphenation
(hyphen) and Sysprof tracing. GObject introspection, MiniBrowser and
WebDriver are also disabled because no package here uses them.

## Scala 2.12 and 2.13 without sbt

`scala-2.12` and `scala-2.13` follow the Debian packages of the same name:
`build-driver.sh` compiles each module directly with scalac and javac, in
two passes. Pass 1
uses upstream's pinned bootstrap compiler (STARR) and pass 2 uses the
pass-1 compiler; only pass-2 jars are installed. Debian needs a separate
stage0 package for pass 1; Wolfi builds may download from Maven Central,
so the STARR jars and the libraries the compiler uses (scala-asm, jline,
java-diff-utils or scala-xml, the jQuery webjar for scaladoc) are fetched
with pinned checksums. Each recipe checks the pins against upstream's
`versions.properties` and `build.sbt`.

The sources of each module are passed to scalac in sorted order. In
`find`'s order, which depends on the file system, scaladoc failed to
compile with a `CyclicReference` error.

## VLC

VLC 3.0 with the Qt5 interface. Wolfi is moving to OpenSSL 4: libarchive-dev
and libssh2-dev already need it, while qt5-qtbase-dev needs 3.6, so VLC is
built without archive and SFTP access. Wolfi's libsrt, which ffmpeg uses,
depends on `pc:openssl`; the recipe lists `openssl-dev<4` so that apk does
not choose OpenSSL 4 for it.

No plugin cache (`plugins.dat`) is shipped: melange resets file dates when
packaging, which makes a cache written at build time stale, and Wolfi has no
install triggers to write it later. VLC scans its plugins at startup.
Hardware decoding uses VA-API; Wolfi's ffmpeg is built without VDPAU.

## Scala libraries: scala/build

The `scala/build` pipeline reads the `scala-build` file of Debian's dh-scala,
so a library packaged for Debian with dh-scala is built here from the same
file. The Python script is embedded in the pipeline because melange
pipelines cannot ship extra files; `scripts/test_scala_build.py` extracts and
tests it. See [scala-build.md](scala-build.md).

## Retired packages

`packages/RETIRED` lists origins that the publish workflow removes from
the repository, usually because Wolfi now provides them. Old files stay on
SourceForge, because uploads never delete, so the filter runs on every
publish.

An entry can be limited to a version range when a new recipe reuses a
name: `stremio>=4` removes the old 4.x builds and keeps `stremio` 1.x.
Architecture names after an entry limit it to those architectures.
