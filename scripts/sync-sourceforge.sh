#!/bin/bash
# Sync repository to SourceForge via rsync over SSH
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

# Check if rsync is installed
if ! command -v rsync &> /dev/null; then
    echo "Error: rsync is not installed"
    exit 1
fi

# Check SSH connectivity
echo "Testing SSH connection..."
SOURCEFORGE_HOST=$(echo "$REMOTE_PATH" | cut -d@ -f2 | cut -d: -f1)
SOURCEFORGE_USER=$(echo "$REMOTE_PATH" | cut -d@ -f1)

ssh -o BatchMode=yes -o ConnectTimeout=10 "${SOURCEFORGE_USER}@${SOURCEFORGE_HOST}" 'echo "SSH connection successful"' 2>/dev/null

if [ $? -ne 0 ]; then
    echo "⚠ SSH connection test failed, but proceeding anyway..."
    echo "Make sure SSH keys are properly configured"
fi

echo ""
echo "Starting rsync..."

# Sync with rsync
# Options:
#   -a: archive mode (preserves permissions, timestamps, etc.)
#   -v: verbose
#   -z: compress during transfer
#   -P: show progress and keep partial files
#   --delete: delete files on remote that don't exist locally
#   --exclude: exclude certain files/patterns

rsync -avzP \
    --delete \
    --exclude=".git" \
    --exclude="*.tmp" \
    --exclude="*.log" \
    "$LOCAL_DIR/" \
    "$REMOTE_PATH"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Repository synced successfully to SourceForge"
    echo "Public URL: https://downloads.sourceforge.net/project/wolfi/repo/"
else
    echo ""
    echo "✗ Sync failed"
    exit 1
fi

echo ""
echo "=== Sync completed ==="
