import io

import pymupdf
import pytest
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from app.services.pdf_service import PDFService


def _font_with_alternate_digit() -> bytes:
    glyph_order = [".notdef", "one", "one.alt"]
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap({ord("1"): "one"})
    glyphs = {}
    for name in glyph_order:
        pen = TTGlyphPen(None)
        pen.moveTo((100, 0))
        pen.lineTo((100, 700))
        pen.lineTo((500, 700))
        pen.lineTo((500, 0))
        pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name: (600, 100) for name in glyph_order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({"familyName": "AltDigit", "styleName": "Regular"})
    builder.setupOS2()
    builder.setupPost()
    addOpenTypeFeaturesFromString(builder.font, "feature locl { sub one by one.alt; } locl;")
    output = io.BytesIO()
    builder.save(output)
    return output.getvalue()


def _pdf_drawing_one_and_its_alternate(alternate_target: str) -> bytes:
    font = _font_with_alternate_digit()
    to_unicode = (
        "/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
        "1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
        f"2 beginbfchar\n<0001> <0031>\n<0002> <{alternate_target}>\nendbfchar\n"
        "endcmap CMapName currentdict /CMap defineresource pop end end"
    ).encode("ascii")
    content = b"BT /F1 24 Tf 10 40 Td <00010002> Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        content,
        b"<< /Type /Font /Subtype /Type0 /BaseFont /AltDigit /Encoding /Identity-H /DescendantFonts [6 0 R] /ToUnicode 9 0 R >>",
        b"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /AltDigit /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /CIDToGIDMap /Identity /FontDescriptor 7 0 R >>",
        b"<< /Type /FontDescriptor /FontName /AltDigit /Flags 4 /FontBBox [0 -200 1000 800] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 /FontFile2 8 0 R >>",
        font,
        to_unicode,
    ]
    streams = {4, 8, 9}
    pdf = bytearray(b"%PDF-1.7\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        if number in streams:
            pdf += f"{number} 0 obj\n<< /Length {len(body)} >>\nstream\n".encode() + body + b"\nendstream\nendobj\n"
        else:
            pdf += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    pdf += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(pdf)


@pytest.mark.parametrize("alternate_target, expected", [("FFFD", "11"), ("0041", "1A")])
def test_alternate_glyphs_without_unicode_are_mapped_back_to_their_source_character(alternate_target, expected):
    pdf = _pdf_drawing_one_and_its_alternate(alternate_target)
    assert pymupdf.open("pdf", pdf)[0].get_text().strip() != "11"

    doc = pymupdf.open("pdf", pdf)
    PDFService._map_unmapped_alternate_glyphs(doc)

    assert doc[0].get_text().strip() == expected
