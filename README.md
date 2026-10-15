# Wolfi Community Packages

[![Packages](https://img.shields.io/badge/packages-33-brightgreen)](#available-packages)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/vejeta/wolfi-packages)](https://github.com/vejeta/wolfi-packages/commits)
[![Build Packages](https://github.com/vejeta/wolfi-packages/actions/workflows/build-packages.yml/badge.svg)](https://github.com/vejeta/wolfi-packages/actions)
[![SourceForge](https://img.shields.io/badge/Download-SourceForge-orange)](https://sourceforge.net/projects/wolfi/)

<a href="https://sourceforge.net/projects/wolfi/"><img src="https://sourceforge.net/cdn/syndication/badge_img/3927420/oss-rising-star-white" width="125" alt="SourceForge Rising Star"></a>

An APK repository for [Wolfi OS](https://wolfi.dev) with packages that are
not in the official [wolfi-dev/os](https://github.com/wolfi-dev/os)
repository. The project is independent of Chainguard.

The recipes are [melange](https://github.com/chainguard-dev/melange) YAML
files in [`packages/`](packages/). GitHub Actions builds them, and the signed
packages and `APKINDEX` are published on SourceForge.

## Available packages

| Package | Version | Description | License |
|---------|---------|-------------|---------|
| appstream | 1.2.1 | AppStream metadata library (library only; needed by libadwaita) | LGPL-2.1-or-later |
| glib-networking | 2.90.0 | Network extensions for GLib: TLS support (GnuTLS) | LGPL-2.0-or-later |
| libadwaita | 1.10.0 | Building blocks for modern GNOME applications (GTK4) | LGPL-2.1-or-later |
| libass9 | 0.17.5 | Portable library for rendering ASS/SSA subtitles (shared; official Wolfi's libass is static-only) | ISC |
| libbluray | 1.4.0 | Library to access Blu-Ray disks for video playback | LGPL-2.1-or-later |
| libcdio | 2.2.0 | GNU Compact Disc Input and Control Library | GPL-3.0-or-later |
| libcdio-paranoia | 10.2.2.0.2 | CD paranoia library from libcdio | GPL-3.0-or-later AND LGPL-2.1-or-later |
| libdvdnav | 6.1.1 | Library for DVD navigation | GPL-2.0-or-later |
| libdvdread | 6.1.3 | Library for reading DVD video disks | GPL-2.0-or-later |
| libfyaml | 0.9.6 | Fully featured YAML 1.2 parser and emitter (needed by appstream) | MIT |
| libplacebo | 7.351.0 | Reusable library for GPU-accelerated video/image rendering | LGPL-2.1-or-later |
| libsoup3 | 3.6.6 | GNOME HTTP client/server library, version 3 | LGPL-2.0-or-later |
| libxmlb | 0.3.29 | Library to create and query binary XML blobs (needed by appstream) | LGPL-2.1-or-later |
| libxpresent | 1.0.2 | X11 Present extension library | MIT |
| mpv | 0.40.0 | Free, open source, and cross-platform media player | GPL-2.0-or-later AND LGPL-2.1-or-later |
| mujs | 1.3.7 | Lightweight JavaScript interpreter | ISC |
| qt5-qtdeclarative | 5.15.17 | Qt5 - QtDeclarative (QML/QtQuick) components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtquickcontrols | 5.15.17 | Qt5 - QtQuick Controls 1 components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtquickcontrols2 | 5.15.17 | Qt5 - QtQuick Controls 2 components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtwebchannel | 5.15.17 | Qt5 - QtWebChannel (bidirectional client-server communication) | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtwebengine | 5.15.17 | Qt5 - QtWebEngine (Chromium-based web rendering) | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| rubberband | 4.0.0 | Audio time-stretching and pitch-shifting library | GPL-2.0-or-later |
| scala-2.12 | 2.12.21 | Scala 2.12 compiler and tools (`scalac-2.12`, `scala-2.12`, `scaladoc-2.12`), built from source without sbt | Apache-2.0 |
| scala-2.13 | 2.13.18 | Scala 2.13 compiler and tools (`scalac-2.13`, `scala-2.13`, `scaladoc-2.13`), built from source without sbt | Apache-2.0 |
| scala-xml | 2.5.0 | Scala XML library for Scala 3; `scala-xml-2.13` and `scala-xml-2.12` for Scala 2. Built with the `scala/build` pipeline | Apache-2.0 |
| shaderc | 2025.4 | Tools and libraries for Vulkan shader compilation | Apache-2.0 |
| stremio | 1.2.0 | Modern media center (Stremio desktop 1.x: GTK4, libadwaita, WebKitGTK); converted from the [Debian package](https://tracker.debian.org/pkg/stremio) with `debian-to-melange` | GPL-3.0-only |
| stremio-qt5 | 4.4.169 | Modern media center for online video content (Stremio shell 4.x, Qt5) | GPL-3.0-or-later |
| stremio-server-installer | 4.21.1 | Downloader for Stremio's streaming server (server.js is fetched at install time, never redistributed) | GPL-3.0-only |
| uchardet | 0.0.8 | Universal charset detection library | MPL-1.1 OR GPL-2.0-or-later OR LGPL-2.1-or-later |
| webkitgtk-6.0 | 2.54.1 | WebKitGTK web engine, GTK4 API (webkitgtk-6.0) | LGPL-2.0-or-later AND BSD-2-Clause |
| xdg-dbus-proxy | 0.1.9 | Filtering D-Bus proxy (used by the WebKitGTK sandbox) | LGPL-2.1-or-later |
| zimg | 3.0.6 | Scaling, colorspace conversion, and dithering library | WTFPL |

The recipes in [`packages/`](packages/) are the reference for versions.
Packages are built for x86_64 and aarch64, except qt5-qtwebengine and
stremio-qt5, which are x86_64 only: qt5-qtwebengine takes longer than
GitHub's 6-hour job limit on ARM runners (see [`packages/CI-SKIP`](packages/CI-SKIP)).
Scala libraries can be built from a dh-scala `scala-build` file with the
`scala/build` pipeline ([docs/scala-build.md](docs/scala-build.md)).

## Using these packages

Repository base URL and signing key:

```
Repository: https://downloads.sourceforge.net/project/wolfi
Key:        https://downloads.sourceforge.net/project/wolfi/keys/vejeta-wolfi.rsa.pub
Browse:     https://sourceforge.net/projects/wolfi/files/
```

`apk`, melange and apko append the architecture (`x86_64/`, `aarch64/`) to the
base URL automatically.

### On a running Wolfi system

```bash
wget -O /etc/apk/keys/vejeta-wolfi.rsa.pub \
  https://downloads.sourceforge.net/project/wolfi/keys/vejeta-wolfi.rsa.pub
echo "https://downloads.sourceforge.net/project/wolfi" >> /etc/apk/repositories
apk update
apk add mpv stremio        # or stremio-qt5 for the Qt5 shell
```

`stremio` is the Stremio desktop client 1.x (GTK4/WebKitGTK). `stremio-qt5`
is the earlier Qt5 shell 4.x, installed as `stremio-qt5`; both can be
installed together. Systems that have `stremio` 4.x from this repository
need `apk del stremio && apk add stremio stremio-qt5`, because apk does not
replace a package with a lower version.

### As build dependencies in a melange recipe

```yaml
package:
  name: my-player
  version: 1.0.0
  epoch: 0
  description: Example package linking against libmpv
  copyright:
    - license: GPL-3.0-or-later

environment:
  contents:
    keyring:
      - https://packages.wolfi.dev/os/wolfi-signing.rsa.pub
      - https://downloads.sourceforge.net/project/wolfi/keys/vejeta-wolfi.rsa.pub
    repositories:
      - https://packages.wolfi.dev/os
      - https://downloads.sourceforge.net/project/wolfi
    packages:
      - build-base
      - mpv-dev
      - libass9-dev

pipeline:
  # ...
```

### In an apko image

```yaml
contents:
  keyring:
    - https://packages.wolfi.dev/os/wolfi-signing.rsa.pub
    - https://downloads.sourceforge.net/project/wolfi/keys/vejeta-wolfi.rsa.pub
  repositories:
    - https://packages.wolfi.dev/os
    - https://downloads.sourceforge.net/project/wolfi
  packages:
    - wolfi-base
    - mpv

entrypoint:
  command: /usr/bin/mpv

archs:
  - x86_64
```

### In a Dockerfile

```dockerfile
FROM cgr.dev/chainguard/wolfi-base

RUN wget -O /etc/apk/keys/vejeta-wolfi.rsa.pub \
      https://downloads.sourceforge.net/project/wolfi/keys/vejeta-wolfi.rsa.pub \
 && echo "https://downloads.sourceforge.net/project/wolfi" >> /etc/apk/repositories \
 && apk add --no-cache mpv
```

## Retired packages

Packages are retired when an official or better-suited alternative exists.

| Package | Here since | In official Wolfi since¹ | Retired | Reason / replacement |
|---------|------------|--------------------------|---------|----------------------|
| libass | 2025-11 | 2026-01-31 | 2026-10 | Replaced by `libass9`: official Wolfi's libass is built static-only and ships no `libass.so` |
| stremio 4.x | 2025-11 | — | 2026-10 | Renamed to `stremio-qt5` (Stremio shell 4.x, Qt5). The name `stremio` now belongs to the GTK4/WebKitGTK client (1.x) |
| stremio-server | 2025-11 | — | 2026-10 | Replaced by `stremio-server-installer`, converted from the [Debian package](https://tracker.debian.org/pkg/stremio-server-installer) with `debian-to-melange` |
| libvpx | 2025-11 | 2026-09-25 | 2026-10 | Available in official Wolfi (newer version) |
| libxcb | 2025-11 | 2025-08-07 or earlier | 2026-10 | Available in official Wolfi (all xcb libraries in one package) |
| vulkan-loader | 2025-11 | 2025-09-26 or earlier | 2026-10 | Available in official Wolfi (newer version) |
| zlib | 2025-11 | 2025-01-16 or earlier | 2026-10 | Available in official Wolfi (newer version) |
| qt5-qtbase | 2025-11 | 2026-04-01 | 2026-10 | Available in official Wolfi (5.15.19); the Qt5 modules here build against it |
| qt5-qtwebengine, stremio-qt5 (aarch64) | 2025-11 | — | 2026-10 | Old builds that need `libvpx.so.11`, no longer in Wolfi; x86_64 builds remain. Rebuilt on request |

¹ Earliest build of the package in the official Wolfi APKINDEX (x86_64), checked 2026-10-14.

Retired packages are listed in [`packages/RETIRED`](packages/RETIRED); every publish
removes them, and their subpackages, from the repository index.

Recipes of retired packages stay in the git history. To ask for one back,
open an [issue](https://github.com/vejeta/wolfi-packages/issues).

## Contributing

New packages and updates are accepted through pull requests:

1. Fork [vejeta/wolfi-packages](https://github.com/vejeta/wolfi-packages).
2. Add `packages/<name>.yaml` (and `packages/<name>/` for patches or extra files).
3. Build it locally with melange.
4. Open a pull request with the checklist below completed.

```
packages/
├── mpv.yaml                  # recipe (flat layout, same as wolfi-dev/os)
├── stremio-qt5.yaml
└── stremio-qt5/              # optional: patches and auxiliary files
    ├── 001-release-makefile-fhs.patch
    └── stremio-wrapper.sh
```

Pull request checklist:

- [ ] The package does not exist in official [wolfi-dev/os](https://github.com/wolfi-dev/os) (`tools/pkg-check` helps)
- [ ] The license is OSI-approved (or explicitly redistributable and documented)
- [ ] The recipe includes a `test:` pipeline
- [ ] It builds locally with melange
- [ ] An `update:` section is configured (release monitor or git tags)

Pull requests are reviewed by [@vejeta](https://github.com/vejeta).
[CONTRIBUTING.md](CONTRIBUTING.md) covers local builds and the review
process.

## Tools

The [`tools/`](tools/) directory has packaging tools for moving packages
between Debian, Alpine and Wolfi. melange recipes are the common format:
Debian and Alpine packaging can be converted into a recipe, and a recipe into
Debian packaging. Each tool is a single Python script with its own README and
unit tests, run in CI by [`tools.yml`](.github/workflows/tools.yml).

| Tool | Purpose |
|------|---------|
| [`pkg-check`](tools/pkg-check/) | Check whether a package already exists in Debian, Alpine or Wolfi, and in which version |
| [`debian-to-melange`](tools/debian-to-melange/) | Convert Debian packaging (`control`, `rules`, `copyright`, patches, maintainer scripts, debconf, autopkgtests) to a melange recipe |
| [`alpine-to-melange`](tools/alpine-to-melange/) | Convert an Alpine `APKBUILD` to a melange recipe (replaces the removed `melange convert apkbuild`) |
| [`melange-to-debian`](tools/melange-to-debian/) | Generate a `debian/` directory from a melange recipe, as a starting point for an ITP |

Typical uses:

```bash
# Is it packaged anywhere already?
python3 tools/pkg-check/pkg-check.py -t all -p foo

# Debian package -> Wolfi recipe, built to verify it
tools/debian-to-melange/debian-to-melange.py --from-debian foo --check-wolfi --build

# Alpine package -> Wolfi recipe
tools/alpine-to-melange/alpine-to-melange.py --from-alpine foo --check-wolfi

# Wolfi recipe -> debian/ for a new Debian package
tools/melange-to-debian/melange-to-debian.py packages/foo.yaml --out ~/src/foo --check-debian
```

Every tool reports what it could not convert on stderr and marks it with a
`TODO(<tool>)` comment in its output. A `melange-to-alpine` converter is
planned.

See also [docs/research-tools.md](docs/research-tools.md) (existing
conversion tools), [docs/design-notes.md](docs/design-notes.md) (recipe and
CI decisions) and [TODO.md](TODO.md).

## Scope

The repository is for packages outside the scope of official Wolfi. The
recipes use the same tools (melange, apko) and conventions as Wolfi. When
official Wolfi starts shipping a package, the recipe here is retired (see
[Retired packages](#retired-packages)).

## Infrastructure

```
GitHub Actions                       SourceForge
  melange build, in waves      --->  signed APKs + APKINDEX
  RSA signing, APKINDEX              https://sourceforge.net/projects/wolfi/
  rsync over SSH
```

- [`build-packages.yml`](.github/workflows/build-packages.yml): builds the changed recipes, or those given in `package_filter`, in dependency order.
- [`sign-and-publish.yml`](.github/workflows/sign-and-publish.yml): signs, indexes and publishes a build run (full or `incremental=true`).
- [`cleanup-old-packages.yml`](.github/workflows/cleanup-old-packages.yml): removes superseded versions.

```bash
# Build one package and publish it incrementally
gh workflow run build-packages.yml -f package_filter="mujs" -R vejeta/wolfi-packages
gh workflow run sign-and-publish.yml -f run_id=<RUN_ID> -f incremental=true -R vejeta/wolfi-packages
```

SourceForge hosts the packages because it has no per-file size limit
(qt5-qtwebengine is about 300 MB) and a mirror network.

## Contact

- Maintainer: Juan Manuel Méndez Rey ([@vejeta](https://github.com/vejeta))
- Issues and package requests: [GitHub Issues](https://github.com/vejeta/wolfi-packages/issues)
- Security reports: open an issue with the `security` label

Co-maintainers are welcome. Maintainers of Wolfi packages that are not in
the official repository can open an issue or a pull request.

## Acknowledgments

- The Wolfi project and Chainguard, for Wolfi, melange and apko.
- SourceForge, for hosting.
- The upstream authors of the packaged projects.

## License

Copyright (C) 2025-2026 Juan Manuel Méndez Rey.

Build recipes, scripts, workflows and tools in this repository are licensed
under the [GNU General Public License v3.0 or later](LICENSE)
(`SPDX-License-Identifier: GPL-3.0-or-later` in each file). [NOTICE](NOTICE)
lists the exceptions (Debian-derived recipes, upstream patches, test
fixtures).

Each built package keeps its upstream license, declared in its recipe.
