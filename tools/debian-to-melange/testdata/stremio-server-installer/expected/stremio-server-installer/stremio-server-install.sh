#!/bin/sh
# stremio-server-install: download Stremio's streaming server (server.js)
# from Stremio's own CDN, verify its checksum and install it where the
# stremio package expects it. server.js is not redistributed by this
# repository; see /usr/share/doc/stremio-server-installer/README.
#
# Port of Debian's stremio-server-installer (contrib) to Wolfi.

set -e

version="@VERSION@"
hash="@SHA256@"
file="server.js"
url="https://dl.strem.io/server/v${version}/desktop/${file}"

conffile="/etc/stremio-server-installer.conf"
cachedir="/var/cache/stremio-server-installer"
destdir="/usr/share/stremio"

STREMIO_SERVER_DOWNLOAD=yes
# shellcheck disable=SC1090
[ -r "${conffile}" ] && . "${conffile}"

msg() { echo "stremio-server-installer: $*"; }

error()
{
	echo "stremio-server-installer: $1" >&2
	rm -f "${cachedir}/${file}" "${cachedir}/${file}.tmp"
	exit 1
}

usage()
{
	cat <<USAGE
Usage: stremio-server-install [--auto | --force | --remove | --version | --help]

  (no option)  download and install server.js ${version}
  --auto       same, but honour STREMIO_SERVER_DOWNLOAD in ${conffile}
               (used by the package install scripts)
  --force      re-download even if the installed copy is up to date
  --remove     remove the installed server.js and the download cache
  --version    print the server.js version this installer fetches
USAGE
}

installed_ok()
{
	[ -f "${destdir}/${file}" ] &&
		echo "${hash}  ${destdir}/${file}" | sha256sum -c >/dev/null 2>&1
}

remove()
{
	rm -f "${destdir}/${file}"
	rm -rf "${cachedir}"
	msg "removed ${destdir}/${file}"
}

install_server()
{
	if [ "$1" != "force" ] && installed_ok; then
		msg "server.js ${version} already installed"
		return 0
	fi

	mkdir -p "${cachedir}"
	cd "${cachedir}"

	msg "downloading ${url}"
	wget -q -O "${file}.tmp" "${url}" || error "download failed"
	mv "${file}.tmp" "${file}"

	echo "${hash}  ${file}" | sha256sum -c >/dev/null 2>&1 \
		|| error "checksum mismatch for ${file}, expected ${hash}"

	install -Dm644 "${cachedir}/${file}" "${destdir}/${file}"
	msg "installed ${destdir}/${file}"
}

case "${1:-}" in
	"")        install_server ;;
	--auto)
		case "${STREMIO_SERVER_DOWNLOAD}" in
			yes|true|1) install_server ;;
			*) msg "download disabled in ${conffile}, skipping" ;;
		esac ;;
	--force)   install_server force ;;
	--remove)  remove ;;
	--version) echo "${version}" ;;
	-h|--help) usage ;;
	*)         usage >&2; exit 2 ;;
esac
