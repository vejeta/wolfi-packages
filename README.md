# Wolfi APK Repository - Stremio and Media Packages

[![Build Packages](https://github.com/vejeta/wolfi-packages/actions/workflows/build-packages.yml/badge.svg)](https://github.com/vejeta/wolfi-packages/actions)
[![Packages](https://img.shields.io/badge/packages-25-brightgreen)](https://sourceforge.net/projects/wolfi/)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Architecture](https://img.shields.io/badge/architecture-x86__64-orange)](https://sourceforge.net/projects/wolfi/)
[![SourceForge](https://img.shields.io/badge/Download-SourceForge-orange)](https://sourceforge.net/projects/wolfi/)

Community APK repository for [Wolfi Linux](https://wolfi.dev) providing **Stremio**, **MPV**, and comprehensive media libraries including Qt5 WebEngine.

**Hosted on SourceForge** • **Automated CI/CD** • **Cryptographically signed** • **Multi-architecture support**

## Technical Overview

**Advanced Melange packaging** for complex multimedia dependencies including Qt5 WebEngine compilation with GCC 15 compatibility fixes. This repository demonstrates:

- Complex dependency resolution (25 interdependent packages)
- Cross-compilation for multiple architectures 
- Automated CI/CD with cryptographic signing
- Production-ready APK distribution infrastructure

Built as part of [PR #69098](https://github.com/wolfi-dev/os/pull/69098) to the official Wolfi repository.

> **Important**: This is a community repository providing early access to packages from [PR #69098](https://github.com/wolfi-dev/os/pull/69098) which is currently under review by the official Wolfi team.
>
> **If/when the PR is merged into wolfi-dev/os**, this repository may become unnecessary, and users should migrate to the official Wolfi packages. Until then, this repository serves as:
> - Early access for users who need these packages immediately
> - Testing ground for the package configurations before official inclusion
> - Demonstration of advanced Wolfi packaging techniques

---

## Key Technical Achievements

- **Qt5 WebEngine compilation**: Successfully resolved GCC 15 C++20 compatibility issues in Chromium codebase
- **Multi-stage dependency building**: Orchestrated build order for 25+ interdependent packages  
- **Production packaging**: Native builds for x86_64 architecture with optimized compilation
- **Production CI/CD pipeline**: Automated build, sign, and deploy workflow with GitHub Actions
- **Zero-cost infrastructure**: Optimized hosting strategy using SourceForge + GitHub Actions
- **Complex problem solving**: ICU compatibility, dependency chains, 4+ hour compilation management

---

## Quick Installation

### Add Repository

```bash
# Download and install repository signing key
wget -O /etc/apk/keys/vejeta-wolfi.rsa.pub \
  https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub/download

# Add repository to apk (x86_64 only)
echo "https://downloads.sourceforge.net/project/wolfi/x86_64" >> /etc/apk/repositories

# Update package index
apk update

# Install packages
apk add stremio mpv qt5-qtwebengine
```

### Manual Download

Download APK files directly from [SourceForge](https://sourceforge.net/projects/wolfi/files/)

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

## Architecture & Infrastructure

```
GitHub Actions (CI/CD)
    ↓ Melange build for x86_64
    ↓ RSA signing with generated keys
    ↓ APKINDEX generation and verification
    ↓ Automated rsync deployment over SSH
SourceForge (Distribution)
    └── Production APK repository with CDN
```

### Supported Architectures
- **x86_64** - Intel/AMD 64-bit (primary support)

> **Note**: Currently only x86_64 packages are available. Qt5 WebEngine compilation on aarch64 
> requires 6+ hours, making it impractical for the current CI/CD setup. Future optimizations 
> may include cross-compilation or dedicated ARM build infrastructure.

### Security Features

All packages are:
- **Cryptographically signed** with RSA keys
- **Built from source** using Melange reproducible builds
- **Automated verification** via GitHub Actions
- **Open source** - all build configurations publicly auditable

```bash
# Package signatures are verified automatically by apk
apk verify stremio mpv qt5-qtwebengine
```

---

## Build Status & Performance

| Package | Status | Size | Build Time | Architecture |
|---------|--------|------|------------|--------------|
| stremio | Passing | ~50MB | ~5 min | x86_64 |
| mpv | Passing | ~20MB | ~7 min | x86_64 |
| qt5-qtwebengine | Passing | ~300MB | ~4+ hours | x86_64 |
| qt5-qtbase | Passing | ~25MB | ~15 min | x86_64 |
| Other libraries | Passing | Varies | 2-10 min | x86_64 |

---

## For Developers

### CI/CD Workflows

This repository features a sophisticated two-stage CI/CD pipeline:

#### 1. Build Workflow (`build-packages.yml`)

Compiles APK packages using Melange with dependency caching:

```bash
# Build all packages (full rebuild)
gh workflow run build-packages.yml -R vejeta/wolfi-packages

# Build specific packages (incremental)
gh workflow run build-packages.yml \
  -f package_filter="mujs,stremio" \
  -R vejeta/wolfi-packages

# Build for specific architecture (default: x86_64)
gh workflow run build-packages.yml \
  -f architectures="x86_64,aarch64" \
  -R vejeta/wolfi-packages
```

**Features:**
- Package-level dependency caching (7-day retention)
- Configurable architecture targets (x86_64, aarch64, or both)
- Selective package filtering for faster incremental builds
- Automatic artifact generation for downstream publishing

#### 2. Sign & Publish Workflow (`sign-and-publish.yml`)

Cryptographically signs packages and publishes to SourceForge:

```bash
# Full repository publish (replaces all packages)
gh workflow run sign-and-publish.yml \
  -f run_id=19294275595 \
  -R vejeta/wolfi-packages

# Incremental publish (merges with existing repository)
gh workflow run sign-and-publish.yml \
  -f run_id=19294275595 \
  -f incremental=true \
  -R vejeta/wolfi-packages
```

**Full vs Incremental Publishing:**

| Mode | Behavior | Use Case | Time |
|------|----------|----------|------|
| **Full** (default) | Replaces entire repository | Initial publish, major updates | ~15 min |
| **Incremental** | Merges with existing packages | Hotfixes, single package updates | ~25 min |

**Incremental Mode Benefits:**
- Avoids rebuilding unchanged packages (saves 4+ hours for qt5-qtwebengine)
- Downloads existing packages from SourceForge (~10 min for ~1-2GB)
- Merges new packages with existing ones (newer versions replace older)
- Regenerates APKINDEX with complete package list
- Perfect for updating 1-2 packages without full rebuild

**Example Workflow - Quick Package Update:**
```bash
# 1. Build only the updated package (e.g., mujs)
gh workflow run build-packages.yml -f package_filter="mujs"
# Wait ~2 minutes for build completion

# 2. Get the build run ID
BUILD_RUN_ID=$(gh run list --workflow=build-packages.yml --limit=1 --json databaseId --jq '.[0].databaseId')

# 3. Publish incrementally (merges with existing repository)
gh workflow run sign-and-publish.yml -f run_id=$BUILD_RUN_ID -f incremental=true

# Total time: ~17 minutes vs 4+ hours for full rebuild
```

### Building with GitHub Actions (Recommended)

This repository uses **GitHub Actions Cache** for efficient, independent builds:

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
# See build_order_summary.md for detailed dependency instructions
```

**Performance with populated cache:**
- Build time: 7-92 minutes (individual packages)
- No dependency rebuilds required
- Example: Update only `stremio` without rebuilding entire Qt5 stack

**Performance with empty cache (>7 days):**
- Build time: 2.5-4.5 hours (full sequential build)
- Must follow strict dependency order
- SourceForge repository acts as fallback dependency source

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

---

## Project Metrics

- **Development time**: 3 weeks of intensive packaging work
- **Lines of configuration**: 2000+ YAML/shell scripts  
- **Build complexity**: 25 packages, 17 core dependencies
- **Repository size**: ~800MB (x86_64 architecture)
- **Largest package**: qt5-qtwebengine (300MB) - Full Chromium web engine
- **Build infrastructure cost**: $0/month (optimized GitHub Actions + SourceForge)
- **Package compatibility**: GCC 15, modern Wolfi base system
- **Technical challenges solved**: ICU version conflicts, C++20 compatibility, 4+ hour compilation times
- **Build constraints**: Qt5 WebEngine aarch64 compilation exceeds 6-hour CI limits

---

## Background & Motivation

This repository was created to address several needs:

- **Immediate availability**: Chainguard has not yet merged [PR #69098](https://github.com/wolfi-dev/os/pull/69098)
- **User demand**: Community needs these multimedia packages for production use
- **Technical showcase**: Demonstrates advanced Wolfi packaging and CI/CD capabilities
- **Learning platform**: Open source example of complex dependency management

### Why SourceForge for Distribution?

GitHub Pages has a **100 MB file size limit**, making it unsuitable for large packages like qt5-qtwebengine (300MB). SourceForge provides:

- **No file size limits** for large binary packages
- **Unlimited bandwidth** with global CDN
- **Reliable rsync/SSH access** for automated deployment
- **Production-grade hosting** for open source projects
- **Zero hosting costs** with professional infrastructure

---

## Contributing & Support

### Issue Reporting
1. **Package Issues**: Report at [GitHub Issues](https://github.com/vejeta/wolfi-packages/issues)
2. **Build Problems**: Check [GitHub Actions logs](https://github.com/vejeta/wolfi-packages/actions)
3. **Security Concerns**: Report responsibly via GitHub Issues with "security" label

### Getting Help
- **Installation Issues**: Review installation instructions and verify signing key
- **Build Failures**: Examine [GitHub Actions](https://github.com/vejeta/wolfi-packages/actions) for detailed logs
- **Package Requests**: Open an [issue](https://github.com/vejeta/wolfi-packages/issues) with technical requirements
- **Upstream Wolfi**: Visit https://wolfi.dev for official documentation

---

## Acknowledgments

- **Wolfi Team & Chainguard**: For creating an excellent security-focused Linux distribution and Melange tooling
- **SourceForge**: For providing free, reliable hosting and bandwidth for open source projects
- **Stremio**: For developing an outstanding cross-platform media center application
- **Open Source Community**: For the foundational libraries that make this multimedia stack possible

---

## License

**Build configurations and automation scripts**: MIT License

**Individual packages**: Retain their respective upstream licenses (see each package's .yaml configuration file for details)

---

**Maintained by**: Juan Manuel Méndez Rey ([vejeta](https://github.com/vejeta))

**Last updated**: 2025-11-11

**Repository**: https://github.com/vejeta/wolfi-packages

**Distribution**: https://sourceforge.net/projects/wolfi/
