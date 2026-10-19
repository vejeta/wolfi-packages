#!/usr/bin/python3
"""Build FontAwesome font files (TTF, WOFF2) from SVG sources."""

import os
import yaml
from fontTools.svgLib.path import SVGPath
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
import xml.etree.ElementTree as ET

version = 7
VERSIONS = {7: '7.3.0'}

UPM = 1000
ASCENT = 800
DESCENT = -200

STYLES = {
    'solid': {'weight': 900, 'filename_weight': '900'},
    'regular': {'weight': 400, 'filename_weight': '400'},
    'brands': {'weight': 400, 'filename_weight': '400'},
}


def build_font(icons, style, svgs_dir, output_dir):
    config = STYLES[style]
    glyphNames = ['.notdef']
    cmap = {}
    glyphDrawings = {}

    for name, data in icons.items():
        if style not in data.get('styles', []):
            continue
        svg_path = os.path.join(svgs_dir, style, f'{name}.svg')
        if not os.path.exists(svg_path):
            continue

        gname = name.replace('-', '_')
        codepoint = int(data['unicode'], 16)
        glyphNames.append(gname)
        cmap[codepoint] = gname

        tree = ET.parse(svg_path)
        root = tree.getroot()
        vb = root.get('viewBox', '0 0 512 512').split()
        svg_w, svg_h = float(vb[2]), float(vb[3])
        scale = UPM / svg_h

        svg = SVGPath(svg_path)
        rec = RecordingPen()
        svg.draw(rec)
        glyphDrawings[gname] = (rec, scale, svg_w)

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyphNames)
    fb.setupCharacterMap(cmap)

    glyphs_dict = {}
    metrics = {}

    for gname in glyphNames:
        ttpen = TTGlyphPen(None)
        if gname == '.notdef':
            glyphs_dict[gname] = ttpen.glyph()
            metrics[gname] = (UPM, 0)
            continue

        rec, scale, svg_w = glyphDrawings[gname]
        tpen = TransformPen(
            Cu2QuPen(ttpen, max_err=1.0, reverse_direction=True),
            (scale, 0, 0, -scale, 0, ASCENT)
        )
        rec.replay(tpen)
        glyphs_dict[gname] = ttpen.glyph()
        metrics[gname] = (int(svg_w * scale), 0)

    fb.setupGlyf(glyphs_dict)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    if style == "brands":
        base_name = 'Font Awesome %d Brands' % version
        style_name = 'Regular'
    else:
        base_name = 'Font Awesome %d Free' % version
        style_name = style.capitalize()
    family_name = '%s %s' % (base_name, style_name)
    ps_name = base_name.replace(' ', '') + "-" + style_name
    fb.setupNameTable({
        'familyName': dict(en=family_name),
        'styleName': dict(en=style_name),
        'fullName': family_name,
        'uniqueFontIdentifier': 'FontAwesome DFSG: %s' % family_name,
        'psName': ps_name,
        'version': 'Debian build of Font Awesome version %s' % VERSIONS[version],
    })
    fb.setupOS2(fsType=0x0000, sTypoAscender=ASCENT, sTypoDescender=DESCENT)
    fb.setupPost()

    os.makedirs(output_dir, exist_ok=True)

    basename = f'fa-{style}-{config["filename_weight"]}'

    ttf_path = os.path.join(output_dir, f'{basename}.ttf')
    fb.font.save(ttf_path)
    print(f'  {ttf_path}: {len(glyphNames) - 1} glyphs')

    fb.font.flavor = 'woff2'
    woff2_path = os.path.join(output_dir, f'{basename}.woff2')
    fb.font.save(woff2_path)
    print(f'  {woff2_path}')


def build_v4compatibility(icons, svgs_dir, output_dir):
    """Build the v4compatibility font.

    This font maps old v4 unicode codepoints to the current icon glyphs,
    so that pages using FA v4 codepoints still render correctly.
    """
    glyphNames = ['.notdef']
    cmap = {}
    glyphDrawings = {}

    for name, data in icons.items():
        aliases = data.get('aliases', {})
        composite = aliases.get('unicodes', {}).get('composite', [])
        if not composite:
            continue

        # Only include old v4 PUA codepoints (f000-f8ff) that differ
        # from the current icon codepoint
        current_cp = int(data['unicode'], 16)
        v4_codepoints = []
        for cp_hex in composite:
            cp = int(cp_hex, 16)
            if 0xf000 <= cp <= 0xf8ff and cp != current_cp:
                v4_codepoints.append(cp)
        if not v4_codepoints:
            continue

        # Find the SVG in whichever style is available
        svg_path = None
        for style in ('solid', 'regular', 'brands'):
            candidate = os.path.join(svgs_dir, style, f'{name}.svg')
            if os.path.exists(candidate):
                svg_path = candidate
                break
        if not svg_path:
            continue

        gname = name.replace('-', '_')
        if gname not in glyphNames:
            glyphNames.append(gname)

            tree = ET.parse(svg_path)
            root = tree.getroot()
            vb = root.get('viewBox', '0 0 512 512').split()
            svg_w, svg_h = float(vb[2]), float(vb[3])
            scale = UPM / svg_h

            svg = SVGPath(svg_path)
            rec = RecordingPen()
            svg.draw(rec)
            glyphDrawings[gname] = (rec, scale, svg_w)

        for cp in v4_codepoints:
            cmap[cp] = gname

    fb = FontBuilder(UPM, isTTF=True)
    fb.setupGlyphOrder(glyphNames)
    fb.setupCharacterMap(cmap)

    glyphs_dict = {}
    metrics = {}

    for gname in glyphNames:
        ttpen = TTGlyphPen(None)
        if gname == '.notdef':
            glyphs_dict[gname] = ttpen.glyph()
            metrics[gname] = (UPM, 0)
            continue

        rec, scale, svg_w = glyphDrawings[gname]
        tpen = TransformPen(
            Cu2QuPen(ttpen, max_err=1.0, reverse_direction=True),
            (scale, 0, 0, -scale, 0, ASCENT)
        )
        rec.replay(tpen)
        glyphs_dict[gname] = ttpen.glyph()
        metrics[gname] = (int(svg_w * scale), 0)

    fb.setupGlyf(glyphs_dict)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT)
    base_name = 'Font Awesome v4 Compatibility'
    style_name = 'Regular'
    family_name = '%s %s' % (base_name, style_name)
    ps_name = family_name.replace(' ', '') + "-" + style_name
    fb.setupNameTable({
        'familyName': dict(en=family_name),
        'styleName': dict(en=style_name),
        'fullName': family_name,
        'uniqueFontIdentifier': 'FontAwesome DFSG: %s' % family_name,
        'psName': ps_name,
        'version': 'Debian build of Font Awesome version %s' % VERSIONS[version],
    })
    fb.setupOS2(fsType=0x0000, sTypoAscender=ASCENT, sTypoDescender=DESCENT)
    fb.setupPost()

    os.makedirs(output_dir, exist_ok=True)

    ttf_path = os.path.join(output_dir, 'fa-v4compatibility.ttf')
    fb.font.save(ttf_path)
    print(f'  {ttf_path}: {len(glyphNames) - 1} glyphs')

    fb.font.flavor = 'woff2'
    woff2_path = os.path.join(output_dir, 'fa-v4compatibility.woff2')
    fb.font.save(woff2_path)
    print(f'  {woff2_path}')


def main():
    with open('metadata/icons.yml') as f:
        icons = yaml.safe_load(f)

    print('Building fonts from SVG sources...')
    for style in STYLES:
        print(f'Building {style}...')
        build_font(icons, style, 'svgs', 'webfonts')

    print('Building v4compatibility...')
    build_v4compatibility(icons, 'svgs', 'webfonts')

    print('Done.')


if __name__ == '__main__':
    main()
