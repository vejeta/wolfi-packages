# APK Signing Keys

## IMPORTANT: Keys are NOT stored in this directory

For security reasons, signing keys are stored in `~/.ssh/` directory, **outside** of this repository.

This directory only contains documentation. The `.gitignore` is configured to prevent accidental commits of private keys.

## Key Location

APK signing keys should be stored in:
```
~/.ssh/vejeta-wolfi.rsa       # Private key (NEVER commit)
~/.ssh/vejeta-wolfi.rsa.pub   # Public key
```

SourceForge SSH keys are stored in:
```
~/.ssh/sourceforge_wolfi_rsa      # Private key (NEVER commit)
~/.ssh/sourceforge_wolfi_rsa.pub  # Public key
```

## Key Generation

### 1. Generate APK Signing Key

```bash
# Generate 4096-bit RSA private key
cd ~/.ssh
openssl genrsa -out vejeta-wolfi.rsa 4096

# Extract public key
openssl rsa -in vejeta-wolfi.rsa -pubout -out vejeta-wolfi.rsa.pub

# Set proper permissions
chmod 600 vejeta-wolfi.rsa
chmod 644 vejeta-wolfi.rsa.pub
```

### 2. Generate SourceForge SSH Key

```bash
# Generate SSH key
ssh-keygen -t rsa -b 4096 -f ~/.ssh/sourceforge_wolfi_rsa -C "wolfi-repo@sourceforge"

# Don't use passphrase for CI/CD automation
```

## GitHub Secrets Configuration

Add these secrets to your GitHub repository at:
`https://github.com/vejeta/wolfi-packages/settings/secrets/actions`

### APK_SIGNING_KEY
The complete content of the **private** key file:
```bash
cat ~/.ssh/vejeta-wolfi.rsa
```

### APK_KEY_NAME
The filename of your key (without .rsa extension):
```
vejeta-wolfi
```

### SOURCEFORGE_SSH_KEY
Your SourceForge SSH private key:
```bash
cat ~/.ssh/sourceforge_wolfi_rsa
```

## Public Key Distribution

The **public** key should be:
- Published to SourceForge at `/keys/vejeta-wolfi.rsa.pub`
- Downloaded by users to `/etc/apk/keys/`

Upload to SourceForge:
```bash
scp ~/.ssh/vejeta-wolfi.rsa.pub \
    jmendezr@frs.sourceforge.net:/home/frs/project/wolfi/keys/
```

## Key Security

### Do:
- Keep private keys in `~/.ssh/` with mode 600
- Store in GitHub Secrets for CI/CD
- Backup keys securely offline (encrypted)
- Use different keys for different purposes

### Don't:
- Never commit private keys to Git
- Never share private keys via email/chat
- Never store keys in repository directories
- Never reuse keys across projects

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

Record your key fingerprint for verification:

```bash
# SHA256 fingerprint
openssl rsa -in ~/.ssh/vejeta-wolfi.rsa -pubout -outform DER | sha256sum

# Display public key details
openssl rsa -in ~/.ssh/vejeta-wolfi.rsa -text -noout | head -20
```

## Backup Procedure

```bash
# Create encrypted backup
cd ~/.ssh
tar czf wolfi-keys-backup-$(date +%Y%m%d).tar.gz \
    vejeta-wolfi.rsa vejeta-wolfi.rsa.pub \
    sourceforge_wolfi_rsa sourceforge_wolfi_rsa.pub

# Encrypt with GPG
gpg --symmetric --cipher-algo AES256 wolfi-keys-backup-*.tar.gz

# Move to secure location
mv wolfi-keys-backup-*.tar.gz.gpg ~/secure-backup/

# Verify backup
gpg --decrypt ~/secure-backup/wolfi-keys-backup-*.tar.gz.gpg | tar tz
```

## Additional Resources

- [APK Tools Documentation](https://wiki.alpinelinux.org/wiki/Package_management)
- [Melange Documentation](https://github.com/chainguard-dev/melange)
- [OpenSSL RSA](https://www.openssl.org/docs/man3.0/man1/openssl-rsa.html)
