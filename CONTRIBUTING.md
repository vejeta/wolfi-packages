# Contributing to Wolfi Community Packages

Thanks for helping. This guide covers adding a package, updating one, and how
reviews work.

## 1. Before you start: is it already packaged?

Packaging is time-consuming. First check that nobody else already did it:

```bash
python3 tools/pkg-check/pkg-check.py --target wolfi  --package <name>
python3 tools/pkg-check/pkg-check.py --target alpine --package <name>
python3 tools/pkg-check/pkg-check.py --target debian --package <name>
```

- **Exists in Wolfi** → it does not belong here; use or improve the official package.
- **Exists in Alpine** → the `APKBUILD` is a good starting point for your recipe.
- **Exists in Debian** → `debian/rules` and `debian/patches` are useful references.

## 2. Repository layout

The layout mirrors [wolfi-dev/os](https://github.com/wolfi-dev/os) so recipes
can move between the two with no changes:

```
wolfi-packages/
├── packages/
│   ├── <name>.yaml          # melange recipe (one per package, flat)
│   └── <name>/              # optional: patches, wrappers, config files
│       └── 001-description.patch
├── pipelines/               # shared melange pipelines (from wolfi-dev/os)
├── scripts/                 # build, sign and publish helpers
├── tools/                   # contributor tooling (pkg-check, converters)
├── docs/                    # guides and research notes
├── keys/                    # public signing key
└── .github/workflows/       # CI: build, sign & publish, cleanup
```

CI discovers packages automatically from `packages/*.yaml`; no registration is
needed.

## 3. Writing a recipe

Minimum expectations:

- `package.name` equals the file name (`packages/foo.yaml` → `name: foo`).
- `epoch: 0` for a new version; bump `epoch` for rebuilds of the same version.
- `copyright[].license` uses SPDX identifiers.
- Sources are fetched with a pinned checksum (`expected-sha256`) or a pinned
  git commit (`expected-commit`).
- Patches live in `packages/<name>/`, are numbered (`001-`, `002-`…) and
  start with a short header explaining why they are needed and whether they
  were sent upstream.
- A `-dev` subpackage for libraries (`split/dev`).
- A `test:` section that exercises the package (at minimum `--version`/`--help`
  for binaries, `pkgconf`/linking for libraries).
- An `update:` section (`release-monitor` or `git`) so new versions are detected.

Repositories: depend on official Wolfi first, then on this repository:

```yaml
environment:
  contents:
    repositories:
      - https://packages.wolfi.dev/os
```

Dependencies built in this repository are resolved by CI from its own build
cache and from the published SourceForge repository.

## 4. Building locally

Using the helper script (runs melange in the official container):

```bash
./scripts/build-with-melange.sh packages/<name>.yaml x86_64 ./packages-out
```

Or with melange directly:

```bash
melange keygen local-melange.rsa
melange build packages/<name>.yaml \
  --arch x86_64 \
  --signing-key local-melange.rsa \
  --repository-append ./packages-out \
  --keyring-append local-melange.rsa.pub \
  --pipeline-dir ./pipelines \
  --out-dir ./packages-out
melange test packages/<name>.yaml --arch x86_64 \
  --repository-append ./packages-out --keyring-append local-melange.rsa.pub
```

If your package depends on others from this repository, build those first (or
add `https://downloads.sourceforge.net/project/wolfi` with
`--repository-append` and its key with `--keyring-append`).

## 5. Pull request checklist

Copy this into your PR description:

```markdown
- [ ] Package does not exist in official wolfi-dev/os
- [ ] License is OSI-approved (or explicitly redistributable and documented)
- [ ] Test pipeline included
- [ ] Builds locally with melange (arch: x86_64 / aarch64)
- [ ] `update:` section configured
- [ ] Patches documented (purpose + upstream status)
```

One package per PR is preferred; a new package plus its new dependencies in
the same PR is fine.

## 6. Review process

- Reviews are currently done by the maintainer, [@vejeta](https://github.com/vejeta).
- CI must pass (`build-packages.yml`) for the changed packages.
- After merge, packages are signed and published to SourceForge by the
  maintainer (`sign-and-publish.yml`).
- Contributors who maintain several packages can be invited as reviewers.

## 7. Updating an existing package

1. Bump `version`, reset `epoch: 0`, update the checksum.
2. Rebase or drop patches that upstream has merged.
3. Build and test locally, then open a PR titled `<name>: <old> -> <new>`.

## 8. When a package lands in official Wolfi

It is removed from this repository in a follow-up PR, and the README table is
updated. Users are pointed to the official package.

## Commit conventions

- `<package>: <short summary>` for package changes (e.g. `mpv: 0.40.0 -> 0.41.0`).
- `ci: ...`, `docs: ...`, `tools: ...` for everything else.

## License

By contributing you agree that your recipes, patches and scripts are licensed
under the MIT License. Packaged software keeps its upstream license.
