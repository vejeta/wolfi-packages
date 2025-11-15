#!/bin/bash
# Test script to validate Cirrus CI configuration logic
# Tests the module extraction and QEMU wrapper logic without requiring ARM64

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Testing Cirrus CI configuration logic ==="
echo ""

ERRORS=0

# Test 1: Verify .cirrus.yml syntax
echo "1. Validating .cirrus.yml syntax..."
if command -v yq >/dev/null 2>&1; then
    if yq eval '.' "$REPO_ROOT/.cirrus.yml" >/dev/null 2>&1; then
        echo "   ✓ YAML syntax is valid"
    else
        echo "   ✗ ERROR: Invalid YAML syntax"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "   ⚠ yq not installed, skipping YAML validation"
fi

# Test 2: Verify QEMU_KERNEL_MODULES is used (not manual initramfs combination)
echo ""
echo "2. Checking for QEMU_KERNEL_MODULES usage..."
if grep -q "QEMU_KERNEL_MODULES" "$REPO_ROOT/.cirrus.yml"; then
    echo "   ✓ QEMU_KERNEL_MODULES is used"
    
    # Check that we're extracting modules
    if grep -q "Extract virtio modules\|Extracting virtio modules" "$REPO_ROOT/.cirrus.yml"; then
        echo "   ✓ Module extraction logic present"
    else
        echo "   ✗ ERROR: Module extraction logic not found"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Check that we're NOT combining initramfs manually
    if grep -q "cat.*initramfs.*cpio\|combined-initramfs" "$REPO_ROOT/.cirrus.yml"; then
        echo "   ✗ WARNING: Manual initramfs combination still present (should use QEMU_KERNEL_MODULES instead)"
        ERRORS=$((ERRORS + 1))
    else
        echo "   ✓ No manual initramfs combination (using melange native feature)"
    fi
else
    echo "   ✗ ERROR: QEMU_KERNEL_MODULES not found in .cirrus.yml"
    ERRORS=$((ERRORS + 1))
fi

# Test 3: Verify QEMU wrapper doesn't modify initramfs
echo ""
echo "3. Checking QEMU wrapper logic..."
if grep -q "setup_qemu_wrapper_script" "$REPO_ROOT/.cirrus.yml"; then
    # Extract wrapper script section
    WRAPPER_START=$(grep -n "setup_qemu_wrapper_script" "$REPO_ROOT/.cirrus.yml" | cut -d: -f1)
    WRAPPER_END=$(awk -v start="$WRAPPER_START" 'NR > start && /^      EOF$/ {print NR; exit}' "$REPO_ROOT/.cirrus.yml")
    
    if [ -n "$WRAPPER_START" ] && [ -n "$WRAPPER_END" ]; then
        # Check if wrapper modifies initramfs
        if sed -n "$((WRAPPER_START + 1)),$((WRAPPER_END - 1))p" "$REPO_ROOT/.cirrus.yml" | grep -q "initramfs\|initrd.*combined\|melange_initrd"; then
            echo "   ✗ ERROR: QEMU wrapper still modifies initramfs (should not)"
            ERRORS=$((ERRORS + 1))
        else
            echo "   ✓ QEMU wrapper does not modify initramfs"
        fi
        
        # Check that wrapper handles TCG/KVM replacement
        if sed -n "$((WRAPPER_START + 1)),$((WRAPPER_END - 1))p" "$REPO_ROOT/.cirrus.yml" | grep -q "tcg,thread=multi"; then
            echo "   ✓ QEMU wrapper replaces KVM with TCG"
        else
            echo "   ✗ ERROR: QEMU wrapper doesn't replace KVM with TCG"
            ERRORS=$((ERRORS + 1))
        fi
    fi
else
    echo "   ✗ ERROR: QEMU wrapper script not found"
    ERRORS=$((ERRORS + 1))
fi

# Test 4: Verify module extraction logic
echo ""
echo "4. Checking module extraction logic..."
if grep -q "Extract virtio modules\|Extracting virtio modules" "$REPO_ROOT/.cirrus.yml"; then
    echo "   ✓ Module extraction step present"
    
    # Check for cpio extraction
    if grep -q "cpio.*-idm\|gunzip.*initramfs" "$REPO_ROOT/.cirrus.yml"; then
        echo "   ✓ Uses cpio to extract modules"
    else
        echo "   ⚠ WARNING: Module extraction method unclear"
    fi
    
    # Check that MODULES_DIR is set
    if grep -q "MODULES_DIR\|virtio-modules" "$REPO_ROOT/.cirrus.yml"; then
        echo "   ✓ Modules directory variable present"
    else
        echo "   ✗ ERROR: Modules directory not defined"
        ERRORS=$((ERRORS + 1))
    fi
    
    # Check that QEMU_KERNEL_MODULES is exported
    if grep -q "export QEMU_KERNEL_MODULES" "$REPO_ROOT/.cirrus.yml"; then
        echo "   ✓ QEMU_KERNEL_MODULES is exported"
    else
        echo "   ✗ ERROR: QEMU_KERNEL_MODULES not exported"
        ERRORS=$((ERRORS + 1))
    fi
else
    echo "   ✗ ERROR: Module extraction logic not found"
    ERRORS=$((ERRORS + 1))
fi

# Test 5: Verify build script uses QEMU_KERNEL_MODULES
echo ""
echo "5. Checking build script..."
if grep -A 10 "build_script:" "$REPO_ROOT/.cirrus.yml" | grep -q "QEMU_KERNEL_MODULES"; then
    echo "   ✓ Build script references QEMU_KERNEL_MODULES"
else
    echo "   ✗ ERROR: Build script doesn't use QEMU_KERNEL_MODULES"
    ERRORS=$((ERRORS + 1))
fi

# Test 6: Verify dependencies include required packages
echo ""
echo "6. Checking dependencies..."
REQUIRED_DEPS=("qemu-system-aarch64" "linux-virt" "cpio" "file" "gzip")
MISSING_DEPS=()
for dep in "${REQUIRED_DEPS[@]}"; do
    if ! grep -q "apk add.*$dep" "$REPO_ROOT/.cirrus.yml"; then
        MISSING_DEPS+=("$dep")
    fi
done

if [ ${#MISSING_DEPS[@]} -eq 0 ]; then
    echo "   ✓ All required dependencies present"
else
    echo "   ✗ ERROR: Missing dependencies: ${MISSING_DEPS[*]}"
    ERRORS=$((ERRORS + 1))
fi

# Summary
echo ""
echo "=== Summary ==="
if [ $ERRORS -eq 0 ]; then
    echo "✓ All validation checks passed!"
    echo ""
    echo "The configuration should work correctly in Cirrus CI."
    echo "Key points verified:"
    echo "  - Uses QEMU_KERNEL_MODULES (melange native feature)"
    echo "  - Extracts virtio modules from Alpine initramfs"
    echo "  - QEMU wrapper doesn't modify initramfs"
    echo "  - All required dependencies present"
    exit 0
else
    echo "✗ Found $ERRORS error(s)!"
    echo ""
    echo "Please fix the errors before pushing."
    exit 1
fi
