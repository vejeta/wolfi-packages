#!/bin/sh
install -D --mode 644 _build/CHANGES.md debian/tmp/usr/doc/topkg/CHANGES.md
install -D --mode 644 _build/LICENSE.md debian/tmp/usr/doc/topkg/LICENSE.md
install -D --mode 644 _build/README.md debian/tmp/usr/doc/topkg/README.md
install -D --mode 644 _build/doc/index-topkg.mld debian/tmp/usr/doc/topkg/odoc-pages/index.mld
install -D --mode 644 _build/pkg/META debian/tmp$OCAML_STDLIB_DIR/topkg/META
install -D --mode 644 _build/src/topkg.cma debian/tmp$OCAML_STDLIB_DIR/topkg/topkg.cma
install -D --mode 644 _build/src/topkg.cmi debian/tmp$OCAML_STDLIB_DIR/topkg/topkg.cmi
if [ -f _build/src/topkg.cmt ]; then install --mode 644 _build/src/topkg.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg.cmt; fi
if [ -f _build/src/topkg.cmti ]; then install --mode 644 _build/src/topkg.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg.cmti; fi
install -D --mode 644 _build/src/topkg.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg.ml
install -D --mode 644 _build/src/topkg.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg.mli
if [ -f _build/src/topkg_build.cmt ]; then install --mode 644 _build/src/topkg_build.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_build.cmt; fi
if [ -f _build/src/topkg_build.cmti ]; then install --mode 644 _build/src/topkg_build.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_build.cmti; fi
install -D --mode 644 _build/src/topkg_build.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_build.ml
install -D --mode 644 _build/src/topkg_build.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_build.mli
if [ -f _build/src/topkg_cmd.cmt ]; then install --mode 644 _build/src/topkg_cmd.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_cmd.cmt; fi
if [ -f _build/src/topkg_cmd.cmti ]; then install --mode 644 _build/src/topkg_cmd.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_cmd.cmti; fi
install -D --mode 644 _build/src/topkg_cmd.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_cmd.ml
install -D --mode 644 _build/src/topkg_cmd.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_cmd.mli
if [ -f _build/src/topkg_codec.cmt ]; then install --mode 644 _build/src/topkg_codec.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_codec.cmt; fi
if [ -f _build/src/topkg_codec.cmti ]; then install --mode 644 _build/src/topkg_codec.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_codec.cmti; fi
install -D --mode 644 _build/src/topkg_codec.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_codec.ml
install -D --mode 644 _build/src/topkg_codec.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_codec.mli
if [ -f _build/src/topkg_conf.cmt ]; then install --mode 644 _build/src/topkg_conf.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_conf.cmt; fi
if [ -f _build/src/topkg_conf.cmti ]; then install --mode 644 _build/src/topkg_conf.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_conf.cmti; fi
install -D --mode 644 _build/src/topkg_conf.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_conf.ml
install -D --mode 644 _build/src/topkg_conf.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_conf.mli
if [ -f _build/src/topkg_distrib.cmt ]; then install --mode 644 _build/src/topkg_distrib.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_distrib.cmt; fi
if [ -f _build/src/topkg_distrib.cmti ]; then install --mode 644 _build/src/topkg_distrib.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_distrib.cmti; fi
install -D --mode 644 _build/src/topkg_distrib.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_distrib.ml
install -D --mode 644 _build/src/topkg_distrib.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_distrib.mli
if [ -f _build/src/topkg_fexts.cmt ]; then install --mode 644 _build/src/topkg_fexts.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_fexts.cmt; fi
if [ -f _build/src/topkg_fexts.cmti ]; then install --mode 644 _build/src/topkg_fexts.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_fexts.cmti; fi
install -D --mode 644 _build/src/topkg_fexts.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_fexts.ml
install -D --mode 644 _build/src/topkg_fexts.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_fexts.mli
if [ -f _build/src/topkg_fpath.cmt ]; then install --mode 644 _build/src/topkg_fpath.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_fpath.cmt; fi
if [ -f _build/src/topkg_fpath.cmti ]; then install --mode 644 _build/src/topkg_fpath.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_fpath.cmti; fi
install -D --mode 644 _build/src/topkg_fpath.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_fpath.ml
install -D --mode 644 _build/src/topkg_fpath.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_fpath.mli
if [ -f _build/src/topkg_install.cmt ]; then install --mode 644 _build/src/topkg_install.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_install.cmt; fi
if [ -f _build/src/topkg_install.cmti ]; then install --mode 644 _build/src/topkg_install.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_install.cmti; fi
install -D --mode 644 _build/src/topkg_install.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_install.ml
install -D --mode 644 _build/src/topkg_install.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_install.mli
if [ -f _build/src/topkg_ipc.cmt ]; then install --mode 644 _build/src/topkg_ipc.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_ipc.cmt; fi
if [ -f _build/src/topkg_ipc.cmti ]; then install --mode 644 _build/src/topkg_ipc.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_ipc.cmti; fi
install -D --mode 644 _build/src/topkg_ipc.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_ipc.ml
install -D --mode 644 _build/src/topkg_ipc.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_ipc.mli
if [ -f _build/src/topkg_log.cmt ]; then install --mode 644 _build/src/topkg_log.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_log.cmt; fi
if [ -f _build/src/topkg_log.cmti ]; then install --mode 644 _build/src/topkg_log.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_log.cmti; fi
install -D --mode 644 _build/src/topkg_log.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_log.ml
install -D --mode 644 _build/src/topkg_log.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_log.mli
if [ -f _build/src/topkg_main.cmt ]; then install --mode 644 _build/src/topkg_main.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_main.cmt; fi
if [ -f _build/src/topkg_main.cmti ]; then install --mode 644 _build/src/topkg_main.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_main.cmti; fi
install -D --mode 644 _build/src/topkg_main.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_main.ml
install -D --mode 644 _build/src/topkg_main.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_main.mli
if [ -f _build/src/topkg_opam.cmt ]; then install --mode 644 _build/src/topkg_opam.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_opam.cmt; fi
if [ -f _build/src/topkg_opam.cmti ]; then install --mode 644 _build/src/topkg_opam.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_opam.cmti; fi
install -D --mode 644 _build/src/topkg_opam.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_opam.ml
install -D --mode 644 _build/src/topkg_opam.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_opam.mli
if [ -f _build/src/topkg_os.cmt ]; then install --mode 644 _build/src/topkg_os.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_os.cmt; fi
if [ -f _build/src/topkg_os.cmti ]; then install --mode 644 _build/src/topkg_os.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_os.cmti; fi
install -D --mode 644 _build/src/topkg_os.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_os.ml
install -D --mode 644 _build/src/topkg_os.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_os.mli
if [ -f _build/src/topkg_pkg.cmt ]; then install --mode 644 _build/src/topkg_pkg.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_pkg.cmt; fi
if [ -f _build/src/topkg_pkg.cmti ]; then install --mode 644 _build/src/topkg_pkg.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_pkg.cmti; fi
install -D --mode 644 _build/src/topkg_pkg.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_pkg.ml
install -D --mode 644 _build/src/topkg_pkg.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_pkg.mli
if [ -f _build/src/topkg_publish.cmt ]; then install --mode 644 _build/src/topkg_publish.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_publish.cmt; fi
if [ -f _build/src/topkg_publish.cmti ]; then install --mode 644 _build/src/topkg_publish.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_publish.cmti; fi
install -D --mode 644 _build/src/topkg_publish.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_publish.ml
install -D --mode 644 _build/src/topkg_publish.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_publish.mli
if [ -f _build/src/topkg_result.cmt ]; then install --mode 644 _build/src/topkg_result.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_result.cmt; fi
if [ -f _build/src/topkg_result.cmti ]; then install --mode 644 _build/src/topkg_result.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_result.cmti; fi
install -D --mode 644 _build/src/topkg_result.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_result.ml
install -D --mode 644 _build/src/topkg_result.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_result.mli
if [ -f _build/src/topkg_string.cmt ]; then install --mode 644 _build/src/topkg_string.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_string.cmt; fi
if [ -f _build/src/topkg_string.cmti ]; then install --mode 644 _build/src/topkg_string.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_string.cmti; fi
install -D --mode 644 _build/src/topkg_string.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_string.ml
install -D --mode 644 _build/src/topkg_string.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_string.mli
if [ -f _build/src/topkg_test.cmt ]; then install --mode 644 _build/src/topkg_test.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_test.cmt; fi
if [ -f _build/src/topkg_test.cmti ]; then install --mode 644 _build/src/topkg_test.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_test.cmti; fi
install -D --mode 644 _build/src/topkg_test.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_test.ml
install -D --mode 644 _build/src/topkg_test.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_test.mli
if [ -f _build/src/topkg_vcs.cmt ]; then install --mode 644 _build/src/topkg_vcs.cmt debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_vcs.cmt; fi
if [ -f _build/src/topkg_vcs.cmti ]; then install --mode 644 _build/src/topkg_vcs.cmti debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_vcs.cmti; fi
install -D --mode 644 _build/src/topkg_vcs.ml debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_vcs.ml
install -D --mode 644 _build/src/topkg_vcs.mli debian/tmp$OCAML_STDLIB_DIR/topkg/topkg_vcs.mli
install -D --mode 644 _build/topkg.opam debian/tmp$OCAML_STDLIB_DIR/topkg/opam
