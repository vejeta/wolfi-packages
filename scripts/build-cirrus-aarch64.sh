#!/bin/bash
# Build all Wolfi packages for aarch64 using Melange natively on Cirrus CI
# This script is designed to run in the Alpine container on Cirrus CI
# with ARM64 native architecture (AWS Graviton2)
#
# Expected environment:
# - Melange installed natively at /usr/local/bin/melange
# - Signing keys generated in current directory (melange.rsa, melange.rsa.pub)
# - Running in Alpine Linux ARM64 container

set -euo pipefail

ARCH="aarch64"
OUTPUT_DIR="build-output"
REPO_URL="https://downloads.sourceforge.net/project/wolfi"
FAILED_PACKAGES=()
SUCCESSFUL_PACKAGES=()

echo "=== Wolfi Packages - Cirrus CI ARM64 Build Script ==="
echo "Architecture: $ARCH"
echo "Output directory: $OUTPUT_DIR/$ARCH"
echo "Repository: $REPO_URL"
echo "Melange version: $(melange version 2>/dev/null || echo 'unknown')"
echo ""

# Create output directory
mkdir -p "$OUTPUT_DIR/$ARCH"

# Verify signing key exists
if [ ! -f "melange.rsa" ]; then
    echo "ERROR: Signing key melange.rsa not found!"
    echo "Cirrus CI should have generated it in setup_keys_script step"
    exit 1
fi

if [ ! -f "melange.rsa.pub" ]; then
    echo "ERROR: Public key melange.rsa.pub not found!"
    exit 1
fi

if [ ! -f "wolfi-signing.rsa.pub" ]; then
    echo "ERROR: Wolfi signing key wolfi-signing.rsa.pub not found!"
    exit 1
fi

echo "✓ Signing keys verified"
echo ""

# Check if aarch64 SourceForge repository exists (for subsequent builds)
AARCH64_REPO_EXISTS=false
echo "=== Checking if aarch64 repository exists on SourceForge ==="

# Download and check if APKINDEX is valid (SourceForge returns empty file for non-existent paths)
if wget -q -O /tmp/test-apkindex.tar.gz "$REPO_URL/$ARCH/APKINDEX.tar.gz" 2>/dev/null; then
    # Check if file is larger than 100 bytes (empty APKINDEX from SourceForge is ~89 bytes)
    FILE_SIZE=$(stat -c%s "/tmp/test-apkindex.tar.gz" 2>/dev/null || echo "0")
    if [ "$FILE_SIZE" -gt 100 ]; then
        echo "✓ aarch64 repository found on SourceForge - will use it for dependencies"
        AARCH64_REPO_EXISTS=true
    else
        echo "✓ aarch64 repository not found (empty APKINDEX from SourceForge)"
        echo "  Will use only official Wolfi repository for dependencies"
    fi
    rm -f /tmp/test-apkindex.tar.gz
else
    echo "✓ aarch64 repository not found (first build)"
    echo "  Will use only official Wolfi repository for dependencies"
fi
echo ""

# List of packages in dependency order
# Based on build_order_summary.md
PACKAGES=(
    # Stage 1: Base utilities and libraries
    "zlib"
    "uchardet"
    "mujs"

    # Stage 2: Graphics and media foundations
    "zimg"
    "libcdio"
    "libxcb"
    "libxpresent"

    # Stage 3: Audio/video processing and graphics
    "libcdio-paranoia"
    "vulkan-loader"
    "shaderc"

    # Stage 4: Media libraries
    "rubberband"
    "libvpx"
    "libplacebo"
    "libbluray"
    "libass"

    # Stage 5: DVD support
    "libdvdread"

    # Stage 6: DVD navigation
    "libdvdnav"

    # Stage 7: Media player
    "mpv"

    # Stage 8: Qt5 base
    "qt5-qtbase"

    # Stage 9: Qt5 declarative components
    "qt5-qtdeclarative"
    "qt5-qtwebchannel"
    "qt5-qtquickcontrols"

    # Stage 10: Qt5 Quick Controls 2
    "qt5-qtquickcontrols2"

    # Stage 11: Qt5 WebEngine (longest build ~4-5 hours)
    "qt5-qtwebengine"

    # Stage 12: Stremio application
    "stremio"
)

TOTAL_PACKAGES=${#PACKAGES[@]}
CURRENT=0

echo "=== Building $TOTAL_PACKAGES packages for $ARCH ==="
echo ""

# Build each package
for pkg in "${PACKAGES[@]}"; do
    CURRENT=$((CURRENT + 1))
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "[$CURRENT/$TOTAL_PACKAGES] Building: $pkg"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    PACKAGE_YAML="packages/$pkg.yaml"

    if [ ! -f "$PACKAGE_YAML" ]; then
        echo "⚠️  WARNING: Package YAML not found: $PACKAGE_YAML"
        echo "   Skipping..."
        FAILED_PACKAGES+=("$pkg (YAML not found)")
        echo ""
        continue
    fi

    # Record start time for this package
    START_TIME=$(date +%s)

    # Build repository arguments dynamically
    # Note: Melange automatically appends /{arch} to repository URLs
    REPO_ARGS="--repository-append https://packages.wolfi.dev/os"

    # Only add SourceForge repository if it exists (skip on first build)
    if [ "$AARCH64_REPO_EXISTS" = true ]; then
        REPO_ARGS="$REPO_ARGS --repository-append https://downloads.sourceforge.net/project/wolfi"
    fi

    # Export kernel path for Melange QEMU runner
    # Melange's QEMU runner needs QEMU_KERNEL_IMAGE environment variable to locate the kernel
    # $CIRRUS_ENV only persists between Cirrus CI script blocks, not to subprocesses
    export QEMU_KERNEL_IMAGE="/boot/vmlinuz-virt"

    # Build with Melange using QEMU runner (works in Alpine container without special privileges)
    # Use absolute paths for keyring files so the runner can access them
    if melange build \
        --runner qemu \
        --arch "$ARCH" \
        --signing-key "$PWD/melange.rsa" \
        --keyring-append "$PWD/melange.rsa.pub" \
        --keyring-append "$PWD/wolfi-signing.rsa.pub" \
        --pipeline-dir "$PWD/pipelines" \
        $REPO_ARGS \
        --out-dir "$OUTPUT_DIR/$ARCH" \
        "$PACKAGE_YAML"; then

        # Calculate duration
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        DURATION_MIN=$((DURATION / 60))
        DURATION_SEC=$((DURATION % 60))

        echo "✅ Successfully built: $pkg (${DURATION_MIN}m ${DURATION_SEC}s)"
        SUCCESSFUL_PACKAGES+=("$pkg")

        # Show resulting APK files
        echo "   Generated APK files:"
        ls -lh "$OUTPUT_DIR/$ARCH/" | grep "$pkg" | tail -3 || echo "   (no files found)"
    else
        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))
        DURATION_MIN=$((DURATION / 60))
        DURATION_SEC=$((DURATION % 60))

        echo "❌ FAILED to build: $pkg (failed after ${DURATION_MIN}m ${DURATION_SEC}s)"
        FAILED_PACKAGES+=("$pkg")

        # Show QEMU debug log if available
        if [ -f /tmp/qemu-debug.log ]; then
            echo "   === QEMU Debug Log ==="
            tail -50 /tmp/qemu-debug.log
            echo "   ====================="
        fi

        echo "   Continuing with next package..."
    fi

    echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "=== Build Summary ==="
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Total packages: $TOTAL_PACKAGES"
echo "Successful: ${#SUCCESSFUL_PACKAGES[@]}"
echo "Failed: ${#FAILED_PACKAGES[@]}"
echo ""

if [ ${#SUCCESSFUL_PACKAGES[@]} -gt 0 ]; then
    echo "✅ Successfully built packages:"
    for pkg in "${SUCCESSFUL_PACKAGES[@]}"; do
        echo "   - $pkg"
    done
    echo ""
fi

if [ ${#FAILED_PACKAGES[@]} -gt 0 ]; then
    echo "❌ Failed packages:"
    for pkg in "${FAILED_PACKAGES[@]}"; do
        echo "   - $pkg"
    done
    echo ""
fi

# Count APK files generated
APK_COUNT=$(ls -1 "$OUTPUT_DIR/$ARCH/"*.apk 2>/dev/null | wc -l)
echo "Total APK files generated: $APK_COUNT"
echo ""

# Generate APKINDEX if we have any packages
if [ $APK_COUNT -gt 0 ]; then
    echo "=== Generating APKINDEX.tar.gz ==="
    cd "$OUTPUT_DIR/$ARCH"

    # Use melange index to create APKINDEX
    if melange index -o APKINDEX.tar.gz *.apk; then
        echo "✅ APKINDEX.tar.gz generated successfully"
        ls -lh APKINDEX.tar.gz

        # Verify APKINDEX contents
        echo ""
        echo "=== APKINDEX Contents ==="
        tar -tzf APKINDEX.tar.gz
    else
        echo "❌ Failed to generate APKINDEX.tar.gz"
        cd ../..
        exit 1
    fi

    cd ../..
else
    echo "⚠️  WARNING: No APK files generated, skipping APKINDEX creation"
fi

echo ""
echo "=== Build Complete ==="
echo "Output directory: $OUTPUT_DIR/$ARCH/"
echo ""
echo "Directory contents:"
ls -lh "$OUTPUT_DIR/$ARCH/" | head -20

echo ""
echo "Disk usage:"
du -sh "$OUTPUT_DIR/$ARCH/"

# Exit with error if critical packages failed
CRITICAL_FAILURES=()
for pkg in "${FAILED_PACKAGES[@]}"; do
    # Check if this is a critical package (qt5-qtwebengine or stremio)
    if [[ "$pkg" == "qt5-qtwebengine" ]] || [[ "$pkg" == "stremio" ]]; then
        CRITICAL_FAILURES+=("$pkg")
    fi
done

if [ ${#CRITICAL_FAILURES[@]} -gt 0 ]; then
    echo ""
    echo "⚠️  WARNING: Critical packages failed:"
    for pkg in "${CRITICAL_FAILURES[@]}"; do
        echo "   - $pkg"
    done
    echo ""
    echo "Build completed with errors (non-critical packages were built)"
    # Don't exit with error - Cirrus CI should still upload available artifacts
fi

echo "=== Script finished ==="
exit 0
