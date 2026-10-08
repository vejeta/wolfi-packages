# Research: Packaging Format Conversion Tools

Survey of existing tooling to convert between Alpine (`APKBUILD`), Debian
(`debian/`) and melange YAML, carried out before building anything new.

> Status: initial survey (2026-10). Items marked *verify* should be re-checked
> against the latest melange / wolfictl releases (`melange convert --help`,
> `wolfictl --help`) before starting implementation.

## Summary

| Direction | Exists? | Where | Gap we can cover |
|-----------|---------|-------|------------------|
| Alpine → melange | Partial | `melange convert apkbuild` (experimental, *verify* still shipped) | Robust converter: patches, subpackages, `checkdepends`, `_` variables, local APKBUILD files |
| Debian → melange | No | — | Full tool (`debian/control` + `debian/rules` + `debian/patches`) |
| melange → Debian | No | — | Full tool (generate `debian/` skeleton) |
| melange → Alpine | No | — | Full tool (generate `APKBUILD`) |
| "Does this package already exist?" | No unified tool | Per-distro web UIs/APIs only | `pkg-check` (see `tools/pkg-check/`) |

## 1. alpine-to-melange

- **melange `convert apkbuild`**: melange shipped a `convert` command family
  (`convert apkbuild`, `convert gem`, `convert python`). The apkbuild converter
  fetches an `APKBUILD` from Alpine's aports and generates a melange YAML for
  the package and, optionally, its missing dependencies.
  - Tracking issue for accepting local files/URIs:
    [chainguard-dev/melange#621](https://github.com/chainguard-dev/melange/issues/621)
    (the apkbuild item was still open when last indexed).
  - Limitations observed in practice:
    - Parses APKBUILD by heuristics, not by evaluating shell, so `${_var}`
      substitutions, conditionals and arch-specific blocks are often lost.
    - `build()` / `package()` are mapped to generic `autoconf/*` pipelines;
      custom logic must be ported by hand.
    - Patches listed in `source=` are not wired up as `patch` pipeline steps.
    - Subpackages (`-dev`, `-doc`, `-libs`) are only partially mapped to
      melange `split/*` pipelines.
    - Experimental; output is a starting point, never build-ready.
  - **Action**: before writing our own, test the current melange release on
    3–4 APKBUILDs from this repo's history (libass, mujs, zimg). If it still
    exists and is usable, we contribute a wrapper/post-processor instead of
    a new tool.
- No independent, maintained third-party `apkbuild2melange` project was found.

## 2. debian-to-melange

- No tool found (GitHub, melange docs, wolfi-dev discussions).
- Manual mapping is well-defined and automatable for the common `dh` cases:

| Debian | melange |
|--------|---------|
| `debian/control` `Source`, `Package`, `Description` | `package.name`, `package.description` |
| `debian/changelog` (upstream part of version) | `package.version` |
| `debian/copyright` (DEP-5 `License:`) | `package.copyright[].license` |
| `Build-Depends` | `environment.contents.packages` (needs name mapping) |
| `Depends` (`${shlibs:Depends}` dropped) | `package.dependencies.runtime` |
| `debian/watch` / `.orig.tar.*` | `pipeline: fetch` + `expected-sha256`, `update:` |
| `debian/patches/series` | `pipeline: patch` with `patches:` |
| `dh $@ --buildsystem=cmake|meson|autoconf` | `cmake/*`, `meson/*`, `autoconf/*` pipelines |
| `override_dh_auto_configure: ... -- FLAGS` | `with: opts:` on the configure pipeline |
| Extra binary packages (`libfoo-dev`) | `subpackages:` + `split/dev`, etc. |

- Hard parts: arbitrary Makefile logic in `debian/rules`, and package-name
  mapping Debian → Wolfi (`libfoo-dev` → `foo-dev`). A mapping table is needed.

## 3. melange-to-debian

- No tool found. melange only emits `.apk`.
- Feasible because melange YAML is declarative: generate `debian/control`,
  `debian/rules` (`dh` with the matching buildsystem), `debian/patches/series`,
  `debian/copyright` (DEP-5 from SPDX) and `debian/source/format`.
- Value: lets packagers working in Wolfi upstream the same work to Debian.

## 4. melange-to-alpine

- No tool found.
- Closest mapping of the four; melange's design borrows from APKBUILD.
  `fetch` → `source=`/`sha512sums=`, pipelines → `build()`/`package()`,
  `subpackages` → `subpackages=` + split functions.

## Gaps this project can cover (priority order)

1. **pkg-check** — cheap, immediately useful, prevents duplicated work.
2. **alpine-to-melange** — highest demand; build on or wrap
   `melange convert apkbuild` if still available.
3. **debian-to-melange** — no existing solution; covers `dh`-based packages.
4. **melange-to-debian** / **melange-to-alpine** — upstreaming helpers.

## Sources

- melange: https://github.com/chainguard-dev/melange
- melange convert issue: https://github.com/chainguard-dev/melange/issues/621
- melange overview: https://edu.chainguard.dev/open-source/build-tools/melange/overview/
- melange YAML reference: https://edu.chainguard.dev/open-source/build-tools/melange/reference/
