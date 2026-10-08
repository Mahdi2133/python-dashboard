# -*- coding: utf-8 -*-
"""کمک‌کارهای راست‌چین و فونت برای python-docx.

چرا این فایل جداست
------------------
ورد برای متنِ فارسی سه چیزِ جدا لازم دارد و اگر یکی‌شان جا بیفتد،
سند ظاهراً درست است ولی در عمل خراب:

  • <w:bidi/>  در pPr      → جهتِ پاراگراف
  • <w:rtl/>   در rPr      → جهتِ متنِ داخلِ ران
  • w:cs و w:szCs          → فونت و اندازه‌ی «خطِ پیچیده» (Complex Script)

w:sz اندازه‌ی متنِ لاتین را تعیین می‌کند و روی فارسی اثری ندارد؛ اگر
فقط w:sz بگذارید، فارسی روی اندازه‌ی پیش‌فرض می‌ماند. برای درشت کردن
هم w:bCs لازم است، نه فقط w:b.

⚠️ ترتیبِ فرزندان اجباری است
---------------------------
OOXML برای pPr و rPr و tcPr ترتیبِ ثابتی تعریف کرده و اگر عنصری سرِ
جای خودش نباشد، ورد و لیبره‌آفیس فایل را اصلاً باز نمی‌کنند
(«source file could not be loaded»). پس هیچ‌چیز را append نمی‌کنیم؛
همه‌چیز با insert_ordered سرِ جای درست می‌نشیند.
"""

from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.shared import Pt, RGBColor

FA = 'B Nazanin'          # فونتِ فارسی
EN = 'Times New Roman'    # فونتِ لاتین

# ترتیبِ رسمیِ ECMA-376
P_SEQ = ('pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr '
         'suppressLineNumbers pBdr shd tabs suppressAutoHyphens kinsoku wordWrap '
         'overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd '
         'snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc '
         'textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr '
         'sectPr pPrChange').split()

R_SEQ = ('rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow '
         'emboss imprint noProof snapToGrid vanish webHidden color spacing w kern '
         'position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em '
         'lang eastAsianLayout specVanish oMath').split()

TC_SEQ = ('cnfStyle tcW gridSpan hMerge vMerge tcBorders shd noWrap tcMar '
          'textDirection tcFitText vAlign hideMark').split()

TBL_SEQ = ('tblStyle tblpPr tblOverlap bidiVisual tblStyleRowBandSize '
           'tblStyleColBandSize tblW jc tblCellSpacing tblInd tblBorders shd '
           'tblLayout tblCellMar tblLook tblCaption tblDescription tblPrChange').split()

SECT_SEQ = ('footnotePr endnotePr type pgSz pgMar paperSrc pgBorders lnNumType '
            'pgNumType cols formProt vAlign noEndnote titlePg textDirection bidi '
            'rtlGutter docGrid printerSettings sectPrChange').split()


def _el(tag, **attrs):
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn('w:' + k), str(v))
    return e


def insert_ordered(parent, child, seq):
    """child را سرِ جای درستش در parent می‌گذارد (طبقِ ترتیبِ seq)."""
    name = child.tag.split('}')[1]
    if name not in seq:
        parent.append(child); return child
    idx = seq.index(name)
    for existing in parent:
        ename = existing.tag.split('}')[1]
        if ename in seq and seq.index(ename) > idx:
            existing.addprevious(child)
            return child
    parent.append(child)
    return child


def _set_p(pPr, tag, **attrs):
    """عنصری را در pPr می‌گذارد؛ اگر بود، جایگزینش می‌کند."""
    old = pPr.find(qn('w:' + tag))
    if old is not None: pPr.remove(old)
    return insert_ordered(pPr, _el('w:' + tag, **attrs), P_SEQ)


def _set_r(rPr, tag, **attrs):
    old = rPr.find(qn('w:' + tag))
    if old is not None: rPr.remove(old)
    return insert_ordered(rPr, _el('w:' + tag, **attrs), R_SEQ)


def rtl_para(p, align=None, space_after=6, space_before=0, line=1.5,
             indent_r=0, indent_l=0, keep_next=False):
    """پاراگراف را راست‌چین و دوزبانه تنظیم می‌کند."""
    pPr = p._p.get_or_add_pPr()
    _set_p(pPr, 'bidi')
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(space_before)
    pf.line_spacing = line
    if indent_r: pf.right_indent = indent_r
    if indent_l: pf.left_indent = indent_l
    if keep_next: pf.keep_with_next = True
    return p


def run(p, text, size=12, bold=False, color=None, fa=FA, en=EN,
        italic=False, underline=False):
    """یک رانِ دوزبانه: لاتینش تایمز، فارسی‌اش نازنین."""
    r = p.add_run(text)
    rPr = r._r.get_or_add_rPr()

    _set_r(rPr, 'rFonts', ascii=en, hAnsi=en, cs=fa, eastAsia=en)

    if bold:
        r.bold = True
        _set_r(rPr, 'bCs')
    if italic:
        r.italic = True
        _set_r(rPr, 'iCs')
    if underline:
        r.underline = True
    if color:
        r.font.color.rgb = RGBColor.from_string(color)

    r.font.size = Pt(size)
    _set_r(rPr, 'szCs', val=str(int(round(size * 2))))   # اندازه‌ی فارسی
    _set_r(rPr, 'rtl')                                   # جهتِ ران
    return r


def cell_shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    old = tcPr.find(qn('w:shd'))
    if old is not None: tcPr.remove(old)
    insert_ordered(tcPr, _el('w:shd', val='clear', color='auto', fill=fill), TC_SEQ)


def borders(p_el, **sides):
    """خط‌های دورِ پاراگراف. مثال: borders(p._p, bottom=('8F6E2C', 6))"""
    pPr = p_el.get_or_add_pPr()
    old = pPr.find(qn('w:pBdr'))
    if old is not None: pPr.remove(old)
    bd = OxmlElement('w:pBdr')
    for side in ('top', 'left', 'bottom', 'right'):
        if side in sides:
            color, sz = sides[side]
            bd.append(_el('w:' + side, val='single', sz=str(sz), space='4', color=color))
    insert_ordered(pPr, bd, P_SEQ)


def cell_borders(cell, **sides):
    tcPr = cell._tc.get_or_add_tcPr()
    old = tcPr.find(qn('w:tcBorders'))
    if old is not None: tcPr.remove(old)
    bd = OxmlElement('w:tcBorders')
    # ترتیبِ داخلِ tcBorders هم تعریف‌شده است
    for side in ('top', 'start', 'left', 'bottom', 'end', 'right',
                 'insideH', 'insideV'):
        if side in sides:
            color, sz = sides[side]
            bd.append(_el('w:' + side, val='single', sz=str(sz), space='0', color=color))
    insert_ordered(tcPr, bd, TC_SEQ)


def table_rtl(table):
    """ترتیبِ ستون‌ها را راست‌به‌چپ می‌کند تا ستونِ اول سمتِ راست بیفتد.

    bidiVisual در tblPr جای مشخصی دارد (پیش از tblW و jc و tblLook).
    اگر append شود، فایل اصلاً باز نمی‌شود.
    """
    tblPr = table._tbl.tblPr
    old = tblPr.find(qn('w:bidiVisual'))
    if old is not None: tblPr.remove(old)
    insert_ordered(tblPr, _el('w:bidiVisual'), TBL_SEQ)


def cell_valign(cell, v='center'):
    tcPr = cell._tc.get_or_add_tcPr()
    old = tcPr.find(qn('w:vAlign'))
    if old is not None: tcPr.remove(old)
    insert_ordered(tcPr, _el('w:vAlign', val=v), TC_SEQ)


def no_space(cell):
    for p in cell.paragraphs:
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)


def section_rtl(section):
    """جهتِ کلِ بخش را راست‌به‌چپ می‌کند.

    w:bidi در sectPr پس از textDirection و پیش از docGrid می‌نشیند.
    """
    sectPr = section._sectPr
    old = sectPr.find(qn('w:bidi'))
    if old is not None: sectPr.remove(old)
    insert_ordered(sectPr, _el('w:bidi'), SECT_SEQ)


def fix_zoom(doc):
    """قالبِ پیش‌فرضِ python-docx یک <w:zoom> بدونِ صفتِ percent دارد که
    اعتبارسنجیِ OOXML ردش می‌کند. یا پُرش می‌کنیم یا برش می‌داریم."""
    st = doc.settings.element
    z = st.find(qn('w:zoom'))
    if z is not None and z.get(qn('w:percent')) is None:
        z.set(qn('w:percent'), '100')


def fix_table(table, widths):
    """عرضِ ستون‌ها را قطعی می‌کند.

    ⚠️ تنظیمِ cell.width به‌تنهایی کافی نیست. ورد و لیبره‌آفیس تا وقتی
       tblLayout روی fixed نباشد، خودشان ستون‌ها را «جا» می‌دهند و
       عرضِ خانه‌ها را نادیده می‌گیرند. در نسخه‌ی اولِ این سند، ستونِ
       مربعِ تیک پهن شد و ستونِ متن باریک — دقیقاً به همین دلیل.

       پس هر سه را با هم می‌گذاریم: tblW کل، tblLayout=fixed،
       gridCol هر ستون، و tcW هر خانه.
    """
    total = sum(w.twips if hasattr(w, 'twips') else int(w) for w in widths)
    tbl = table._tbl
    tblPr = tbl.tblPr

    for tag, attrs in (('tblW', dict(w=str(total), type='dxa')),
                       ('tblLayout', dict(type='fixed'))):
        old = tblPr.find(qn('w:' + tag))
        if old is not None: tblPr.remove(old)
        insert_ordered(tblPr, _el('w:' + tag, **attrs), TBL_SEQ)

    # شبکه‌ی ستون‌ها
    grid = tbl.find(qn('w:tblGrid'))
    if grid is not None:
        tbl.remove(grid)
    grid = OxmlElement('w:tblGrid')
    for w in widths:
        grid.append(_el('w:gridCol', w=str(w.twips if hasattr(w, 'twips') else int(w))))
    tblPr.addnext(grid)

    table.autofit = False
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            if i < len(widths):
                cell.width = widths[i]
    return table
