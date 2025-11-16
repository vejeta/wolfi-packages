#!/bin/bash
# Sync repository to SourceForge via lftp (SFTP)
# Usage: ./sync-sourceforge.sh <local-repo-dir> <sourceforge-path>

set -euo pipefail

LOCAL_DIR="${1:?Local repository directory required}"
REMOTE_PATH="${2:?SourceForge remote path required}"

# Validate local directory
if [ ! -d "$LOCAL_DIR" ]; then
    echo "Error: Local directory not found: $LOCAL_DIR"
    exit 1
fi

echo "=== Syncing Repository to SourceForge ==="
echo "Local directory: $LOCAL_DIR"
echo "Remote path: $REMOTE_PATH"
echo ""

# Check if lftp is installed
if ! command -v lftp &> /dev/null; then
    echo "Error: lftp is not installed"
    exit 1
fi

# Extract components from REMOTE_PATH (user@host:/path/to/dir/)
# Example: jmendezr@frs.sourceforge.net:/home/frs/project/wolfi/
REMOTE_USER=$(echo "$REMOTE_PATH" | cut -d@ -f1)
REMOTE_HOST=$(echo "$REMOTE_PATH" | cut -d@ -f2 | cut -d: -f1)
REMOTE_DIR=$(echo "$REMOTE_PATH" | cut -d: -f2)

echo "Starting sync with lftp..."
echo "Host: $REMOTE_HOST"
echo "Remote directory: $REMOTE_DIR"
echo ""

# Use lftp to mirror the local directory to SourceForge
# Options:
#   -R: Reverse mirror (upload from local to remote)
#   --verbose: Show detailed progress
#   --exclude-glob: Exclude patterns
#   --parallel=3: Upload 3 files in parallel for speed (APK files only)
# NOTE: NO --delete flags - we want to accumulate packages from multiple builds

# First sync: Upload all .apk files and keys with parallel transfers (fast)
lftp sftp://${REMOTE_HOST} <<EOF
set sftp:auto-confirm yes
set net:timeout 30
set net:max-retries 3
set net:reconnect-interval-base 5

cd ${REMOTE_DIR}
mirror -R --verbose --parallel=3 \
    --exclude-glob .git/ \
    --exclude-glob .git \
    --exclude-glob '*.tmp' \
    --exclude-glob '*.log' \
    --exclude-glob 'APKINDEX.tar.gz' \
    ${LOCAL_DIR} .

quit
EOF

if [ $? -ne 0 ]; then
    echo "✗ Initial sync failed"
    exit 1
fi

# Second sync: Upload APKINDEX files WITHOUT parallel transfers (reliable)
# These are critical files that must upload completely
# Note: Not using --parallel means sequential uploads (default behavior)
echo "Uploading APKINDEX files (critical, sequential uploads)..."
lftp sftp://${REMOTE_HOST} <<EOF
set sftp:auto-confirm yes
set net:timeout 60
set net:max-retries 5
set net:reconnect-interval-base 10

cd ${REMOTE_DIR}

# Upload x86_64 APKINDEX
put -O x86_64 ${LOCAL_DIR}/x86_64/APKINDEX.tar.gz

# Upload aarch64 APKINDEX
put -O aarch64 ${LOCAL_DIR}/aarch64/APKINDEX.tar.gz

quit
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Repository synced successfully to SourceForge"
    echo "Public URL: https://downloads.sourceforge.net/project/wolfi/"
else
    echo ""
    echo "✗ Sync failed"
    exit 1
fi

echo ""
echo "=== Sync completed ==="
