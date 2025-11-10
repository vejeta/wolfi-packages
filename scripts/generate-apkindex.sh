#!/bin/bash
# Generate APKINDEX.tar.gz for APK repository
# Usage: ./generate-apkindex.sh <packages-dir> <signing-key>

set -euo pipefail

PACKAGES_DIR="${1:?Packages directory required}"
SIGNING_KEY="${2:?Signing key required}"

# Validate inputs
if [ ! -d "$PACKAGES_DIR" ]; then
    echo "Error: Packages directory not found: $PACKAGES_DIR"
    exit 1
fi

if [ ! -f "$SIGNING_KEY" ]; then
    echo "Error: Signing key not found: $SIGNING_KEY"
    exit 1
fi

echo "=== Generating APKINDEX for APK Repository ==="
echo "Packages directory: $PACKAGES_DIR"
echo "Signing key: $SIGNING_KEY"
echo ""

# Check if apk tools are installed
if ! command -v apk &> /dev/null; then
    echo "Error: apk is not installed"
    echo "Install apk-tools for your distribution"
    exit 1
fi

# Count packages
PACKAGE_COUNT=$(find "$PACKAGES_DIR" -name "*.apk" -type f | wc -l)
echo "Found $PACKAGE_COUNT APK packages"
echo ""

# Generate APKINDEX
cd "$PACKAGES_DIR"

echo "Generating APKINDEX..."
apk index -o APKINDEX.tar.gz *.apk

if [ $? -eq 0 ] && [ -f "APKINDEX.tar.gz" ]; then
    echo "✓ APKINDEX.tar.gz created"
    ls -lh APKINDEX.tar.gz
else
    echo "✗ Failed to create APKINDEX.tar.gz"
    exit 1
fi

# Sign APKINDEX with abuild-sign (if available)
if command -v abuild-sign &> /dev/null; then
    echo ""
    echo "Signing APKINDEX..."
    abuild-sign -k "$SIGNING_KEY" APKINDEX.tar.gz
    echo "✓ APKINDEX signed"
else
    echo ""
    echo "⚠ abuild-sign not found, APKINDEX not signed"
    echo "Install alpine-sdk for signing support"
fi

echo ""
echo "=== APKINDEX generation completed ==="
echo "Repository ready at: $PACKAGES_DIR"
