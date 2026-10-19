#!/bin/sh
if [ -f _build/test/utftrip.byte ]; then install -D --mode 755 _build/test/utftrip.byte debian/tmp/usr/bin/utftrip; fi
install -D --mode 644 _build/CHANGES.md debian/tmp/usr/doc/uutf/CHANGES.md
install -D --mode 644 _build/LICENSE.md debian/tmp/usr/doc/uutf/LICENSE.md
install -D --mode 644 _build/README.md debian/tmp/usr/doc/uutf/README.md
install -D --mode 644 _build/doc/index.mld debian/tmp/usr/doc/uutf/odoc-pages/index.mld
install -D --mode 644 _build/opam debian/tmp$OCAML_STDLIB_DIR/uutf/opam
install -D --mode 644 _build/pkg/META debian/tmp$OCAML_STDLIB_DIR/uutf/META
install -D --mode 644 _build/src/uutf.cma debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.cma
install -D --mode 644 _build/src/uutf.cmi debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.cmi
if [ -f _build/src/uutf.cmt ]; then install --mode 644 _build/src/uutf.cmt debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.cmt; fi
if [ -f _build/src/uutf.cmti ]; then install --mode 644 _build/src/uutf.cmti debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.cmti; fi
install -D --mode 644 _build/src/uutf.ml debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.ml
install -D --mode 644 _build/src/uutf.mli debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.mli
