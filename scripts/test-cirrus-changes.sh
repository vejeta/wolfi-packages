#!/bin/bash
# Quick validation script for Cirrus CI changes
# This runs faster than the full Docker test and checks critical issues

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Quick validation of Cirrus CI changes ==="
echo ""

ERRORS=0

# Check 1: Verify 'file' package is in dependencies
echo "1. Checking dependencies..."
if grep -q "apk add --no-cache.*file" "$REPO_ROOT/.cirrus.yml"; then
    echo "   ✓ 'file' package is included"
else
    echo "   ✗ ERROR: 'file' package is MISSING from dependencies!"
    ERRORS=$((ERRORS + 1))
fi

# Check 2: Verify initramfs combination order (Alpine first, then melange)
echo ""
echo "2. Checking initramfs combination order..."
if grep -q "cat /tmp/alpine-initramfs.cpio /tmp/melange-initramfs.cpio" "$REPO_ROOT/.cirrus.yml"; then
    echo "   ✓ Correct order: Alpine first, then melange"
else
    echo "   ✗ WARNING: Initramfs order may be incorrect"
    echo "   Expected: cat /tmp/alpine-initramfs.cpio /tmp/melange-initramfs.cpio"
fi

# Check 3: Verify file command is used for compression detection
echo ""
echo "3. Checking compression detection..."
if grep -q "file.*initramfs.*grep.*gzip" "$REPO_ROOT/.cirrus.yml"; then
    echo "   ✓ Using 'file' command for compression detection"
else
    echo "   ✗ WARNING: Compression detection may not be using 'file' command"
fi

# Check 4: Verify error handling (COMBINE_FAILED flag)
echo ""
echo "4. Checking error handling..."
if grep -q "COMBINE_FAILED" "$REPO_ROOT/.cirrus.yml"; then
    echo "   ✓ Error handling with COMBINE_FAILED flag present"
else
    echo "   ✗ WARNING: Error handling may be missing"
fi

# Check 5: Verify cleanup of temporary files
echo ""
echo "5. Checking cleanup..."
if grep -q "rm -f.*alpine-initramfs.cpio.*melange-initramfs.cpio" "$REPO_ROOT/.cirrus.yml"; then
    echo "   ✓ Cleanup of temporary files present"
else
    echo "   ✗ WARNING: Cleanup may be missing"
fi

# Summary
echo ""
if [ $ERRORS -eq 0 ]; then
    echo "✓ All critical checks passed!"
    echo ""
    echo "Note: For full testing with Docker, run:"
    echo "  ./scripts/test-qemu-wrapper.sh"
    exit 0
else
    echo "✗ Found $ERRORS critical error(s)!"
    echo ""
    echo "Please fix the errors before committing."
    exit 1
fi
