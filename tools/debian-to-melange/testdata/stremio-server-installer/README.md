# Test case: stremio-server-installer

First real-world case for `debian-to-melange`.

- `debian/`: Debian contrib source package `stremio-server-installer` (1),
  from https://sources.debian.org/src/stremio-server-installer/1/debian/
  (translations in `debian/po/` omitted; they are not used by the converter).
- `expected/`: converter output (snapshot). Identical, apart from the header
  link, to the published [`packages/stremio-server-installer.yaml`](../../../../packages/stremio-server-installer.yaml),
  which is generated with `--from-debian stremio-server-installer`.
- `reference/`: the hand-written port made before the converter existed,
  kept for comparison. It is not built or published.

Verified on 2026-10-13 with melange v0.62.1 (bubblewrap runner):

- `melange build` and `melange test` pass.
- The generated `.post-install` downloads server.js 4.21.1 and its sha256
  matches `405eb494…930f`; `STREMIO_SERVER_INSTALLER_DOWNLOAD="false"` skips
  the download; a wrong checksum exits 1 and installs nothing.
