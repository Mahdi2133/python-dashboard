# -*- coding: utf-8 -*-
"""A small Word (.docx) writer: right-to-left paragraphs, tables and pictures.

Pure Python — zipfile and XML strings — so the report export works on an
offline workshop PC with nothing beyond what the app already ships. It knows
only what a report needs: headings, paragraphs, a key/value block, data
tables with a repeated header row, PNG pictures, page breaks, and a header
and footer with the page number.
"""
from __future__ import annotations

import io
import struct
import zipfile
from xml.sax.saxutils import escape

EMU_PER_CM = 360000
A4_W, A4_H = 11906, 16838          # twentieths of a point
MARGIN = 1000

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')


def _t(text) -> str:
    text = "" if text is None else str(text)
    return f'<w:t xml:space="preserve">{escape(text)}</w:t>'


def _png_size(data: bytes):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    w, h = struct.unpack(">II", data[16:24])
    return w, h


class DocxWriter:
    def __init__(self, title="گزارش", landscape=False, font="Tahoma"):
        self.title = title
        self.landscape = landscape
        self.font = font
        self.body = []
        self.images = []            # (rid, name, bytes)
        self._pic = 0
        self.header_text = title
        self.footer_text = ""

    # ── geometry ──
    @property
    def page_w(self):
        return A4_H if self.landscape else A4_W

    @property
    def page_h(self):
        return A4_W if self.landscape else A4_H

    @property
    def text_w(self):
        return self.page_w - 2 * MARGIN

    # ── runs and paragraphs ──
    def _run(self, text, bold=False, size=None, color=None, italic=False):
        rpr = [f'<w:rFonts w:ascii="{self.font}" w:hAnsi="{self.font}" w:cs="{self.font}"/>']
        if bold:
            rpr.append("<w:b/><w:bCs/>")
        if italic:
            rpr.append("<w:i/><w:iCs/>")
        if color:
            rpr.append(f'<w:color w:val="{color}"/>')
        if size:
            rpr.append(f'<w:sz w:val="{int(size * 2)}"/><w:szCs w:val="{int(size * 2)}"/>')
        rpr.append("<w:rtl/>")
        return f'<w:r><w:rPr>{"".join(rpr)}</w:rPr>{_t(text)}</w:r>'

    def _para(self, runs, style=None, align=None, space_after=None, keep_next=False,
              shading=None, border_bottom=None):
        ppr = []
        if style:
            ppr.append(f'<w:pStyle w:val="{style}"/>')
        if keep_next:
            ppr.append("<w:keepNext/>")
        if border_bottom:
            ppr.append(f'<w:pBdr><w:bottom w:val="single" w:sz="8" w:space="4" '
                       f'w:color="{border_bottom}"/></w:pBdr>')
        if shading:
            ppr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>')
        ppr.append("<w:bidi/>")
        if space_after is not None:
            ppr.append(f'<w:spacing w:after="{int(space_after)}"/>')
        if align:
            ppr.append(f'<w:jc w:val="{align}"/>')
        return f'<w:p><w:pPr>{"".join(ppr)}</w:pPr>{"".join(runs)}</w:p>'

    def heading(self, text, level=1):
        self.body.append(self._para([self._run(text)], style=f"Heading{level}", keep_next=True))

    def title_block(self, title, subtitle=None):
        self.body.append(self._para([self._run(title, bold=True, size=22, color="0A3D62")],
                                    align="center", space_after=120, border_bottom="0A3D62"))
        if subtitle:
            self.body.append(self._para([self._run(subtitle, size=11, color="5B6B78")],
                                        align="center", space_after=240))

    def paragraph(self, text, bold=False, size=None, color=None, align=None, italic=False,
                  shading=None):
        self.body.append(self._para([self._run(text, bold, size, color, italic)], align=align,
                                    shading=shading))

    def bullet(self, text):
        self.body.append(self._para([self._run(f"• {text}")], style="ListLine"))

    def rich(self, parts, align=None):
        """parts: [(text, {bold, color, size})]"""
        self.body.append(self._para([self._run(t, **(o or {})) for t, o in parts], align=align))

    def spacer(self, pts=6):
        self.body.append(f'<w:p><w:pPr><w:bidi/><w:spacing w:after="{pts * 20}"/></w:pPr></w:p>')

    def page_break(self):
        self.body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    # ── tables ──
    def table(self, header, rows, widths=None, header_fill="0A3D62", zebra=True,
              row_fills=None, bold_rows=None, font_size=9):
        """header: [str]; rows: [[str]]; widths: relative weights."""
        n = len(header) or (len(rows[0]) if rows else 1)
        weights = widths or [1] * n
        total = float(sum(weights)) or 1.0
        cols = [max(400, int(self.text_w * w / total)) for w in weights]
        border = ('<w:tblBorders>' + "".join(
            f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="C9D3DC"/>'
            for s in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>')
        out = [f'<w:tbl><w:tblPr><w:bidiVisual/><w:tblW w:w="{sum(cols)}" w:type="dxa"/>'
               f'{border}<w:tblLayout w:type="fixed"/>'
               '<w:tblCellMar><w:top w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/>'
               '<w:bottom w:w="40" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar>'
               '</w:tblPr><w:tblGrid>']
        out += [f'<w:gridCol w:w="{c}"/>' for c in cols]
        out.append("</w:tblGrid>")

        def cell(text, width, fill=None, bold=False, color=None):
            shd = f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>' if fill else ""
            return (f'<w:tc><w:tcPr><w:tcW w:w="{width}" w:type="dxa"/>{shd}'
                    '<w:vAlign w:val="center"/></w:tcPr>'
                    + self._para([self._run(text, bold=bold, size=font_size, color=color)],
                                 align="center", space_after=0) + '</w:tc>')

        if header:
            out.append('<w:tr><w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>')
            out += [cell(h, cols[i], header_fill, True, "FFFFFF") for i, h in enumerate(header)]
            out.append("</w:tr>")
        for ri, row in enumerate(rows):
            fill = (row_fills or {}).get(ri) or ("F4F7FA" if zebra and ri % 2 else None)
            bold = ri in (bold_rows or set())
            out.append('<w:tr><w:trPr><w:cantSplit/></w:trPr>')
            for i in range(n):
                val = row[i] if i < len(row) else ""
                cfill = fill
                if isinstance(val, tuple):          # (text, fill)
                    val, cfill = val[0], val[1] or fill
                out.append(cell(val, cols[i], cfill, bold))
            out.append("</w:tr>")
        out.append("</w:tbl>")
        self.body.append("".join(out))
        self.spacer(4)

    def key_values(self, pairs):
        self.table([], [[k, v] for k, v in pairs], widths=[1, 2.4], zebra=True)

    # ── pictures ──
    def image(self, data: bytes, width_cm=None, caption=None):
        size = _png_size(data)
        if not size:
            return False
        self._pic += 1
        rid = f"rIdImg{self._pic}"
        name = f"image{self._pic}.png"
        self.images.append((rid, name, data))
        max_cm = (self.text_w / 1440.0) * 2.54
        w_cm = min(width_cm or max_cm, max_cm)
        cx = int(w_cm * EMU_PER_CM)
        cy = int(cx * size[1] / float(size[0] or 1))
        max_cy = int(((self.page_h - 2 * MARGIN) / 1440.0) * 2.54 * EMU_PER_CM * 0.8)
        if cy > max_cy:
            cx, cy = int(cx * max_cy / cy), max_cy
        pid = self._pic
        drawing = (
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{pid}" name="Picture {pid}"/>'
            '<wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
            '<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:pic><pic:nvPicPr><pic:cNvPr id="{pid}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
            '</a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')
        self.body.append(self._para([drawing], align="center", space_after=60))
        if caption:
            self.body.append(self._para([self._run(caption, size=9, color="5B6B78", italic=True)],
                                        align="center"))
        return True

    # ── package ──
    def _styles(self):
        f = self.font

        def heading(n, size, color):
            return (f'<w:style w:type="paragraph" w:styleId="Heading{n}"><w:name w:val="heading {n}"/>'
                    '<w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
                    f'<w:pPr><w:keepNext/><w:bidi/><w:spacing w:before="240" w:after="120"/>'
                    f'<w:outlineLvl w:val="{n - 1}"/></w:pPr>'
                    f'<w:rPr><w:b/><w:bCs/><w:color w:val="{color}"/><w:sz w:val="{size}"/>'
                    f'<w:szCs w:val="{size}"/><w:rtl/></w:rPr></w:style>')
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:styles {NS}><w:docDefaults><w:rPrDefault><w:rPr>'
                f'<w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:eastAsia="{f}" w:cs="{f}"/>'
                '<w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="en-US" w:bidi="fa-IR"/>'
                '</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:bidi/>'
                '<w:spacing w:after="100" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
                '</w:docDefaults>'
                '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
                '<w:qFormat/><w:pPr><w:bidi/></w:pPr><w:rPr><w:rtl/></w:rPr></w:style>'
                + heading(1, 30, "0A3D62") + heading(2, 25, "1E5F8C") + heading(3, 22, "2E7DAF")
                + '<w:style w:type="paragraph" w:styleId="ListLine"><w:name w:val="List Line"/>'
                '<w:basedOn w:val="Normal"/><w:pPr><w:bidi/><w:spacing w:after="40"/>'
                '</w:pPr></w:style>'
                '<w:style w:type="table" w:default="1" w:styleId="TableNormal">'
                '<w:name w:val="Normal Table"/><w:tblPr><w:tblInd w:w="0" w:type="dxa"/>'
                '<w:tblCellMar><w:top w:w="0" w:type="dxa"/><w:left w:w="108" w:type="dxa"/>'
                '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="108" w:type="dxa"/></w:tblCellMar>'
                '</w:tblPr></w:style></w:styles>')

    def _hf(self, kind, inner):
        tag = "w:hdr" if kind == "header" else "w:ftr"
        return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><{tag} {NS}>{inner}</{tag}>'

    def to_bytes(self) -> bytes:
        orient = ' w:orient="landscape"' if self.landscape else ""
        sect = (f'<w:sectPr><w:headerReference w:type="default" r:id="rIdHeader"/>'
                f'<w:footerReference w:type="default" r:id="rIdFooter"/>'
                f'<w:pgSz w:w="{self.page_w}" w:h="{self.page_h}"{orient}/>'
                f'<w:pgMar w:top="{MARGIN + 200}" w:right="{MARGIN}" w:bottom="{MARGIN + 200}" '
                f'w:left="{MARGIN}" w:header="500" w:footer="500" w:gutter="0"/>'
                '<w:bidi/></w:sectPr>')
        document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                    f'<w:document {NS}><w:body>{"".join(self.body)}{sect}</w:body></w:document>')
        header = self._hf("header", self._para(
            [self._run(self.header_text, size=8, color="5B6B78")], align="center",
            border_bottom="C9D3DC", space_after=0))
        footer_runs = [self._run((self.footer_text + " — ") if self.footer_text else "",
                                 size=8, color="5B6B78"),
                       self._run("صفحه ", size=8, color="5B6B78"),
                       '<w:fldSimple w:instr=" PAGE "><w:r><w:t>1</w:t></w:r></w:fldSimple>',
                       self._run(" از ", size=8, color="5B6B78"),
                       '<w:fldSimple w:instr=" NUMPAGES "><w:r><w:t>1</w:t></w:r></w:fldSimple>']
        footer = self._hf("footer", self._para(footer_runs, align="center", space_after=0))
        rels = ['<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
                '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>',
                '<Relationship Id="rIdHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>',
                '<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>']
        rels += [f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>'
                 for rid, name, _ in self.images]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                       '<Default Extension="xml" ContentType="application/xml"/>'
                       '<Default Extension="png" ContentType="image/png"/>'
                       '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                       '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
                       '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
                       '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
                       '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
                       '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
                       '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
                       '</Types>')
            z.writestr("_rels/.rels",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                       '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                       '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
                       '</Relationships>')
            z.writestr("docProps/core.xml",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                       'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
                       'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                       f'<dc:title>{escape(self.title)}</dc:title><dc:creator>ElectropumpWorkshop</dc:creator>'
                       '</cp:coreProperties>')
            z.writestr("docProps/app.xml",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
                       '<Application>ElectropumpWorkshop</Application></Properties>')
            z.writestr("word/_rels/document.xml.rels",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       + "".join(rels) + '</Relationships>')
            z.writestr("word/document.xml", document)
            z.writestr("word/styles.xml", self._styles())
            z.writestr("word/settings.xml",
                       '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                       f'<w:settings {NS}>'
                       '<w:defaultTabStop w:val="720"/><w:compat>'
                       '<w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/>'
                       '</w:compat></w:settings>')
            z.writestr("word/header1.xml", header)
            z.writestr("word/footer1.xml", footer)
            for _rid, name, data in self.images:
                z.writestr(f"word/media/{name}", data)
        return buf.getvalue()
