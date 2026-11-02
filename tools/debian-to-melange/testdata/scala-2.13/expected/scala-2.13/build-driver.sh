#!/bin/sh
# No-sbt staged Scala 2.13 build: compiles each module straight with a STARR
# scalac (Scala first, then javac for the Java sources), copies the non-source
# resources and assembles the jars.
#
# Usage: build-driver.sh SRC STARR ASM JLINE3 OUT VERSION
set -e
SRC="$1"; STARR="$2"; ASM="$3"; JLINE3="$4"; OUT="$5"; VERSION="$6"
mkdir -p "$OUT"; OUT=$(cd "$OUT" && pwd)
SLIB="$STARR/lib/scala-library.jar"
SCP="$SLIB:$STARR/lib/scala-reflect.jar:$STARR/lib/scala-compiler.jar"
# $ASM on the run classpath: upstream's STARR shades ASM into
# scala-compiler.jar, Debian's does not.
scalac() { java -Xss16m -Xmx4g -cp "$SCP:$ASM" scala.tools.nsc.Main -nowarn "$@"; }

L="$OUT/library"; R="$OUT/reflect"; C="$OUT/compiler"; I="$OUT/interactive"
RE="$OUT/repl"; RF="$OUT/repl-frontend"; SD="$OUT/scaladoc"; SP="$OUT/scalap"
mkdir -p "$L" "$R" "$C" "$I" "$RE" "$RF" "$SD" "$SP" "$OUT/jars"

# layer NAME SRCDIR OUTDIR BOOTCP CP
layer() {
  n="$1"; src="$SRC/src/$2"; od="$3"; bcp="$4"; cp="$5"
  sc=$(find "$src" -name '*.scala')
  jv=$(find "$src" -name '*.java')
  echo "[$n]"
  scalac -bootclasspath "$bcp" -d "$od" -classpath "$cp" $sc $jv
  [ -n "$jv" ] && javac -nowarn --release 8 -d "$od" -cp "$od:$cp" $jv
  (cd "$src" && find . -type f ! -name '*.scala' ! -name '*.java' -print0 \
     | xargs -0 -r cp --parents -t "$od/")
}

layer library       library       "$L"  "$SLIB" "$L"
layer reflect       reflect       "$R"  "$L"    "$L:$R"
layer compiler      compiler      "$C"  "$L"    "$L:$R:$ASM:$C"
layer interactive   interactive   "$I"  "$L"    "$L:$R:$C:$ASM:$I"
layer repl          repl          "$RE" "$L"    "$L:$R:$C:$I:$ASM:$RE"
layer repl-frontend repl-frontend "$RF" "$L"    "$L:$R:$C:$I:$RE:$ASM:$JLINE3:$RF"
layer scaladoc      scaladoc      "$SD" "$L"    "$L:$R:$C:$I:$ASM:$SD"
layer scalap        scalap        "$SP" "$L"    "$L:$R:$C:$SP"

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

echo "DONE v$VERSION : lib=$(find "$L" -name '*.class'|wc -l) reflect=$(find "$R" -name '*.class'|wc -l) compiler=$(find "$C" -name '*.class'|wc -l) interactive=$(find "$I" -name '*.class'|wc -l) repl=$(find "$RE" -name '*.class'|wc -l) repl-frontend=$(find "$RF" -name '*.class'|wc -l) scaladoc=$(find "$SD" -name '*.class'|wc -l) scalap=$(find "$SP" -name '*.class'|wc -l)"
