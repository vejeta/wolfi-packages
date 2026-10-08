# Wolfi Community Packages

**Community-maintained packages for Wolfi OS**

[![Packages](https://img.shields.io/badge/packages-24-brightgreen)](#available-packages)
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
| libbluray | 1.4.0 | Library to access Blu-Ray disks for video playback | LGPL-2.1-or-later |
| libcdio | 2.2.0 | GNU Compact Disc Input and Control Library | GPL-3.0-or-later |
| libcdio-paranoia | 10.2.2.0.2 | CD paranoia library from libcdio | GPL-3.0-or-later AND LGPL-2.1-or-later |
| libdvdnav | 6.1.1 | Library for DVD navigation | GPL-2.0-or-later |
| libdvdread | 6.1.3 | Library for reading DVD video disks | GPL-2.0-or-later |
| libplacebo | 7.351.0 | Reusable library for GPU-accelerated video/image rendering | LGPL-2.1-or-later |
| libvpx | 1.15.2 | Library for the VP8/VP9 codecs | BSD-3-Clause |
| libxcb | 1.17.0 | X11 client-side library | MIT |
| libxpresent | 1.0.2 | X11 Present extension library | MIT |
| mpv | 0.40.0 | Free, open source, and cross-platform media player | GPL-2.0-or-later AND LGPL-2.1-or-later |
| mujs | 1.3.7 | Lightweight JavaScript interpreter | ISC |
| qt5-qtbase | 5.15.17 | Qt5 - QtBase components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtdeclarative | 5.15.17 | Qt5 - QtDeclarative (QML/QtQuick) components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtquickcontrols | 5.15.17 | Qt5 - QtQuick Controls 1 components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtquickcontrols2 | 5.15.17 | Qt5 - QtQuick Controls 2 components | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtwebchannel | 5.15.17 | Qt5 - QtWebChannel (bidirectional client-server communication) | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| qt5-qtwebengine | 5.15.17 | Qt5 - QtWebEngine (Chromium-based web rendering) | LGPL-3.0-only OR GPL-3.0-only WITH Qt-GPL-exception-1.0 |
| rubberband | 4.0.0 | Audio time-stretching and pitch-shifting library | GPL-2.0-or-later |
| shaderc | 2025.4 | Tools and libraries for Vulkan shader compilation | Apache-2.0 |
| stremio | 4.4.169 | Modern media center for online video content | GPL-3.0-or-later |
| uchardet | 0.0.8 | Universal charset detection library | MPL-1.1 OR GPL-2.0-or-later OR LGPL-2.1-or-later |
| vulkan-loader | 1.4.330 | Vulkan Installable Client Driver (ICD) Loader | Apache-2.0 |
| zimg | 3.0.6 | Scaling, colorspace conversion, and dithering library | WTFPL |
| zlib | 1.3.1 | Library implementing the zlib compression algorithms | MPL-2.0 AND MIT |

Versions reflect the recipes in [`packages/`](packages/); the YAML file is
always the source of truth. Architectures: **x86_64** and **aarch64** (GitHub Actions ARM runners;
qt5-qtwebengine is x86_64 only due to build time).

## Using these packages

Repository base URL and signing key:

```
Repository: https://downloads.sourceforge.net/project/wolfi
Key:        https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub/download
Browse:     https://sourceforge.net/projects/wolfi/files/
```

`apk`, melange and apko append the architecture (`x86_64/`, `aarch64/`) to the
base URL automatically.

### On a running Wolfi system

```bash
wget -O /etc/apk/keys/vejeta-wolfi.rsa.pub \
  https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub/download
echo "https://downloads.sourceforge.net/project/wolfi" >> /etc/apk/repositories
apk update
apk add mpv stremio
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
      - https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub/download
    repositories:
      - https://packages.wolfi.dev/os
      - https://downloads.sourceforge.net/project/wolfi
    packages:
      - build-base
      - mpv-dev
      - libass-dev

pipeline:
  # ...
```

### In an apko image

```yaml
contents:
  keyring:
    - https://packages.wolfi.dev/os/wolfi-signing.rsa.pub
    - https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub/download
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
      https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub/download \
 && echo "https://downloads.sourceforge.net/project/wolfi" >> /etc/apk/repositories \
 && apk add --no-cache mpv
```

## Retired packages

Packages are retired when an official or better-suited alternative exists.

| Package | Retired | Reason / replacement |
|---------|---------|----------------------|
| libass | 2026-10 | Available in official Wolfi (`apk add libass`) |
| stremio-server | 2026-10 | To be replaced by `stremio-server-installer`, generated from the Debian package with `debian-to-melange` |

Already-published APKs of retired packages remain on SourceForge until the
next repository cleanup.

## Contributing

Contributions of new packages and updates are welcome. The short version:

1. Fork [vejeta/wolfi-packages](https://github.com/vejeta/wolfi-packages).
2. Add `packages/<name>.yaml` (and `packages/<name>/` for patches or extra files).
3. Build it locally with melange.
4. Open a pull request with the checklist below completed.

```
packages/
├── mpv.yaml                  # recipe (flat layout, same as wolfi-dev/os)
├── stremio.yaml
└── stremio/                  # optional: patches and auxiliary files
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
| `alpine-to-melange` | Planned | Convert an `APKBUILD` to a melange YAML (building on `melange convert apkbuild` where possible) |
| `debian-to-melange` | Planned (first case: `stremio-server-installer`) | Convert `debian/control` + `debian/rules` + `debian/patches` to melange YAML |
| `melange-to-debian` | Planned | Generate a `debian/` directory from a melange YAML |
| `melange-to-alpine` | Planned | Generate an `APKBUILD` from a melange YAML |

Background research on existing tooling: [docs/research-tools.md](docs/research-tools.md).

## Why this project exists

Some packages do not fit the official Wolfi process — because of scope,
maintenance priorities or review capacity. This repository offers a
community-maintained alternative so that those packages remain available,
buildable and reproducible, using the same tooling (melange, apko) and
conventions as Wolfi itself.

When a package is accepted into official Wolfi, it is removed from here and
users should switch to the official one.

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

Build recipes, scripts and tools in this repository: MIT.
Each package retains its upstream license, declared in its YAML recipe.
