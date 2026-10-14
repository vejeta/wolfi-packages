# melange-to-debian

Generate a `debian/` directory from a [melange](https://github.com/chainguard-dev/melange)
recipe. It is the reverse of [`debian-to-melange`](../debian-to-melange/) and
is meant as a starting point for an ITP: many packages exist in Wolfi but not
in Debian.

A melange recipe does not contain everything a Debian package needs:
copyright holders, a long description, and SONAME-based names for library
packages. Those places are marked `TODO(melange-to-debian)` in the output and
listed on stderr.

Python ≥ 3.9 and PyYAML (`python3-yaml`).

## Usage

```bash
tools/melange-to-debian/melange-to-debian.py packages/libxmlb.yaml --out ~/src/libxmlb
grep -rn 'TODO(melange-to-debian)' ~/src/libxmlb/debian
```

| Option | Purpose |
|--------|---------|
| `--out DIR` | Directory in which `debian/` is created (default `./NAME`) |
| `--maintainer "Name <email>"` | Defaults to `$DEBFULLNAME <$DEBEMAIL>` |
| `--check-debian` | Look up the mapped dependency names in Debian unstable (uses `pkg-check`) |
| `--force` | Overwrite an existing `debian/` |
| `--strict` | Exit 1 if anything needs manual review |

## What is generated

| melange | Debian |
|---------|--------|
| `package`, `subpackages` | `debian/control`: one binary package per subpackage; `-dev` in `libdevel`, `-doc` as `Architecture: all` |
| `environment.contents.packages` | `Build-Depends`, with Wolfi names mapped to Debian names |
| `dependencies.runtime` | `Depends` (sibling packages as `(= ${binary:Version})`) |
| `meson/configure`, `cmake/configure`, `autoconf/configure` options | `dh --buildsystem=...` and `override_dh_auto_configure` |
| `runs:` build and install steps | `override_dh_auto_build` and `override_dh_auto_install`, with `${{targets.destdir}}` as `$(DESTDIR)` |
| Files in `packages/NAME/` used by a step | Copied to `debian/`, paths rewritten |
| A first step that only removes files | `Files-Excluded` in `debian/copyright` |
| `uses: patch` | `debian/patches/` and `series` |
| `copyright` (SPDX) | `debian/copyright` (DEP-5), with license texts or `/usr/share/common-licenses` references |
| `update.github`, or a versioned `fetch` URL | `debian/watch` (version 4) |
| GitHub upstream | `debian/upstream/metadata` |
| `test:` steps with `runs:` | `debian/tests/control` and one script per test |
| `split/dev`, `split/manpages`, subpackage `mv` paths | `debian/*.install` |

Not converted, and reported:

- Steps with shell control flow (`if`, `for`, functions) or melange variables
  other than the package version and `targets`: they need a manual port to
  `debian/rules`.
- `-lang` subpackages (translations stay in the main package) and `-dbg`
  subpackages (Debian builds `-dbgsym` packages automatically).
- melange test pipelines (`uses: test/...`).
- Rust and Go builds: Debian builds against packaged crates and modules
  (`dh-cargo`, `dh-golang`), not against `Cargo.lock` or vendored modules.

## Name mapping

Wolfi names are mapped in this order:

1. Dropped: tools that are implicit in a Debian build (`build-base`, `busybox`).
2. A table of known names (`ninja` → `ninja-build`, `glib-dev` →
   `libglib2.0-dev`, …), plus the reverse of the `debian-to-melange` table.
3. Rules: `py3-X` → `python3-X`, `perl-X` → `libX-perl`, `openjdk-N` →
   `openjdk-N-jdk`.
4. `X-dev` → `libX-dev` and unchanged names. These are guesses; they are
   reported, or checked against Debian with `--check-debian`.

## Tests

```bash
python3 -m unittest discover -s tools/melange-to-debian -v
```

The tests convert a sample recipe and every recipe in `packages/`.
