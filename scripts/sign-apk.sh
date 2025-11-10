#!/bin/bash
# Sign an APK package with RSA key
# Usage: ./sign-apk.sh <apk-file> <signing-key>

set -euo pipefail

APK_FILE="${1:?APK file required}"
SIGNING_KEY="${2:?Signing key required}"

# Validate inputs
if [ ! -f "$APK_FILE" ]; then
    echo "Error: APK file not found: $APK_FILE"
    exit 1
fi

if [ ! -f "$SIGNING_KEY" ]; then
    echo "Error: Signing key not found: $SIGNING_KEY"
    exit 1
fi

echo "=== Signing APK Package ==="
echo "APK file: $APK_FILE"
echo "Signing key: $SIGNING_KEY"
echo ""

# Check if openssl is installed
if ! command -v openssl &> /dev/null; then
    echo "Error: openssl is not installed"
    exit 1
fi

# Create signature
SIGNATURE_FILE="${APK_FILE}.SIGN.RSA.${SIGNING_KEY##*/}"
SIGNATURE_FILE="${SIGNATURE_FILE%.rsa}.rsa"

echo "Creating signature..."
openssl dgst -sha256 -sign "$SIGNING_KEY" -out "$SIGNATURE_FILE" "$APK_FILE"

if [ $? -eq 0 ] && [ -f "$SIGNATURE_FILE" ]; then
    echo "✓ Signature created: $SIGNATURE_FILE"
    ls -lh "$SIGNATURE_FILE"
else
    echo "✗ Failed to create signature"
    exit 1
fi

# Verify signature (optional)
echo ""
echo "Verifying signature..."
PUBLIC_KEY="${SIGNING_KEY}.pub"

if [ -f "$PUBLIC_KEY" ]; then
    openssl dgst -sha256 -verify "$PUBLIC_KEY" -signature "$SIGNATURE_FILE" "$APK_FILE" && \
        echo "✓ Signature verified successfully" || \
        echo "✗ Signature verification failed"
else
    echo "⚠ Public key not found, skipping verification"
fi

echo ""
echo "=== Signing completed ==="
