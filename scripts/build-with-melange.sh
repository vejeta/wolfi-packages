#!/bin/bash
# Build a single package with Melange
# Usage: ./build-with-melange.sh <package-yaml> <architecture> <output-dir>

set -euo pipefail

PACKAGE_YAML="${1:?Package YAML file required}"
ARCH="${2:-x86_64}"
OUTPUT_DIR="${3:-./build-output}"

# Validate inputs
if [ ! -f "$PACKAGE_YAML" ]; then
    echo "Error: Package YAML file not found: $PACKAGE_YAML"
    exit 1
fi

# Create output directory
mkdir -p "$OUTPUT_DIR/$ARCH"

echo "=== Building APK Package with Melange ==="
echo "Package configuration: $PACKAGE_YAML"
echo "Target architecture: $ARCH"
echo "Output directory: $OUTPUT_DIR/$ARCH"
echo ""

# Check if melange is installed
if ! command -v melange &> /dev/null; then
    echo "Error: melange is not installed"
    echo "Install from: https://github.com/chainguard-dev/melange"
    exit 1
fi

# Generate signing key if it doesn't exist
if [ ! -f "melange.rsa" ]; then
    echo "Generating Melange signing key..."
    melange keygen melange.rsa
fi

# Build the package
echo "=== Starting build ==="
melange build "$PACKAGE_YAML" \
    --arch "$ARCH" \
    --out-dir "$OUTPUT_DIR/$ARCH" \
    --workspace-dir ./workspace \
    --signing-key melange.rsa \
    --generate-index false

# Check if build was successful
if [ $? -eq 0 ]; then
    echo ""
    echo "=== Build successful ==="
    echo "Packages created:"
    ls -lh "$OUTPUT_DIR/$ARCH"/*.apk 2>/dev/null || echo "No APK files found"
else
    echo ""
    echo "=== Build failed ==="
    exit 1
fi
