#!/bin/bash
# Build a single package with Melange using official container
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

echo "=== Building APK Package with Melange Container ==="
echo "Package configuration: $PACKAGE_YAML"
echo "Target architecture: $ARCH"
echo "Output directory: $OUTPUT_DIR/$ARCH"
echo ""

# Map architecture to Docker platform
case "$ARCH" in
    x86_64)
        DOCKER_PLATFORM="linux/amd64"
        ;;
    aarch64)
        DOCKER_PLATFORM="linux/arm64"
        ;;
    *)
        echo "Error: Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

# Generate signing key if it doesn't exist
if [ ! -f "melange.rsa" ]; then
    echo "Generating Melange signing key using container..."
    docker run --rm \
        -v $PWD:/work \
        -w /work \
        cgr.dev/chainguard/melange:latest \
        keygen melange.rsa

    chmod 600 melange.rsa
    chmod 644 melange.rsa.pub
fi

# Build the package using Melange container
echo "=== Starting build with Melange container ==="
docker run --rm --privileged \
    --platform "$DOCKER_PLATFORM" \
    -v $PWD:/work \
    -w /work \
    cgr.dev/chainguard/melange:latest \
    build \
    --arch "$ARCH" \
    --signing-key melange.rsa \
    --keyring-append /work/melange.rsa.pub \
    --repository-append https://packages.wolfi.dev/os \
    --out-dir "$OUTPUT_DIR/$ARCH" \
    "$PACKAGE_YAML"

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
