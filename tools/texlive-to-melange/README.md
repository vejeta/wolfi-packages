# texlive-to-melange

Generate the `texmf-dist` [melange](https://github.com/chainguard-dev/melange)
recipe from a TeX Live release.

TeX Live describes itself in `texlive.tlpdb`: every package with its run,
source and documentation files, and every collection with the packages and
other collections it depends on. Alpine's texmf-dist APKBUILD splits the
texmf tarball by collection at build time with shell functions; a melange
recipe is static, so this writes the split out:

- `texmf-dist`: collection-basic, the Perl modules of tlmgr and updmap, and
  the hyphenation configuration (assembled from the `lang.d` files of the
  collections installed, by a trigger)
- `texmf-dist-<collection>` and `texmf-dist-<collection>-doc` for each other
  collection, depending on the collections the tlpdb says it needs
- `texmf-dist-lang`, `texmf-dist-most` and `texmf-dist-full`, as in Alpine

The TeX programs are in the `texlive` recipe, converted from Alpine with
`alpine-to-melange --source-url` to build the same release.

Standard library only (Python ≥ 3.9).

## Usage

```bash
# texlive.tlpdb is in the release's extra tarball (tlpkg/texlive.tlpdb)
tools/texlive-to-melange/texlive-to-melange.py --release 20260301 \
  --tlpdb texlive.tlpdb \
  --texmf-sha512 <sha512 of texlive-20260301-texmf.tar.xz> \
  --extra-sha512 <sha512 of texlive-20260301-extra.tar.xz> \
  --out packages/texmf-dist.yaml
```

The tarballs come from TeX Live's historic archive, which keeps every
release. The files next to the recipe (`packages/texmf-dist/`: Alpine's
patches and the hyphenation preamble, epilog and per-language files) are
not generated.

## Tests

```bash
python3 -m unittest discover -s tools/texlive-to-melange -v
```
