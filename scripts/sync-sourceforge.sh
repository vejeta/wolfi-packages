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

# No SSH test needed - SourceForge has a restricted shell that doesn't allow commands
# rsync will fail immediately if SSH doesn't work
echo "Starting rsync to SourceForge..."

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
