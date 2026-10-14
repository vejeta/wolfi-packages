# Wolfi Community Packages

**Community-maintained packages for Wolfi OS**

[![Packages](https://img.shields.io/badge/packages-21-brightgreen)](#available-packages)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/vejeta/wolfi-packages)](https://github.com/vejeta/wolfi-packages/commits)
[![Build Packages](https://github.com/vejeta/wolfi-packages/actions/workflows/build-packages.yml/badge.svg)](https://github.com/vejeta/wolfi-packages/actions)
[![SourceForge](https://img.shields.io/badge/Download-SourceForge-orange)](https://sourceforge.net/projects/wolfi/)

<a href="https://sourceforge.net/projects/wolfi/"><img src="https://sourceforge.net/cdn/syndication/badge_img/3927420/oss-rising-star-white" width="125" alt="SourceForge Rising Star"></a>

---

## What is this?

Wolfi Community Packages is a **community-maintained APK repository** for
[Wolfi OS](https://wolfi.dev). It provides packages that are not part of the
official [wolfi-dev/os](https://github.com/wolfi-dev/os) repository.

- **Independent** — not affiliated with or endorsed by Chainguard.
- **Complementary** — only packages that are *not* available in official Wolfi.
- **Open** — every build recipe is a plain [melange](https://github.com/chainguard-dev/melange) YAML in this repository.
- **Signed** — all APKs are signed with the repository key and indexed in a standard `APKINDEX`.

Build recipes and CI live on GitHub; built packages are distributed through
SourceForge.

## Available packages

| Package | Version | Description | License |
|---------|---------|-------------|---------|
| libass9 | 0.17.5 | Portable library for rendering ASS/SSA subtitles (shared; official Wolfi's libass is static-only) | ISC |
| libbluray | 1.4.0 | Library to access Blu-Ray disks for video playback | LGPL-2.1-or-later |
| libcdio | 2.2.0 | GNU Compact Disc Input and Control Library | GPL-3.0-or-later |
| libcdio-paranoia | 10.2.2.0.2 | CD paranoia library from libcdio | GPL-3.0-or-later AND LGPL-2.1-or-later |
| libdvdnav | 6.1.1 | Library for DVD navigation | GPL-2.0-or-later |
| libdvdread | 6.1.3 | Library for reading DVD video disks | GPL-2.0-or-later |
| libplacebo | 7.351.0 | Reusable library for GPU-accelerated video/image rendering | LGPL-2.1-or-later |
| libxpresent | 1.0.2 | X11 Present extension library | MIT |
| mpv | 0.40.0 | Free, open source, and cross-platform media player | GPL-2.0-or-later AND LGPL-2.1-or-later |
| mujs | 1.3.7 | Lightweight JavaScript interpreter | ISC |
| qt5-qtdeclarative | 5.15.17 | Qt5 - QtDeclarative (QML/QtQuick) components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtquickcontrols | 5.15.17 | Qt5 - QtQuick Controls 1 components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtquickcontrols2 | 5.15.17 | Qt5 - QtQuick Controls 2 components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtwebchannel | 5.15.17 | Qt5 - QtWebChannel (bidirectional client-server communication) | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtwebengine | 5.15.17 | Qt5 - QtWebEngine (Chromium-based web rendering) | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| rubberband | 4.0.0 | Audio time-stretching and pitch-shifting library | GPL-2.0-or-later |
| shaderc | 2025.4 | Tools and libraries for Vulkan shader compilation | Apache-2.0 |
| stremio-qt5 | 4.4.169 | Modern media center for online video content (Stremio shell 4.x, Qt5) | GPL-3.0-or-later |
| stremio-server-installer | 4.21.1 | Downloader for Stremio's streaming server (server.js is fetched at install time, never redistributed) | GPL-3.0-only |
| uchardet | 0.0.8 | Universal charset detection library | MPL-1.1 OR GPL-2.0-or-later OR LGPL-2.1-or-later |
| zimg | 3.0.6 | Scaling, colorspace conversion, and dithering library | WTFPL |

Versions reflect the recipes in [`packages/`](packages/); the YAML file is
always the source of truth. Architectures: **x86_64** and **aarch64** (GitHub Actions ARM runners;
qt5-qtwebengine is x86_64 only due to build time).

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
apk add mpv stremio-qt5
```

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
| stremio | 2025-11 | — | 2026-10 | Renamed to `stremio-qt5`: upstream's current desktop app no longer uses Qt5; the name `stremio` is kept for packaging it later |
| stremio-server | 2025-11 | — | 2026-10 | Replaced by `stremio-server-installer`, converted from the [Debian package](https://tracker.debian.org/pkg/stremio-server-installer) with `debian-to-melange` |
| libvpx | 2025-11 | 2026-09-25 | 2026-10 | Available in official Wolfi (newer version) |
| libxcb | 2025-11 | 2025-08-07 or earlier | 2026-10 | Available in official Wolfi (all xcb libraries in one package) |
| vulkan-loader | 2025-11 | 2025-09-26 or earlier | 2026-10 | Available in official Wolfi (newer version) |
| zlib | 2025-11 | 2025-01-16 or earlier | 2026-10 | Available in official Wolfi (newer version) |
| qt5-qtbase | 2025-11 | 2026-04-01 | 2026-10 | Available in official Wolfi (5.15.19); the Qt5 modules here build against it |

¹ Earliest build of the package in the official Wolfi APKINDEX (x86_64), checked 2026-10-14.

Retired packages are listed in [`packages/RETIRED`](packages/RETIRED); every publish
removes them, and their subpackages, from the repository index.

## Contributing

Contributions of new packages and updates are welcome. The short version:

1. Fork [vejeta/wolfi-packages](https://github.com/vejeta/wolfi-packages).
2. Add `packages/<name>.yaml` (and `packages/<name>/` for patches or extra files).
3. Build it locally with melange.
4. Open a pull request with the checklist below completed.

```
packages/
├── mpv.yaml                  # recipe (flat layout, same as wolfi-dev/os)
├── stremio-qt5.yaml
└── stremio-qt5/                  # optional: patches and auxiliary files
    ├── 001-release-makefile-fhs.patch
    └── stremio-wrapper.sh
```

**Pull request checklist**

- [ ] The package does not exist in official [wolfi-dev/os](https://github.com/wolfi-dev/os) (`tools/pkg-check` helps)
- [ ] The license is OSI-approved (or explicitly redistributable and documented)
- [ ] The recipe includes a `test:` pipeline
- [ ] It builds locally with melange
- [ ] An `update:` section is configured (release monitor or git tags)

Reviews are currently done by the maintainer ([@vejeta](https://github.com/vejeta)).
See [CONTRIBUTING.md](CONTRIBUTING.md) for the full guide, local build
instructions and review process.

## Tools (roadmap)

| Tool | Status | Purpose |
|------|--------|---------|
| [`pkg-check`](tools/pkg-check/) | Initial version | Check whether a package already exists in Debian, Alpine or Wolfi before packaging it |
| [`alpine-to-melange`](tools/alpine-to-melange/) | Initial version | Convert an Alpine `APKBUILD` to a melange recipe (replaces the removed `melange convert apkbuild`) |
| [`debian-to-melange`](tools/debian-to-melange/) | Initial version | Convert Debian packaging (`control`, `rules`, `copyright`, patches, maintainer scripts, debconf) to a melange recipe |
| `melange-to-debian` | Planned | Generate a `debian/` directory from a melange YAML |
| `melange-to-alpine` | Planned | Generate an `APKBUILD` from a melange YAML |

Background research on existing tooling: [docs/research-tools.md](docs/research-tools.md).

## Why this project exists

Some packages do not fit the official Wolfi process — because of scope,
maintenance priorities or review capacity. This repository offers a
community-maintained alternative so that those packages remain available,
buildable and reproducible, using the same tooling (melange, apko) and
conventions as Wolfi itself.

Recipes are developed, reviewed and published only in this repository. When
official Wolfi starts shipping one of these packages, the recipe is retired
here (see [Retired packages](#retired-packages)) and users should switch to
the official one.

## Infrastructure

```
GitHub Actions                      SourceForge
  melange build (per package)  ──►  signed APKs + APKINDEX
  RSA signing, APKINDEX            https://sourceforge.net/projects/wolfi/
  rsync over SSH
```

- [`build-packages.yml`](.github/workflows/build-packages.yml) — builds all or selected packages (`package_filter`, `architectures` inputs) with a shared dependency cache.
- [`sign-and-publish.yml`](.github/workflows/sign-and-publish.yml) — signs, indexes and publishes a build run (full or `incremental=true`).
- [`cleanup-old-packages.yml`](.github/workflows/cleanup-old-packages.yml) — prunes superseded versions.

```bash
# Build one package and publish it incrementally
gh workflow run build-packages.yml -f package_filter="mujs" -R vejeta/wolfi-packages
gh workflow run sign-and-publish.yml -f run_id=<RUN_ID> -f incremental=true -R vejeta/wolfi-packages
```

SourceForge is used for distribution because it has no per-file size limit
(qt5-qtwebengine is ~300 MB) and provides a global mirror network at no cost.

## Contact and maintainers

- Maintainer: Juan Manuel Méndez Rey ([@vejeta](https://github.com/vejeta))
- Issues and package requests: [GitHub Issues](https://github.com/vejeta/wolfi-packages/issues)
- Security reports: open an issue with the `security` label

**Looking for co-maintainers.** If you maintain Wolfi packages that are not in
the official repository and want a shared home for them, open an issue or a
pull request — reviewer and maintainer roles are open.

## Acknowledgments

- The Wolfi project and Chainguard, for Wolfi, melange and apko.
- SourceForge, for hosting and bandwidth.
- The upstream authors of every packaged project.

## License

Copyright (C) 2025-2026 Juan Manuel Méndez Rey.

Build recipes, scripts, workflows and tools in this repository are licensed
under the [GNU General Public License v3.0 or later](LICENSE)
(`SPDX-License-Identifier: GPL-3.0-or-later` in each file). Reuse is welcome
under its terms: keep the copyright and license notices, and share modified
versions under the same license. See [NOTICE](NOTICE) for exceptions
(Debian-derived recipes, upstream patches, test fixtures).

Each built package keeps its upstream license, declared in its recipe.
