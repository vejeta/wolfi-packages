# APK Signing Keys

This directory contains documentation for APK package signing keys.

## ⚠️ IMPORTANT

**NEVER commit private keys to this repository!**

The `.gitignore` file is configured to prevent accidental commits of private keys.

## Key Generation

### 1. Generate RSA Key Pair

```bash
# Generate 4096-bit RSA private key
openssl genrsa -out vejeta-wolfi.rsa 4096

# Extract public key
openssl rsa -in vejeta-wolfi.rsa -pubout -out vejeta-wolfi.rsa.pub

# Set proper permissions
chmod 600 vejeta-wolfi.rsa
chmod 644 vejeta-wolfi.rsa.pub
```

### 2. Alternative: Using Melange

```bash
# Melange can generate signing keys
melange keygen vejeta-wolfi.rsa
```

## GitHub Secrets Configuration

Add these secrets to your GitHub repository:

### `APK_SIGNING_KEY`
The complete content of the **private** key file (`vejeta-wolfi.rsa`):

```bash
# Copy the private key content
cat vejeta-wolfi.rsa | pbcopy  # macOS
cat vejeta-wolfi.rsa | xclip -selection clipboard  # Linux

# Or display it to copy manually
cat vejeta-wolfi.rsa
```

Then go to:
1. GitHub repository → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `APK_SIGNING_KEY`
4. Value: Paste the private key content
5. Click "Add secret"

### `APK_KEY_NAME`
The filename of your key (without .rsa extension):

```
vejeta-wolfi
```

### `SOURCEFORGE_SSH_KEY`
Your SourceForge SSH private key for rsync deployment.

## Public Key Distribution

The **public** key (`vejeta-wolfi.rsa.pub`) should be:
- ✅ Published to SourceForge at `/keys/vejeta-wolfi.rsa.pub`
- ✅ Included in repository documentation
- ✅ Downloaded by users to `/etc/apk/keys/`

## Key Security

### Do:
- ✅ Keep private keys in GitHub Secrets
- ✅ Use strong passphrases (if encrypting keys)
- ✅ Regularly rotate keys (annually recommended)
- ✅ Backup private keys securely offline
- ✅ Use different keys for different purposes

### Don't:
- ❌ Commit private keys to Git
- ❌ Share private keys via email/chat
- ❌ Store keys in cloud storage without encryption
- ❌ Reuse keys across projects
- ❌ Lose private keys (no recovery possible)

## Key Verification

Users can verify packages with:

```bash
# Download public key
wget -O /etc/apk/keys/vejeta-wolfi.rsa.pub \
  https://sourceforge.net/projects/wolfi/files/keys/vejeta-wolfi.rsa.pub

# Verify packages
apk verify stremio
```

## Key Fingerprint

After generating your key, record its fingerprint:

```bash
# SHA256 fingerprint
openssl rsa -in vejeta-wolfi.rsa -pubout -outform DER | sha256sum

# Display public key details
openssl rsa -in vejeta-wolfi.rsa -text -noout
```

Document the fingerprint in your admin documentation for verification.

## Emergency Key Rotation

If your private key is compromised:

1. **Immediately** revoke the compromised key
2. Generate new RSA key pair
3. Update GitHub Secrets with new keys
4. Re-sign all packages with new key
5. Publish new public key to SourceForge
6. Notify users to update their trusted keys
7. Update documentation

## Additional Resources

- [APK Tools Documentation](https://wiki.alpinelinux.org/wiki/Package_management)
- [Melange Documentation](https://github.com/chainguard-dev/melange)
- [OpenSSL RSA](https://www.openssl.org/docs/man3.0/man1/openssl-rsa.html)
