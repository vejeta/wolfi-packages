#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Juan Manuel Méndez Rey <vejeta@gmail.com>
#
# Scala 2.13 build without sbt, ported from the Debian scala-2.13 package:
# each module is compiled with a STARR scalac (Scala sources, then javac for
# the Java sources), its resources are copied and the jars are assembled.
#
# Usage: build-driver.sh SRC STARR DEPS OUT VERSION WEBJARS
#   STARR    directory with lib/scala-{library,reflect,compiler}.jar
#   DEPS     colon-separated scala-asm, jline and java-diff-utils jars
#   WEBJARS  directory with the files scaladoc loads from the root of its
#            classpath (jquery.min.js); sbt extracts them from webjars
set -e
SRC="$1"; STARR="$2"; DEPS="$3"; OUT="$4"; VERSION="$5"; WEBJARS="$6"
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
SLIB="$STARR/lib/scala-library.jar"
SCP="$SLIB:$STARR/lib/scala-reflect.jar:$STARR/lib/scala-compiler.jar"
scalac() { java -Xss16m -Xmx4g -cp "$SCP:$DEPS" scala.tools.nsc.Main -nowarn "$@"; }

L="$OUT/library"; R="$OUT/reflect"; C="$OUT/compiler"; I="$OUT/interactive"
RE="$OUT/repl"; RF="$OUT/repl-frontend"; SD="$OUT/scaladoc"; SP="$OUT/scalap"
mkdir -p "$L" "$R" "$C" "$I" "$RE" "$RF" "$SD" "$SP" "$OUT/jars"

# layer NAME SRCDIR OUTDIR BOOTCP CP
layer() {
  n="$1"; src="$SRC/src/$2"; od="$3"; bcp="$4"; cp="$5"
  # Sorted: scalac can fail with a CyclicReference in scaladoc when the
  # sources come in another order, and find's order depends on the file system.
  sc=$(find "$src" -name '*.scala' | LC_ALL=C sort)
  jv=$(find "$src" -name '*.java' | LC_ALL=C sort)
  echo "[$n]"
  scalac -bootclasspath "$bcp" -d "$od" -classpath "$cp" $sc $jv
  [ -n "$jv" ] && javac -nowarn --release 8 -d "$od" -cp "$od:$cp" $jv
  (cd "$src" && find . -type f ! -name '*.scala' ! -name '*.java' -print0 \
     | xargs -0 -r cp --parents -t "$od/")
}

layer library       library       "$L"  "$SLIB" "$L"
layer reflect       reflect       "$R"  "$L"    "$L:$R"
layer compiler      compiler      "$C"  "$L"    "$L:$R:$DEPS:$C"
layer interactive   interactive   "$I"  "$L"    "$L:$R:$C:$DEPS:$I"
layer repl          repl          "$RE" "$L"    "$L:$R:$C:$I:$DEPS:$RE"
layer repl-frontend repl-frontend "$RF" "$L"    "$L:$R:$C:$I:$RE:$DEPS:$RF"
layer scaladoc      scaladoc      "$SD" "$L"    "$L:$R:$C:$I:$DEPS:$SD"
layer scalap        scalap        "$SP" "$L"    "$L:$R:$C:$SP"
cp "$WEBJARS"/* "$SD/"

COPY="Copyright 2002-2025, LAMP/EPFL and Lightbend, Inc. dba Akka"
props() {
  printf 'version.number=%s\nmaven.version.number=%s\nosgi.version.number=%s\ncopyright.string=%s\n' \
    "$VERSION" "$VERSION" "$VERSION" "$COPY" > "$1"
}
props "$L/library.properties"
props "$R/reflect.properties"
props "$C/compiler.properties"
props "$SP/scalap.properties"

J="$OUT/jars"
( cd "$L" && jar cf "$J/scala-library.jar" . )
( cd "$R" && jar cf "$J/scala-reflect.jar" . )
mkdir -p "$OUT/compiler-all"
for d in "$C" "$I" "$RE" "$RF" "$SD"; do cp -a "$d/." "$OUT/compiler-all/"; done
( cd "$OUT/compiler-all" && jar cf "$J/scala-compiler.jar" . )
( cd "$SP" && jar cf "$J/scalap.jar" . )
echo "built Scala $VERSION in $J"
