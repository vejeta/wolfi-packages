# Wolfi APK Repository - Stremio and Media Packages

[![Build Packages](https://github.com/vejeta/wolfi-packages/actions/workflows/build-packages.yml/badge.svg)](https://github.com/vejeta/wolfi-packages/actions)
[![SourceForge](https://img.shields.io/badge/Download-SourceForge-orange)](https://sourceforge.net/projects/wolfi/)

Community APK repository for [Wolfi Linux](https://wolfi.dev) providing **Stremio**, **MPV**, and comprehensive media libraries including Qt5 WebEngine.

**Hosted on SourceForge** • **Automated CI/CD** • **Cryptographically signed** • **Multi-architecture support**

> **Important**: This is a community repository providing early access to packages from [PR #69098](https://github.com/wolfi-dev/os/pull/69098) which is currently under review by the official Wolfi team.
>
> **If/when the PR is merged into wolfi-dev/os**, this repository may become unnecessary, and users should migrate to the official Wolfi packages. Until then, this repository serves as:
> - Early access for users who need these packages immediately
> - Testing ground for the package configurations before official inclusion
> - Learning resource for Wolfi packaging and CI/CD

---

## Quick Installation

### Add Repository

```bash
# Download repository signing key
wget -O /etc/apk/keys/vejeta-wolfi.rsa.pub \
  https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub

# Add repository to apk
echo "https://downloads.sourceforge.net/project/wolfi/repo/$(uname -m)" >> /etc/apk/repositories

# Update package index
apk update

# Install packages
apk add stremio mpv qt5-qtwebengine
```

### Manual Download

Download APK files directly from [SourceForge](https://sourceforge.net/projects/wolfi/files/repo/)

---

## Available Packages

### Media Players
- **stremio** (4.4.169) - Modern media center application
- **mpv** - Powerful media player

### Qt5 Libraries
- **qt5-qtbase** - Qt5 core libraries
- **qt5-qtdeclarative** - QML and Qt Quick
- **qt5-qtwebengine** - Chromium-based web engine (~300MB)
- **qt5-qtwebchannel** - WebChannel support
- **qt5-qtquickcontrols** - Qt Quick Controls
- **qt5-qtquickcontrols2** - Qt Quick Controls 2

### Media Libraries
- **libass** - Subtitle rendering
- **libbluray** - Blu-ray disc support
- **libcdio** / **libcdio-paranoia** - CD-ROM access
- **libdvdnav** / **libdvdread** - DVD navigation and reading
- **libplacebo** - GPU-accelerated video processing
- **libvpx** - VP8/VP9 video codec
- **rubberband** - Audio time-stretching

### Graphics & Rendering
- **shaderc** - Shader compiler
- **vulkan-loader** - Vulkan graphics API
- **libxcb** - X11 C bindings
- **libxpresent** - X11 Present extension

### Utilities
- **mujs** - JavaScript interpreter
- **uchardet** - Character encoding detection
- **zimg** - Image scaling library
- **zlib** - Compression library

**Total**: 25 packages across media, Qt5, graphics, and utilities

---

## Architecture

```
GitHub Actions (CI/CD)
    ↓ Melange build for x86_64 + aarch64
    ↓ RSA signing
    ↓ APKINDEX generation
    ↓ rsync over SSH
SourceForge (Distribution)
    └── Public APK repository
```

### Supported Architectures
- **x86_64** - Intel/AMD 64-bit
- **aarch64** - ARM 64-bit (Raspberry Pi, servers, etc.)

---

## Security

All packages are:
- Cryptographically signed with RSA keys
- Built from source using Melange
- Reproducible builds via GitHub Actions
- Open source - all build configurations public

### Verify Signatures

```bash
# Package signatures are verified automatically by apk
apk verify stremio mpv qt5-qtwebengine
```

---

## Build Status

| Package | Status | Size | Architectures |
|---------|--------|------|---------------|
| stremio | Passing | ~50MB | x86_64, aarch64 |
| mpv | Passing | ~20MB | x86_64, aarch64 |
| qt5-qtwebengine | Passing | ~300MB | x86_64, aarch64 |
| Other libraries | Passing | Varies | x86_64, aarch64 |

---

## For Developers

### Building with GitHub Actions (Recommended)

This repository uses **GitHub Actions Cache** for fast, independent builds:

- **Cache Duration**: 7 days
- **Cache Size**: ~50 packages (~7 MB compressed)
- **Benefit**: Build individual packages without rebuilding dependencies

#### Quick Start

```bash
# Check if cache is populated (< 7 days old)
gh cache list -R vejeta/wolfi-packages --key wolfi-packages-consolidated-x86_64

# If cache exists: Build any package independently
gh workflow run build-packages.yml -f package_filter="stremio" -R vejeta/wolfi-packages

# If cache empty: Follow sequential build order
# See build_order_summary.md for detailed instructions
```

**With populated cache:**
- Build time: ~7-92 minutes (individual packages)
- No dependency rebuilds required
- Example: Update only `stremio` without rebuilding Qt5 stack

**With empty cache (>7 days):**
- Build time: ~2.5-4.5 hours (full sequential build)
- Must follow dependency order (see `build_order_summary.md`)
- SourceForge acts as fallback dependency source

### Building Locally

```bash
# Clone repository
git clone https://github.com/vejeta/wolfi-packages.git
cd wolfi-packages

# Install Melange
wget https://github.com/chainguard-dev/melange/releases/download/v0.8.0/melange_0.8.0_linux_amd64.tar.gz
tar -xzf melange_0.8.0_linux_amd64.tar.gz
sudo mv melange /usr/local/bin/

# Build a specific package
./scripts/build-with-melange.sh packages/stremio/stremio.yaml x86_64
```

### Project Origin

These packages originated from [PR #69098](https://github.com/wolfi-dev/os/pull/69098) submitted to the official Wolfi repository. As the PR review process continues, this community repository provides early access to these packages for users who need them immediately.

### Contributing

1. **Package Issues**: Report at [GitHub Issues](https://github.com/vejeta/wolfi-packages/issues)
2. **Build Problems**: Check [GitHub Actions logs](https://github.com/vejeta/wolfi-packages/actions)
3. **Security Concerns**: Please report responsibly via GitHub Issues

---

## Background

This repository was created because:
- Chainguard has not yet merged [PR #69098](https://github.com/wolfi-dev/os/pull/69098)
- Users need these packages now for Stremio and MPV
- Learning opportunity for Wolfi CI/CD and package distribution

### Why SourceForge?

GitHub Pages has a **100 MB file size limit**, making it unsuitable for large packages like qt5-qtwebengine (300MB). SourceForge provides:
- No file size limits
- Unlimited bandwidth
- Reliable rsync/SSH access
- CDN for fast downloads
- Free for open source projects

---

## Support

- **Installation Issues**: Check installation instructions above
- **Build Failures**: See [GitHub Actions](https://github.com/vejeta/wolfi-packages/actions)
- **Package Requests**: Open an [issue](https://github.com/vejeta/wolfi-packages/issues)
- **Upstream Wolfi**: https://wolfi.dev

---

## Statistics

- **Packages**: 25
- **Architectures**: x86_64, aarch64
- **Total Repository Size**: ~800 MB per architecture
- **Hosting Cost**: $0/month (SourceForge)
- **Build Time**: ~30-45 minutes per full build

---

## Acknowledgments

- **Wolfi Team**: For creating an excellent security-focused Linux distribution
- **Chainguard**: For Melange build tooling
- **SourceForge**: For free hosting and bandwidth
- **Stremio**: For creating a great media center application

---

## License

Build configurations and scripts: MIT License

Individual packages retain their respective upstream licenses (see each package's .yaml file).

---

**Maintained by**: Juan Manuel Méndez Rey (vejeta)

**Last updated**: 2025-11-10
