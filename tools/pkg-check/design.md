# pkg-check — Design

A gate to run **before** packaging anything: does this package already exist
in Wolfi, Alpine or Debian, and at which version?

## Goals

- Answer "is it already packaged?" in seconds, from the command line and CI.
- Point contributors to reusable recipes (Alpine `APKBUILD`, Debian `debian/`).
- Flag when another distribution ships an older version than ours.
- Zero dependencies (Python 3 standard library) so it runs anywhere,
  including a bare `wolfi-base` container.

Non-goals (for now): name mapping across distributions (`libfoo-dev` vs
`foo-dev`), fuzzy search, Fedora/Arch/Nix.

## CLI

```bash
pkg-check --target debian --package mpv
pkg-check --target alpine --package libass --version 0.17.4
pkg-check --target wolfi  --package stremio
pkg-check --package mpv --package libass          # all targets
pkg-check -t alpine --alpine-branch v3.22 -p mpv
pkg-check -p mpv --json                            # machine-readable
```

| Option | Default | Meaning |
|--------|---------|---------|
| `--target/-t` | `all` | `debian`, `alpine`, `wolfi`, `all`; repeatable |
| `--package/-p` | required | Package name; repeatable |
| `--version/-V` | from `packages/<name>.yaml` | "Your" version to compare against |
| `--arch` | `x86_64` | Architecture for APKINDEX lookups |
| `--alpine-branch` | `edge` | Alpine branch |
| `--debian-suite` | first of stable, testing, unstable… | Suite shown in the summary |
| `--no-cache` | cache on | Bypass the local index cache |
| `--json` | off | One JSON object per (package, target) |
| `--verbose/-v` | off | All suites / subpackages |

### Output

```
✓ mpv exists in Debian (stable): 0.40.0-3+deb13u1
✗ stremio does NOT exist in Wolfi
? libass exists in Alpine (edge/community) but older version: 0.17.1-r0 (yours: 0.17.4)
! mpv: could not query Debian: <error>
```

### Exit codes

The highest code across all lookups is returned, so CI can gate on it.

| Code | Meaning |
|------|---------|
| 0 | Absent in every queried target — safe to package |
| 1 | Present (same or newer version) |
| 2 | Present, but older than ours |
| 3 | A query failed |

## Data sources

| Target | Source | Why |
|--------|--------|-----|
| Debian | `https://api.ftp-master.debian.org/madison?f=json&package=<name>` | Official, JSON, accepts binary *and* source names, returns every suite |
| Debian (alt.) | `https://sources.debian.org/api/src/<name>/` | Source packages only; fallback candidate |
| Alpine | `https://dl-cdn.alpinelinux.org/alpine/<branch>/{main,community,testing}/<arch>/APKINDEX.tar.gz` | Authoritative, includes subpackages and origins; pkgs.alpinelinux.org has no stable JSON API |
| Wolfi | `https://packages.wolfi.dev/os/<arch>/APKINDEX.tar.gz` | Authoritative for what is actually published, includes subpackages |
| Wolfi (alt.) | `https://raw.githubusercontent.com/wolfi-dev/os/main/<name>.yaml` | Cheap single-package lookup, but misses subpackages and unpublished state |

APKINDEX files (Alpine ~2.5 MB per repo, Wolfi ~10 MB) are cached in
`$XDG_CACHE_HOME/pkg-check/` for 6 hours.

### Matching

- **Debian**: madison matches binary and source package names.
- **Alpine / Wolfi**: exact match on package name (`P:`); if there is no
  exact match, a match on origin (`o:`) is reported as "only as subpackage(s)".
  Subpackages of the same origin are listed as notes.

### Version comparison

Distribution decorations are stripped before comparing upstream versions:

- Debian: epoch (`1:`), revision (`-3+deb13u1`), repack suffixes (`+dfsg`, `+ds`).
- Alpine/Wolfi: package release (`-r0`).

Comparison splits versions into numeric and alphabetic runs; numbers compare
numerically, and a trailing alphabetic run (`rc1`, `beta`) sorts before the
final release. This is not a full `dpkg`/`apk` implementation, but it is
correct for upstream version strings in practice.

## Integration points

- **CONTRIBUTING.md**: step 1 of the contributor workflow.
- **CI (planned)**: a job on pull requests that runs
  `pkg-check --target wolfi -p <each new packages/*.yaml>` and fails when
  exit code is 1 (package already in official Wolfi).
- **Scheduled job (planned)**: weekly run over all `packages/*.yaml` that
  opens an issue when a package lands in official Wolfi, so it can be retired here.

## Roadmap

1. ~~Debian backend~~ ✓, ~~Alpine backend~~ ✓, ~~Wolfi backend~~ ✓ (v0.1)
2. `--all-recipes`: iterate over every `packages/*.yaml`.
3. Name-mapping table (Debian `libfoo-dev` → Wolfi `foo-dev`, `python3-x` → `py3-x`).
4. Print links to the upstream recipe (aports `APKBUILD`, salsa `debian/`).
5. Additional targets: Fedora (mdapi), Arch (`archlinux.org/packages/search/json`), Repology as an aggregate fallback.
6. Package as an APK in this repository (`pkg-check.yaml`).
