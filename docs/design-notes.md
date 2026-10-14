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
changed recipes. A change to `pipelines/` or to the build workflows
rebuilds everything. A new push to a pull request cancels the build of the
previous commit.

A source download that fails with a network error (DNS, or a runner without
an IPv6 route) is retried once. Other failures are not retried.

## Architectures

x86_64 and aarch64 are built on GitHub's native runners
(`ubuntu-24.04-arm` for aarch64, without emulation). qt5-qtwebengine does not
finish on an ARM runner within the 6-hour job limit. It is listed in
`packages/CI-SKIP` instead of being limited with `target-architecture`, so
the recipe still builds for aarch64 elsewhere (Cirrus CI, see
`.cirrus.yml.disabled`, or locally). The publish workflow only downloads
Cirrus artifacts while `.cirrus.yml` exists.

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

## AppStream tarball

The entries in the AppStream release tarball begin with
`./AppStream-<version>/`, so the `fetch` step uses `strip-components: 2`
instead of the default of 1.

## Retired packages

`packages/RETIRED` lists origins that the publish workflow removes from
the repository, usually because Wolfi now provides them. Old files stay on
SourceForge, because uploads never delete, so the filter runs on every
publish.

An entry can be limited to a version range when a new recipe reuses a
name: `stremio>=4` removes the old 4.x builds and keeps `stremio` 1.x.
