# Test case: stremio-server-installer

First target for `debian-to-melange`.

- Input: Debian contrib source package `stremio-server-installer` (1)
  https://sources.debian.org/src/stremio-server-installer/1/debian/
- `expected/`: hand-written reference port, used as the golden output the
  converter should approximate. It is **not** a published package.

Mapping exercised by this case:

| Debian | melange |
|--------|---------|
| `debian/rules` `SERVER_VERSION` / `SERVER_SHA256` | `package.version` / `vars.server-sha256` |
| `debian/postinst.in` (`#VERSION#`, `#HASH#`) | installed helper script + `scripts.post-install` / `post-upgrade` |
| `debian/config` + `debian/templates` (debconf prompt) | `/etc/stremio-server-installer.conf` (`STREMIO_SERVER_DOWNLOAD`) |
| `Depends: wget, ca-certificates` | `dependencies.runtime: busybox, ca-certificates-bundle` |
| `debian/copyright` (`GPL-3.0-only`) | `copyright[].license` |
| `debian/README.source` | `/usr/share/doc/stremio-server-installer/README` |

server.js 4.21.1 sha256 `405eb494…930f` was verified against
https://dl.strem.io/server/v4.21.1/desktop/server.js on 2026-10-08.
