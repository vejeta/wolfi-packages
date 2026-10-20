#!/bin/sh
install -D --mode 755 _build/test/utftrip.native debian/tmp/usr/bin/utftrip
install -D --mode 644 _build/src/uutf.a debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.a
install -D --mode 644 _build/src/uutf.cmx debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.cmx
install -D --mode 644 _build/src/uutf.cmxa debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.cmxa
install -D --mode 644 _build/src/uutf.cmxs debian/tmp$OCAML_STDLIB_DIR/uutf/uutf.cmxs
