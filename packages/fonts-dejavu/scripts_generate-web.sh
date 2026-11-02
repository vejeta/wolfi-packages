#! /bin/sh

TARGET="debian/fonts-dejavu-web/usr/share/fonts"

for f in debian/fonts-dejavu-core/usr/share/fonts/truetype/dejavu/*.ttf debian/fonts-dejavu-extra/usr/share/fonts/truetype/dejavu/*.ttf; do
  [ -e "$f" ] &&
  case $f in
    *DejaVuMathTeXGyre*)
      ;;
    *)
      sfnt2woff "$f"
      woff2_compress "$f"
      ;;
  esac;
done

# woff
mkdir -p "${TARGET}"/woff/dejavu
mv debian/*/usr/share/fonts/truetype/dejavu/*.woff "${TARGET}"/woff/dejavu

# woff2
mkdir -p "${TARGET}"/woff2/dejavu
mv debian/*/usr/share/fonts/truetype/dejavu/*.woff2 "${TARGET}"/woff2/dejavu

# vim:set tw=0 nowrap ts=8 sw=2 sts=2:
