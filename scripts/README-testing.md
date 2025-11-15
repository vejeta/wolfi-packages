# Testing Scripts for Cirrus CI Changes

This directory contains scripts to test and validate changes to `.cirrus.yml` before committing.

## Quick Validation (Recommended for Pre-Commit)

**Script**: `test-cirrus-changes.sh`

Fast validation that checks critical issues without requiring Docker:

```bash
./scripts/test-cirrus-changes.sh
```

**What it checks:**
- ✓ `file` package is included in dependencies
- ✓ Initramfs combination order (Alpine first, then melange)
- ✓ Compression detection uses `file` command
- ✓ Error handling with `COMBINE_FAILED` flag
- ✓ Cleanup of temporary files

**Usage**: Run manually or automatically via git pre-commit hook.

## Full Docker Test

**Script**: `test-qemu-wrapper.sh`

Complete test that simulates the Cirrus CI environment using Docker:

```bash
./scripts/test-qemu-wrapper.sh
```

**What it does:**
1. Extracts QEMU wrapper script from `.cirrus.yml`
2. Checks all dependencies are listed
3. Tests in Alpine container (same as Cirrus CI)
4. Verifies `file` command works
5. Tests initramfs detection and combination logic
6. Validates combined initramfs is correct gzip format

**Requirements:**
- Docker installed and running
- Internet connection (to pull Alpine image)

**When to use:**
- Before pushing major changes
- When debugging initramfs combination issues
- To verify changes work in actual Alpine environment

## Git Pre-Commit Hook

A pre-commit hook is automatically installed at `.git/hooks/pre-commit` that runs `test-cirrus-changes.sh` when `.cirrus.yml` is modified.

**To skip the hook** (not recommended):
```bash
git commit --no-verify -m "message"
```

**To test the hook manually:**
```bash
# Stage .cirrus.yml changes
git add .cirrus.yml

# The hook will run automatically
git commit -m "Update Cirrus CI config"
```

## Troubleshooting

### Docker test fails with "permission denied"
- Ensure Docker is running: `docker ps`
- Check Docker permissions: `docker run --rm alpine:latest echo "test"`

### Pre-commit hook not running
- Verify hook is executable: `ls -la .git/hooks/pre-commit`
- Check if hook exists: `test -f .git/hooks/pre-commit && echo "exists"`

### Validation passes but Cirrus CI still fails
- Run full Docker test: `./scripts/test-qemu-wrapper.sh`
- Check Cirrus CI logs for specific error messages
- Verify all dependencies are available in Alpine repository

## Best Practices

1. **Always run quick validation** before committing `.cirrus.yml` changes
2. **Run full Docker test** before pushing to master/main
3. **Don't skip pre-commit hook** unless absolutely necessary
4. **Check Cirrus CI logs** after pushing to verify changes work
