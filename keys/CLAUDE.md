# APK Repository Signing Keys - Documentation

This document provides detailed information about the APK signing keys used for the wolfi-packages repository.

## Key Types and Purposes

This repository uses three different types of keys:

### 1. Repository Signing Key (`melange.rsa` / `melange.rsa.pub`)

**Purpose**: Sign all APK packages built by this repository

- **Private key**: `melange.rsa` (stored in GitHub Secrets as `APK_SIGNING_KEY`)
- **Public key**: `melange.rsa.pub` (published to SourceForge for user verification)
- **Key name**: `vejeta-wolfi.rsa` (stored in GitHub Secret as `APK_KEY_NAME`)
- **Location**: `~/.ssh/melange.rsa` and `~/.ssh/melange.rsa.pub`

**Fingerprint (SHA256)**:
```
c6e801d014d83b1f6cd3ba3185bdb8e6c719c183e514a9d47f213b0f4466c292
```

This is the key that signs all packages in this community repository. Users need the public key to verify package signatures.

### 2. Official Wolfi Signing Key (`wolfi-signing.rsa.pub`)

**Purpose**: Verify packages from the official Wolfi repository

- **Public key only**: Downloaded from `https://packages.wolfi.dev/os/wolfi-signing.rsa.pub`
- **Used by**: Build system to verify dependencies from upstream Wolfi

This key is maintained by the Chainguard Wolfi team, not by this repository.

### 3. SourceForge SSH Key (`sourceforge_wolfi_rsa`)

**Purpose**: Authenticate with SourceForge for uploading packages

- **Private key**: `sourceforge_wolfi_rsa` (stored in GitHub Secret as `SOURCEFORGE_SSH_KEY`)
- **Public key**: Added to SourceForge account settings
- **Used by**: CI/CD workflow to upload packages via SFTP/rsync

This key is only for authentication, NOT for signing packages.

## Current Status

### GitHub Secrets Configuration

All required secrets are configured in the repository:

1. **APK_SIGNING_KEY** - Contains the private RSA key (melange.rsa) for signing packages
2. **APK_KEY_NAME** - Contains the key name: `vejeta-wolfi.rsa`
3. **SOURCEFORGE_SSH_KEY** - Contains the SourceForge SSH private key for uploads

### SourceForge Public Key Status

**⚠️ ACTION REQUIRED**: The public signing key (`melange.rsa.pub`) needs to be uploaded to SourceForge.

Current state:
- ✅ Keys stored in `~/.ssh/` directory
- ✅ Keys stored in GitHub Secrets
- ❌ Public key NOT yet published to SourceForge

Until the public key is uploaded, users must use `--allow-untrusted` flag when installing packages.

## Uploading Public Key to SourceForge

### Prerequisites

1. Ensure you have the key files in `~/.ssh/`:
   ```bash
   ls -l ~/.ssh/melange.rsa*
   ```

2. Verify the fingerprint matches:
   ```bash
   openssl rsa -in ~/.ssh/melange.rsa -pubout -outform DER | sha256sum
   # Should output: c6e801d014d83b1f6cd3ba3185bdb8e6c719c183e514a9d47f213b0f4466c292
   ```

### Upload Using lftp (Recommended)

```bash
# Create a temporary directory for upload
mkdir -p /tmp/wolfi-keys
cp ~/.ssh/melange.rsa.pub /tmp/wolfi-keys/vejeta-wolfi.rsa.pub

# Upload using lftp with SFTP protocol
lftp -c "
  set sftp:auto-confirm yes
  set net:timeout 30
  set net:max-retries 3
  set net:reconnect-interval-base 5
  open sftp://jmendezr@frs.sourceforge.net
  cd /home/frs/project/wolfi/keys/
  put /tmp/wolfi-keys/vejeta-wolfi.rsa.pub
  bye
"

# Cleanup
rm -rf /tmp/wolfi-keys
```

**Note**: You will be prompted for your SourceForge password or SSH key passphrase.

### Alternative: Upload Using scp

```bash
# Copy and rename in one step
scp ~/.ssh/melange.rsa.pub jmendezr@frs.sourceforge.net:/home/frs/project/wolfi/keys/vejeta-wolfi.rsa.pub
```

### Verification

Verify the key was uploaded successfully:

```bash
# Using lftp to list files
lftp -c "
  set sftp:auto-confirm yes
  open sftp://jmendezr@frs.sourceforge.net
  ls /home/frs/project/wolfi/keys/
  bye
"
```

Or download and verify the fingerprint:

```bash
# Download the public key
curl -o /tmp/vejeta-wolfi.rsa.pub \
  https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub/download

# Verify fingerprint matches
openssl rsa -pubin -in /tmp/vejeta-wolfi.rsa.pub -pubout -outform DER | sha256sum
# Should output: c6e801d014d83b1f6cd3ba3185bdb8e6c719c183e514a9d47f213b0f4466c292

# Cleanup
rm /tmp/vejeta-wolfi.rsa.pub
```

## Updating README After Key Upload

Once the public key is uploaded to SourceForge, update the README.md installation instructions:

```bash
# Add the repository signing key
curl -o /etc/apk/keys/vejeta-wolfi.rsa.pub \
  https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub/download

# Add repository to apk (no --allow-untrusted needed!)
echo "https://downloads.sourceforge.net/project/wolfi/$(uname -m)" >> /etc/apk/repositories

# Update package index
apk update

# Install packages (signatures verified automatically)
apk add stremio mpv qt5-qtwebengine
```

## Workflow Integration Issues

### Current Problem

The build workflow (`.github/workflows/build-packages.yml`) has a critical issue at lines 104-122:

```yaml
- name: Generate Melange signing key
  run: |
    docker run --rm \
      -v $PWD:/work \
      -w /work \
      cgr.dev/chainguard/melange:latest \
      keygen  # ⚠️ Generates NEW key every build!
```

This generates a **new key for every build**, making all previous package signatures invalid.

### Proper Implementation (TODO)

The workflow should be modified to use the stored GitHub Secret instead:

```yaml
- name: Setup Melange signing key from GitHub Secrets
  run: |
    echo "${{ secrets.APK_SIGNING_KEY }}" > melange.rsa
    chmod 600 melange.rsa

    # Extract public key from private key
    openssl rsa -in melange.rsa -pubout -out melange.rsa.pub
    chmod 644 melange.rsa.pub

    # Download official Wolfi signing key
    curl -o wolfi-signing.rsa.pub https://packages.wolfi.dev/os/wolfi-signing.rsa.pub
```

**Status**: This fix is deferred. For now, the repository continues using `--allow-untrusted` flag in documentation.

## Security Best Practices

1. **Never commit private keys** - The `.gitignore` file excludes `*.rsa` files
2. **Protect GitHub Secrets** - Only repository admins can access secrets
3. **Rotate keys periodically** - Consider rotating keys annually
4. **Backup keys securely** - Keep encrypted backups (see `wolfi-keys-backup-20251110.tar.gz`)
5. **Verify fingerprints** - Always verify the key fingerprint after download

## Troubleshooting

### Package Signature Verification Fails

If users get signature verification errors:

```bash
# Install with --allow-untrusted temporarily
apk add --allow-untrusted stremio

# Or add the public key manually
curl -o /etc/apk/keys/vejeta-wolfi.rsa.pub \
  https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub/download
```

### Wrong Key Fingerprint

If the fingerprint doesn't match, the key may have been corrupted:

```bash
# Re-download from GitHub Secrets (repository admins only)
gh secret get APK_SIGNING_KEY > melange.rsa

# Or restore from backup
tar -xzf keys/wolfi-keys-backup-20251110.tar.gz
```

## References

- [Melange Signing Documentation](https://github.com/chainguard-dev/melange/blob/main/docs/SIGNING.md)
- [APK Package Signing](https://wiki.alpinelinux.org/wiki/Abuild_and_Helpers#Signing_Packages)
- [SourceForge File Release System](https://sourceforge.net/p/forge/documentation/File%20Management/)
- [Official Wolfi Documentation](https://edu.chainguard.dev/open-source/wolfi/overview/)

---

**Last Updated**: 2025-11-11
**Maintained By**: Juan Manuel Méndez Rey (vejeta)
