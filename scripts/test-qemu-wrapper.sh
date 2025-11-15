#!/bin/bash
# Test script for QEMU wrapper and initramfs combination logic
# This simulates the Cirrus CI environment locally using Docker

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TEST_DIR="/tmp/test-qemu-wrapper-$$"

echo "=== Testing QEMU wrapper and initramfs combination ==="
echo "Test directory: $TEST_DIR"
mkdir -p "$TEST_DIR"

# Cleanup function
cleanup() {
    echo ""
    echo "=== Cleaning up ==="
    rm -rf "$TEST_DIR"
    docker rm -f test-qemu-wrapper 2>/dev/null || true
}
trap cleanup EXIT

# Extract the QEMU wrapper script from .cirrus.yml
echo ""
echo "=== Extracting QEMU wrapper script from .cirrus.yml ==="
WRAPPER_START=$(grep -n "cat > /usr/bin/qemu-system-aarch64" "$REPO_ROOT/.cirrus.yml" | head -1 | cut -d: -f1)
if [ -n "$WRAPPER_START" ]; then
    # Find the EOF line (it has 6 spaces before it in YAML)
    WRAPPER_END=$(awk -v start="$WRAPPER_START" 'NR > start && /^      EOF$/ {print NR; exit}' "$REPO_ROOT/.cirrus.yml")
    # If not found with spaces, try without
    if [ -z "$WRAPPER_END" ]; then
        WRAPPER_END=$(awk -v start="$WRAPPER_START" 'NR > start && /^EOF$/ {print NR; exit}' "$REPO_ROOT/.cirrus.yml")
    fi
fi

if [ -z "$WRAPPER_START" ] || [ -z "$WRAPPER_END" ]; then
    echo "ERROR: Could not find QEMU wrapper script in .cirrus.yml"
    echo "  WRAPPER_START: $WRAPPER_START"
    echo "  WRAPPER_END: $WRAPPER_END"
    echo "  Checking file..."
    grep -n "qemu-system-aarch64" "$REPO_ROOT/.cirrus.yml" | head -5
    exit 1
fi

# Extract the wrapper script (lines between cat > ... << 'EOF' and EOF)
sed -n "$((WRAPPER_START + 1)),$((WRAPPER_END - 1))p" "$REPO_ROOT/.cirrus.yml" > "$TEST_DIR/qemu-wrapper.sh"

# Extract install_deps_script to check dependencies
echo ""
echo "=== Checking dependencies ==="
DEPS_LINE=$(grep -n "apk add --no-cache" "$REPO_ROOT/.cirrus.yml" | head -1)
if [ -z "$DEPS_LINE" ]; then
    echo "ERROR: Could not find install_deps_script"
    exit 1
fi

DEPS=$(echo "$DEPS_LINE" | sed 's/.*apk add --no-cache //' | tr ' ' '\n')
echo "Required dependencies:"
echo "$DEPS" | while read dep; do
    [ -n "$dep" ] && echo "  - $dep"
done

# Check if 'file' is in dependencies
if echo "$DEPS" | grep -q "^file$"; then
    echo "✓ 'file' package is included in dependencies"
else
    echo "✗ ERROR: 'file' package is MISSING from dependencies!"
    exit 1
fi

# Test in Docker container
echo ""
echo "=== Testing in Alpine container ==="
docker run --rm --name test-qemu-wrapper \
    -v "$TEST_DIR:/test" \
    alpine:latest sh << 'DOCKER_TEST'
set -e

echo "Installing dependencies..."
apk add --no-cache bash qemu-system-aarch64 linux-virt gzip cpio file

echo ""
echo "=== Testing 'file' command ==="
if command -v file >/dev/null 2>&1; then
    echo "✓ 'file' command is available"
    file --version
else
    echo "✗ ERROR: 'file' command not found!"
    exit 1
fi

echo ""
echo "=== Testing initramfs detection ==="
if [ -f /boot/initramfs-virt ]; then
    echo "✓ Alpine initramfs found at /boot/initramfs-virt"
    
    # Test if file command can detect compression
    if file /boot/initramfs-virt | grep -q gzip; then
        echo "  → Initramfs is gzip compressed"
        COMPRESSED=true
    else
        echo "  → Initramfs is uncompressed"
        COMPRESSED=false
    fi
    
    # Test extraction
    if [ "$COMPRESSED" = true ]; then
        echo "  → Testing gunzip extraction..."
        if gunzip -c /boot/initramfs-virt > /tmp/test-extract.cpio 2>&1; then
            echo "  ✓ Extraction successful"
            SIZE=$(stat -c%s /tmp/test-extract.cpio 2>/dev/null || echo "unknown")
            echo "  → Extracted size: $SIZE bytes"
            rm -f /tmp/test-extract.cpio
        else
            echo "  ✗ ERROR: Extraction failed"
            exit 1
        fi
    else
        echo "  → Testing cp copy..."
        if cp /boot/initramfs-virt /tmp/test-copy.cpio 2>&1; then
            echo "  ✓ Copy successful"
            SIZE=$(stat -c%s /tmp/test-copy.cpio 2>/dev/null || echo "unknown")
            echo "  → Copied size: $SIZE bytes"
            rm -f /tmp/test-copy.cpio
        else
            echo "  ✗ ERROR: Copy failed"
            exit 1
        fi
    fi
else
    echo "✗ ERROR: Alpine initramfs not found at /boot/initramfs-virt"
    exit 1
fi

echo ""
echo "=== Testing QEMU wrapper script syntax ==="
# Copy wrapper script into container
cp /test/qemu-wrapper.sh /tmp/qemu-wrapper.sh
chmod +x /tmp/qemu-wrapper.sh

# Test syntax with bash -n
if bash -n /tmp/qemu-wrapper.sh 2>&1; then
    echo "✓ Wrapper script syntax is valid"
else
    echo "✗ ERROR: Wrapper script has syntax errors"
    exit 1
fi

echo ""
echo "=== Testing initramfs combination logic (dry run) ==="
# Create a mock melange initramfs for testing
echo "Creating mock melange initramfs..."
echo "test-file" | cpio -o > /tmp/mock-melange-initramfs.cpio 2>/dev/null || true
gzip -c /tmp/mock-melange-initramfs.cpio > /tmp/mock-melange-initramfs.cpio.gz 2>/dev/null || true

# Test the combination logic
ALPINE_INITRD="/boot/initramfs-virt"
MELANGE_INITRD="/tmp/mock-melange-initramfs.cpio.gz"

echo "Testing combination with:"
echo "  Alpine: $ALPINE_INITRD"
echo "  Melange: $MELANGE_INITRD"

COMBINE_FAILED=false

# Extract Alpine's initramfs
if file "$ALPINE_INITRD" | grep -q gzip; then
    echo "  → Alpine initramfs is gzip compressed"
    if ! gunzip -c "$ALPINE_INITRD" > /tmp/alpine-initramfs.cpio 2>&1; then
        echo "  ✗ ERROR: Failed to extract Alpine initramfs"
        COMBINE_FAILED=true
    fi
else
    echo "  → Alpine initramfs is uncompressed"
    if ! cp "$ALPINE_INITRD" /tmp/alpine-initramfs.cpio 2>&1; then
        echo "  ✗ ERROR: Failed to copy Alpine initramfs"
        COMBINE_FAILED=true
    fi
fi

# Extract melange's initramfs
if [ "$COMBINE_FAILED" = false ]; then
    if file "$MELANGE_INITRD" | grep -q gzip; then
        echo "  → Melange initramfs is gzip compressed"
        if ! gunzip -c "$MELANGE_INITRD" > /tmp/melange-initramfs.cpio 2>&1; then
            echo "  ✗ ERROR: Failed to extract melange initramfs"
            COMBINE_FAILED=true
        fi
    else
        echo "  → Melange initramfs is uncompressed"
        if ! cp "$MELANGE_INITRD" /tmp/melange-initramfs.cpio 2>&1; then
            echo "  ✗ ERROR: Failed to copy melange initramfs"
            COMBINE_FAILED=true
        fi
    fi
fi

# Concatenate and compress
if [ "$COMBINE_FAILED" = false ]; then
    if cat /tmp/alpine-initramfs.cpio /tmp/melange-initramfs.cpio > /tmp/combined-initramfs.cpio 2>&1; then
        if gzip -c /tmp/combined-initramfs.cpio > /tmp/combined-initramfs 2>&1; then
            if [ -f /tmp/combined-initramfs ] && [ -s /tmp/combined-initramfs ]; then
                COMBINED_SIZE=$(stat -c%s /tmp/combined-initramfs 2>/dev/null || echo "unknown")
                ALPINE_SIZE=$(stat -c%s /tmp/alpine-initramfs.cpio 2>/dev/null || echo "unknown")
                MELANGE_SIZE=$(stat -c%s /tmp/melange-initramfs.cpio 2>/dev/null || echo "unknown")
                echo "  ✓ Combined initramfs created successfully:"
                echo "    Alpine cpio: $ALPINE_SIZE bytes"
                echo "    Melange cpio: $MELANGE_SIZE bytes"
                echo "    Combined (gzipped): $COMBINED_SIZE bytes"
                
                # Verify the combined file is valid gzip
                if gzip -t /tmp/combined-initramfs 2>&1; then
                    echo "  ✓ Combined initramfs is valid gzip"
                else
                    echo "  ✗ ERROR: Combined initramfs is NOT valid gzip!"
                    COMBINE_FAILED=true
                fi
            else
                echo "  ✗ ERROR: Combined initramfs file is empty"
                COMBINE_FAILED=true
            fi
        else
            echo "  ✗ ERROR: Failed to compress combined initramfs"
            COMBINE_FAILED=true
        fi
        rm -f /tmp/alpine-initramfs.cpio /tmp/melange-initramfs.cpio /tmp/combined-initramfs.cpio
    else
        echo "  ✗ ERROR: Failed to concatenate cpio files"
        COMBINE_FAILED=true
    fi
fi

if [ "$COMBINE_FAILED" = true ]; then
    echo ""
    echo "✗ ERROR: Initramfs combination failed!"
    exit 1
fi

echo ""
echo "=== All tests passed! ==="
DOCKER_TEST

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ All tests passed successfully!"
    exit 0
else
    echo ""
    echo "✗ Tests failed!"
    exit 1
fi
