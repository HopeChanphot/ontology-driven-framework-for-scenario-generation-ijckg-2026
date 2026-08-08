from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
OUTPUT = PACKAGE_ROOT / "START_HERE_PSQ_SCO_HANDOVER.docx"

NAVY = "203748"
BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
INK = "202124"
MUTED = "5F6368"
LIGHT_BLUE = "E8EEF5"
LIGHT_GRAY = "F2F4F7"
CALLOUT = "F4F6F9"
WHITE = "FFFFFF"
GREEN = "1F6D4A"
GOLD = "7A5A00"
RED = "9B1C1C"

PAGE_WIDTH_DXA = 12240
PAGE_HEIGHT_DXA = 15840
MARGIN_DXA = 1440
CONTENT_WIDTH_DXA = 9360
TABLE_INDENT_DXA = 120
CELL_TOP_BOTTOM_DXA = 80
CELL_SIDE_DXA = 120


def set_run_font(
    run,
    *,
    name: str = "Calibri",
    size: float | None = None,
    color: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
) -> None:
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_style_font(style, *, name: str, size: float, color: str, bold: bool = False) -> None:
    style.font.name = name
    style.font.size = Pt(size)
    style.font.color.rgb = RGBColor.from_string(color)
    style.font.bold = bold
    style._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    style._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    style._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)


def configure_styles(doc: Document) -> None:
    normal = doc.styles["Normal"]
    set_style_font(normal, name="Calibri", size=11, color=INK)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    normal.paragraph_format.widow_control = True

    title = doc.styles["Title"]
    set_style_font(title, name="Calibri", size=30, color=NAVY, bold=True)
    title.paragraph_format.space_before = Pt(0)
    title.paragraph_format.space_after = Pt(8)
    title.paragraph_format.line_spacing = 1.0
    title.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.keep_with_next = True
    title_ppr = title._element.get_or_add_pPr()
    title_border = title_ppr.find(qn("w:pBdr"))
    if title_border is not None:
        title_ppr.remove(title_border)

    subtitle = doc.styles["Subtitle"]
    set_style_font(subtitle, name="Calibri", size=15, color=DARK_BLUE)
    subtitle.paragraph_format.space_before = Pt(0)
    subtitle.paragraph_format.space_after = Pt(12)
    subtitle.paragraph_format.line_spacing = 1.1
    subtitle.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.keep_with_next = True

    heading_tokens = {
        "Heading 1": (16, BLUE, 18, 10),
        "Heading 2": (13, BLUE, 14, 7),
        "Heading 3": (12, DARK_BLUE, 10, 5),
    }
    for name, (size, color, before, after) in heading_tokens.items():
        style = doc.styles[name]
        set_style_font(style, name="Calibri", size=size, color=color, bold=True)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.line_spacing = 1.0
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.keep_together = True

    caption = doc.styles["Caption"]
    set_style_font(caption, name="Calibri", size=9, color=MUTED, bold=True)
    caption.paragraph_format.space_before = Pt(4)
    caption.paragraph_format.space_after = Pt(4)
    caption.paragraph_format.line_spacing = 1.0


def set_page_geometry(section) -> None:
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)


def add_page_field(paragraph) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    display = OxmlElement("w:t")
    display.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instruction, separate, display, end])
    set_run_font(run, size=8.5, color=MUTED)


def configure_header_footer(section) -> None:
    section.different_first_page_header_footer = False
    section.header.is_linked_to_previous = False
    header = section.header
    p = header.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)

    section.footer.is_linked_to_previous = False
    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run("Chanphot Wongtaweesup  |  ReaLearn  |  Page ")
    set_run_font(r, size=8.5, color=MUTED)
    add_page_field(p)


def add_numbering_definitions(doc: Document) -> tuple[int, int]:
    numbering = doc.part.numbering_part.element
    abstract_ids = [
        int(node.get(qn("w:abstractNumId")))
        for node in numbering.findall(qn("w:abstractNum"))
    ]
    num_ids = [int(node.get(qn("w:numId"))) for node in numbering.findall(qn("w:num"))]
    bullet_abstract_id = (max(abstract_ids) + 1) if abstract_ids else 1
    decimal_abstract_id = bullet_abstract_id + 1
    bullet_num_id = (max(num_ids) + 1) if num_ids else 1
    decimal_num_id = bullet_num_id + 1

    def add_abstract(abstract_id: int, fmt: str, level_text: str, marker_font: str) -> None:
        abstract = OxmlElement("w:abstractNum")
        abstract.set(qn("w:abstractNumId"), str(abstract_id))
        multi = OxmlElement("w:multiLevelType")
        multi.set(qn("w:val"), "singleLevel")
        abstract.append(multi)
        level = OxmlElement("w:lvl")
        level.set(qn("w:ilvl"), "0")
        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        level.append(start)
        num_fmt = OxmlElement("w:numFmt")
        num_fmt.set(qn("w:val"), fmt)
        level.append(num_fmt)
        lvl_text = OxmlElement("w:lvlText")
        lvl_text.set(qn("w:val"), level_text)
        level.append(lvl_text)
        jc = OxmlElement("w:lvlJc")
        jc.set(qn("w:val"), "left")
        level.append(jc)
        ppr = OxmlElement("w:pPr")
        tabs = OxmlElement("w:tabs")
        tab = OxmlElement("w:tab")
        tab.set(qn("w:val"), "num")
        tab.set(qn("w:pos"), "540")
        tabs.append(tab)
        ppr.append(tabs)
        indent = OxmlElement("w:ind")
        indent.set(qn("w:left"), "540")
        indent.set(qn("w:hanging"), "270")
        ppr.append(indent)
        spacing = OxmlElement("w:spacing")
        spacing.set(qn("w:before"), "0")
        spacing.set(qn("w:after"), "80")
        spacing.set(qn("w:line"), "300")
        spacing.set(qn("w:lineRule"), "auto")
        ppr.append(spacing)
        level.append(ppr)
        rpr = OxmlElement("w:rPr")
        fonts = OxmlElement("w:rFonts")
        fonts.set(qn("w:ascii"), marker_font)
        fonts.set(qn("w:hAnsi"), marker_font)
        rpr.append(fonts)
        level.append(rpr)
        abstract.append(level)
        numbering.append(abstract)

    def add_num(num_id: int, abstract_id: int) -> None:
        num = OxmlElement("w:num")
        num.set(qn("w:numId"), str(num_id))
        abstract_ref = OxmlElement("w:abstractNumId")
        abstract_ref.set(qn("w:val"), str(abstract_id))
        num.append(abstract_ref)
        numbering.append(num)

    add_abstract(bullet_abstract_id, "bullet", "\u2022", "Symbol")
    add_abstract(decimal_abstract_id, "decimal", "%1.", "Calibri")
    add_num(bullet_num_id, bullet_abstract_id)
    add_num(decimal_num_id, decimal_abstract_id)
    return bullet_num_id, decimal_num_id


def add_list_item(doc: Document, text: str, num_id: int, *, bold_prefix: str | None = None):
    p = doc.add_paragraph()
    p.paragraph_format.keep_together = True
    num_pr = p._p.get_or_add_pPr().get_or_add_numPr()
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num_id_element = OxmlElement("w:numId")
    num_id_element.set(qn("w:val"), str(num_id))
    num_pr.append(ilvl)
    num_pr.append(num_id_element)
    if bold_prefix and text.startswith(bold_prefix):
        r = p.add_run(bold_prefix)
        set_run_font(r, bold=True)
        r = p.add_run(text[len(bold_prefix) :])
        set_run_font(r)
    else:
        r = p.add_run(text)
        set_run_font(r)
    return p


def add_body(doc: Document, text: str, *, bold_lead: str | None = None, keep: bool = False):
    p = doc.add_paragraph()
    p.paragraph_format.keep_together = keep
    if bold_lead and text.startswith(bold_lead):
        r = p.add_run(bold_lead)
        set_run_font(r, bold=True)
        r = p.add_run(text[len(bold_lead) :])
        set_run_font(r)
    else:
        r = p.add_run(text)
        set_run_font(r)
    return p


def add_path(doc: Document, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.18)
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.line_spacing = 1.0
    r = p.add_run(text)
    set_run_font(r, name="Consolas", size=8.5, color=DARK_BLUE)
    return p


def set_paragraph_shading(paragraph, fill: str) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    shd = ppr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        ppr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_paragraph_left_border(paragraph, color: str, size: int = 18) -> None:
    ppr = paragraph._p.get_or_add_pPr()
    borders = ppr.find(qn("w:pBdr"))
    if borders is None:
        borders = OxmlElement("w:pBdr")
        ppr.append(borders)
    left = OxmlElement("w:left")
    left.set(qn("w:val"), "single")
    left.set(qn("w:sz"), str(size))
    left.set(qn("w:space"), "8")
    left.set(qn("w:color"), color)
    borders.append(left)


def add_callout(doc: Document, label: str, text: str, *, color: str = BLUE, fill: str = CALLOUT):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.16)
    p.paragraph_format.right_indent = Inches(0.12)
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.keep_together = True
    set_paragraph_shading(p, fill)
    set_paragraph_left_border(p, color)
    r = p.add_run(f"{label}: ")
    set_run_font(r, bold=True, color=color)
    r = p.add_run(text)
    set_run_font(r, color=INK)
    return p


def set_cell_margins(cell) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for side, value in (
        ("top", CELL_TOP_BOTTOM_DXA),
        ("bottom", CELL_TOP_BOTTOM_DXA),
        ("start", CELL_SIDE_DXA),
        ("end", CELL_SIDE_DXA),
    ):
        node = tc_mar.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_cell_width(cell, width_dxa: int) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(width_dxa))
    tc_w.set(qn("w:type"), "dxa")


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def mark_header_row(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_table_geometry(table, widths_dxa: list[int]) -> None:
    if sum(widths_dxa) != CONTENT_WIDTH_DXA:
        raise ValueError(f"Table widths must sum to {CONTENT_WIDTH_DXA}: {widths_dxa}")
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(CONTENT_WIDTH_DXA))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(TABLE_INDENT_DXA))
    tbl_ind.set(qn("w:type"), "dxa")
    layout = tbl_pr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        tbl_pr.append(layout)
    layout.set(qn("w:type"), "fixed")

    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths_dxa:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)

    for row in table.rows:
        for index, cell in enumerate(row.cells):
            set_cell_width(cell, widths_dxa[index])
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def add_table(
    doc: Document,
    headers: list[str],
    rows: list[list[str]],
    widths_dxa: list[int],
    *,
    font_size: float = 9.2,
    alignments: list[int] | None = None,
):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = 0
    set_table_geometry(table, widths_dxa)
    mark_header_row(table.rows[0])
    if alignments is None:
        alignments = [WD_ALIGN_PARAGRAPH.LEFT] * len(headers)

    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        shade_cell(cell, LIGHT_BLUE)
        p = cell.paragraphs[0]
        p.alignment = alignments[index]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run(header)
        set_run_font(r, size=font_size, bold=True, color=NAVY)

    for row_values in rows:
        row = table.add_row()
        for index, value in enumerate(row_values):
            cell = row.cells[index]
            p = cell.paragraphs[0]
            p.alignment = alignments[index]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.05
            r = p.add_run(str(value))
            set_run_font(r, size=font_size, color=INK)
    set_table_geometry(table, widths_dxa)
    after = doc.add_paragraph()
    after.paragraph_format.space_before = Pt(0)
    after.paragraph_format.space_after = Pt(3)
    return table


def add_hyperlink(paragraph, text: str, url: str) -> None:
    relationship_id = paragraph.part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), BLUE)
    rpr.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rpr.append(underline)
    run.append(rpr)
    text_node = OxmlElement("w:t")
    text_node.text = text
    run.append(text_node)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_page_break(doc: Document) -> None:
    p = doc.add_paragraph()
    p.add_run().add_break(WD_BREAK.PAGE)


def add_kicker(doc: Document, text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(76)
    p.paragraph_format.space_after = Pt(18)
    r = p.add_run(text.upper())
    set_run_font(r, size=10, bold=True, color=GOLD)
    return p


def add_metadata_line(doc: Document, label: str, value: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.0
    r = p.add_run(f"{label}: ")
    set_run_font(r, size=10, bold=True, color=NAVY)
    r = p.add_run(value)
    set_run_font(r, size=10, color=MUTED)
    return p


def build_document() -> None:
    doc = Document()
    doc.settings.odd_and_even_pages_header_footer = False
    for section in doc.sections:
        set_page_geometry(section)
        configure_header_footer(section)
    configure_styles(doc)
    bullet_id, decimal_id = add_numbering_definitions(doc)

    props = doc.core_properties
    props.title = "PSQ-SCO Research Internship Handover"
    props.subject = "Compact continuation guide for the PersonaShield Quest Scenario Control Ontology internship project"
    props.author = "Chanphot Wongtaweesup"
    props.keywords = "PSQ-SCO, ontology, GenAI, cybersecurity serious game, research internship, handover"
    props.comments = "Prepared as a compact continuation snapshot dated 26 July 2026."

    # Page 1: editorial cover.
    add_kicker(doc, "ReaLearn | Trustworthy AI Lab | AI So-Go-Chi Center")
    p = doc.add_paragraph("PSQ-SCO Research Internship Handover", style="Title")
    p = doc.add_paragraph(
        "Ontology-Guided Scenario Control Generation for GenAI in a Cybersecurity Serious Game",
        style="Subtitle",
    )
    add_metadata_line(doc, "Researcher", "Chanphot Wongtaweesup, Ph.D. Student, Asian Institute of Technology")
    add_metadata_line(doc, "Internship", "8 May-6 August 2026")
    add_metadata_line(doc, "Host", "ReaLearn, Tohoku University")
    add_metadata_line(doc, "Lab lead", "Teeradaj Racharak")
    add_metadata_line(doc, "Snapshot", "26 July 2026 | Compact continuation package")
    add_callout(
        doc,
        "Status boundary",
        "This handover records work verified through 26 July 2026. Activities scheduled from 27 July to 6 August are planned or in progress and are not presented as completed results.",
        color=GOLD,
        fill="FFF8E8",
    )
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(22)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run("OPEN FIRST  |  VERIFY  |  CONTINUE")
    set_run_font(r, size=10, color=BLUE, bold=True)

    # Page 2: scope and package map.
    add_page_break(doc)
    doc.add_heading("1. What is handed over", level=1)
    add_body(
        doc,
        "This package is a deliberately small research-continuity snapshot. It retains the authoritative ontology, runnable generation and evaluation code, regression tests, compact final evidence, the latest manuscript, weekly slides, and the complete internship report. It excludes replaceable local infrastructure and bulk data.",
    )
    add_callout(
        doc,
        "Read first",
        "Use README.md for commands, EXCLUSIONS_AND_REBUILD.md before a full rerun, and LICENSE_AND_DATA_NOTICE.md before redistribution.",
    )
    doc.add_heading("Package map", level=2)
    add_table(
        doc,
        ["Area", "Continuation-critical contents"],
        [
            ["ontology/", "PSQ-SCO v9.1 OWL, v9.1 CQs, KG exports, bindings, release scripts, final validation evidence."],
            ["genai_engine/", "Four-mode generator, evaluation engines, tests, configs, selected technical docs, final evidence, targeted repair, manuscript."],
            ["internship/", "26-page final report, ten dated weekly slide PDFs, compact report-build sources."],
            ["Root controls", "Two minimal four-mode launchers, small dependency list, README, exclusions, license/data notice, manifest, and checksums."],
        ],
        [2080, 7280],
    )
    doc.add_heading("Version authority", level=2)
    add_list_item(doc, "Ontology authority: v9.1 OWL under ontology/ontology.", bullet_id)
    add_list_item(doc, "Paper authority: latest main.tex under targeted_evaluation_repair/overleaf.", bullet_id)
    add_list_item(doc, "Frozen comparison authority: targeted_evaluation_repair/evaluation_rerun.", bullet_id)
    add_list_item(doc, "Graph-Walk authority: separate ablation evidence dated 20260723.", bullet_id)
    add_list_item(doc, "Internship authority: final report under internship/report.", bullet_id)
    add_callout(
        doc,
        "Do not merge",
        "Graph-Walk v1 is a separate ablation. Do not replace Condition 4 in the frozen paper comparison without labeling the resulting analysis as a new experiment.",
        color=RED,
        fill="FDECEC",
    )

    # Page 3: quick start.
    add_page_break(doc)
    doc.add_heading("2. Quick start", level=1)
    add_body(doc, "The commands below assume Windows PowerShell from the extracted package root and Python 3.10 or newer.")
    add_callout(
        doc,
        "Authoritative ontology",
        "ontology/ontology/personashield-psq-sco-v9.1.owl is included and is used automatically by both launchers.",
        color=GREEN,
        fill="EEF7F2",
    )
    doc.add_heading("Install the minimal environment", level=2)
    for line in (
        "python -m venv .venv",
        "$py = (Resolve-Path .\\.venv\\Scripts\\python.exe).Path",
        "& $py -m pip install --upgrade pip",
        "& $py -m pip install -r .\\requirements-minimal.txt",
    ):
        add_path(doc, line)
    doc.add_heading("Four research modes", level=2)
    add_table(
        doc,
        ["Mode", "Context exercised by the included smoke path"],
        [
            ["prompt_only", "Base prompt; intentionally no retrieval or ontology context."],
            ["prompt_rag", "Base prompt plus the included one-record lexical RAG example."],
            ["ontology_prompt_rag", "Structured PSQ-SCO semantic packet plus lexical RAG."],
            ["ontology_text_rag", "PSQ-SCO graph-to-text documents plus lexical RAG."],
        ],
        [2900, 6460],
        font_size=8.5,
    )
    doc.add_heading("Generate and evaluate", level=2)
    add_list_item(doc, "Generate one matched case in all four modes without a model server.", decimal_id)
    add_path(doc, ".\\RUN_4_MODES_MINIMAL.ps1 -PythonExe $py")
    add_list_item(doc, "Evaluate the newest output with ontology, scenario, method, diversity, and traceability checks.", decimal_id)
    add_path(doc, ".\\EVALUATE_4_MODES_MINIMAL.ps1 -PythonExe $py")
    add_callout(
        doc,
        "Verified outcome",
        "The packaged smoke path produced 4/4 mode outputs with 4/4 engine validation passes. Evaluation imported hash-matched HermiT evidence, passed 8/8 CQs and 4/4 runtime mappings, and wrote a Markdown report plus CSV/JSON evidence.",
        color=GREEN,
        fill="EEF7F2",
    )
    add_body(
        doc,
        "Development entry points are genai_engine/generate_scenarios_sco.py and genai_engine/evaluate_three_layer.py. The root README documents live Ollama use, optional full dependencies, CQs, and regression tests.",
    )

    # Page 4: validated baseline.
    add_page_break(doc)
    doc.add_heading("3. Validated research baseline", level=1)
    doc.add_heading("Ontology release state", level=2)
    add_table(
        doc,
        ["Item", "Verified state"],
        [
            ["Scope", "Scenario-control knowledge only; broad pedagogy branch removed in v9.1."],
            ["Ontology size", "73 declared domain classes; evaluator reports 74 when owl:Thing is included; 49 object and 39 datatype properties; 133 named individuals."],
            ["Graph", "3,229 triples; exported KG has 311 nodes and 3,164 edges."],
            ["Reasoning", "HermiT consistent; 0 unsatisfiable classes; recorded duration 3.636 s."],
            ["Competency tests", "8/8 ASK cases pass. CQ1-CQ4 return 2, 13, 8, and 12 rows for the documented examples."],
            ["Completeness", "4,362/4,362 bounded checks and 1,440/1,440 runtime mappings in the original full release."],
        ],
        [2700, 6660],
        font_size=8.9,
    )
    doc.add_heading("Frozen four-condition comparison", level=2)
    add_body(
        doc,
        "The paper-aligned experiment contains 120 matched cases across four methods and three local models (Mistral 7B, Qwen2.5 7B, and Qwen3 8B), for 1,440 outputs. Higher is better except contradiction rate E.",
    )
    add_table(
        doc,
        ["Method", "F1", "G", "T", "E", "OCIeq", "Rank"],
        [
            ["Prompt only", ".512", ".481", "N/A", ".000", ".799", "4"],
            ["Text RAG", ".448", ".782", ".928", ".000", ".846", "3"],
            ["Structured ontology + RAG", ".545", "1.000", ".996", ".000", ".909", "1"],
            ["Ontology-to-text RAG", ".399", "1.000", ".968", ".003", ".879", "2"],
        ],
        [3600, 820, 820, 820, 820, 1480, 1000],
        font_size=8.4,
        alignments=[
            WD_ALIGN_PARAGRAPH.LEFT,
            WD_ALIGN_PARAGRAPH.CENTER,
            WD_ALIGN_PARAGRAPH.CENTER,
            WD_ALIGN_PARAGRAPH.CENTER,
            WD_ALIGN_PARAGRAPH.CENTER,
            WD_ALIGN_PARAGRAPH.CENTER,
            WD_ALIGN_PARAGRAPH.CENTER,
        ],
    )
    add_callout(
        doc,
        "Interpretation",
        "Ontology conditioning provided its clearest advantage in controllability, completeness, and auditability. It should not be claimed as a universal quality improvement: precision-recall tradeoffs, schema-safe repairs, external-RAG exposure, and human judgment remain material.",
    )
    add_body(
        doc,
        "Separate Graph-Walk v1 evidence: verified ontology-walk exposure 360/360; external vector context 234/360; live content retained 239/360; engine validation passed 151/360; final technical acceptance 360/360; embedding diversity .3732; Self-BLEU .8398.",
    )

    # Page 5: reproduction workflow.
    add_page_break(doc)
    doc.add_heading("4. Reproduce and extend", level=1)
    doc.add_heading("Recommended experiment workflow", level=2)
    _, workflow_decimal_id = add_numbering_definitions(doc)
    for text in (
        "Freeze the research question, condition definitions, case manifest, model tags, generation parameters, ontology checksum, and dataset catalog.",
        "Restore only licensed RAG corpora. Build a fresh index and record ingestion counts, retrieval dates, and source checksums.",
        "Run prompt-only and ontology conditions on the same matched cases. Treat fallback or schema-safe repair as a separate integrity variable.",
        "Validate ontology exposure, external-RAG exposure, output schema, common required concepts, contradictions, traceability, and source-linkage limits.",
        "Report common metrics separately from mechanism-specific metrics. Keep Graph-Walk and other ablations in separate result tables.",
        "Archive source, manifests, logs, summaries, exact environment lock, and a human-review sample under a new immutable run identifier.",
    ):
        add_list_item(doc, text, workflow_decimal_id)
    doc.add_heading("Full evaluation entry point", level=2)
    add_path(doc, "genai_engine/evaluate_three_layer.py")
    add_path(doc, "--ontology-root ../ontology")
    add_path(doc, "--ontology-path ../ontology/ontology/personashield-psq-sco-v9.1.owl")
    add_path(doc, "--queries-dir ../ontology/queries/v9_1")
    add_path(doc, "--hermit-report ../ontology/outputs/v9_1/hermit-reasoner-report.json")
    add_callout(
        doc,
        "Exact replication boundary",
        "The frozen 1,440 scenario JSONL records are intentionally excluded. A new generation run is a valid continuation experiment but is not bit-identical replication unless the same inputs, model builds, prompts, seeds, dependencies, and runtime behavior are restored.",
        color=GOLD,
        fill="FFF8E8",
    )
    doc.add_heading("New run naming", level=2)
    add_body(
        doc,
        "Use a timestamped immutable path such as output/experiments/<study>/<YYYYMMDD_HHMMSS>/ and include a manifest that links every result row to case, model, method, ontology checksum, prompt version, RAG source IDs, and generation-integrity state.",
    )

    # Page 6: limits and controls.
    add_page_break(doc)
    doc.add_heading("5. Limits, safety, and publication state", level=1)
    doc.add_heading("Known limits", level=2)
    for text in (
        "The evaluation is predominantly automated. A preregistered expert human evaluation remains necessary for educational usefulness, realism, safety, and claim-level support.",
        "Claim-source faithfulness was not fully evaluated. Source identifiers and retrieval exposure do not prove that every generated claim is supported.",
        "Local-model behavior, embedding models, and vector indexes are version-sensitive. Rebuilt outputs may differ.",
        "The equal-weight OCI is a secondary operational index. Keep component metrics visible and retain weight-sensitivity analysis.",
        "The original full runtime-mapping export, raw corpora, and vector stores are omitted; see EXCLUSIONS_AND_REBUILD.md.",
        "Historical evidence contains machine-specific paths. Preserve those records; use explicit relative paths for new runs.",
    ):
        add_list_item(doc, text, bullet_id)
    doc.add_heading("Safety and governance controls", level=2)
    add_table(
        doc,
        ["Risk", "Required control"],
        [
            ["Credential or private-data leakage", "Secret scan every archive; never include .env, tokens, private corpora, or unreviewed logs."],
            ["Unsafe scenario content", "Keep defensive framing, block operational attack instructions, and require expert review before deployment."],
            ["Dataset licensing", "Store only approved data; preserve license, source URL, retrieval date, and redistribution status."],
            ["Overclaiming", "Separate verified results, inference, planned work, ablations, and unverified publication status."],
            ["Evidence drift", "Hash ontology, code, cases, prompts, model tags, and final artifacts for every run."],
        ],
        [2700, 6660],
        font_size=8.9,
    )
    add_callout(
        doc,
        "Publication state",
        "The latest manuscript is packaged and targets the IJCKG 2026 Education Track. Submission, peer-review, acceptance, and publication are not verified in this handover.",
        color=GOLD,
        fill="FFF8E8",
    )

    # Page 7: continuation checklist and evidence pointers.
    add_page_break(doc)
    doc.add_heading("6. Continuation checklist", level=1)
    doc.add_heading("First 7 days", level=2)
    for text in (
        "Verify CHECKSUMS_SHA256.txt and record the receiving maintainer.",
        "Create a private version-control repository; protect the default branch and enable secret scanning.",
        "Run the four-mode smoke launcher and evaluator, then rerun 65 core tests and 13 targeted-repair tests.",
        "Review the report, latest main.tex, exclusions guide, and license/data notice.",
    ):
        add_list_item(doc, text, bullet_id)
    doc.add_heading("Next 30 days", level=2)
    for text in (
        "Acquire approved datasets and rebuild the RAG index with a data card and checksums.",
        "Create a locked environment file and CI for ontology, unit, schema, and secret checks.",
        "Design and preregister the expert human-evaluation protocol and analysis plan.",
    ):
        add_list_item(doc, text, bullet_id)
    doc.add_heading("Next 60-90 days", level=2)
    for text in (
        "Run a clearly versioned replication or extension, retaining generation-integrity and exposure audits.",
        "Perform expert review, inter-rater agreement analysis, error analysis, and claim-source evaluation.",
        "Update the manuscript without mixing the frozen comparison with new Graph-Walk or model results.",
    ):
        add_list_item(doc, text, bullet_id)
    doc.add_heading("Verification completed for this package", level=2)
    add_table(
        doc,
        ["Check", "Result"],
        [
            ["PSQ-SCO CQs", "CQ1-CQ4 executed successfully; 8/8 ASK cases passed."],
            ["Core engine suite", "65/65 tests passed with optional scientific dependencies available."],
            ["Targeted repair suite", "13/13 tests passed, including 1,440-record integrity and manuscript checks."],
            ["Four-mode generation", "4/4 dry-run mode outputs generated; 4/4 passed engine validation."],
            ["Minimal evaluation", "HermiT evidence imported by ontology SHA-256; 8/8 CQs and 4/4 runtime mappings passed."],
            ["Archive integrity", "See MANIFEST.csv and CHECKSUMS_SHA256.txt."],
        ],
        [2700, 6660],
        font_size=8.9,
    )
    # Page 8: developer and evidence index.
    add_page_break(doc)
    doc.add_heading("7. Developer and evidence index", level=1)
    add_body(
        doc,
        "Continue from the smallest relevant entry point. The launchers are orchestration only; the implementation remains in the packaged engine modules.",
    )
    add_table(
        doc,
        ["Continuation task", "Start here"],
        [
            ["Run all four modes", "RUN_4_MODES_MINIMAL.ps1"],
            ["Evaluate the newest run", "EVALUATE_4_MODES_MINIMAL.ps1"],
            ["Change mode routing or generation", "genai_engine/psq_sco_generation/cli.py and engine.py"],
            ["Change prompting or graph-to-text", "genai_engine/psq_sco_generation/prompts.py and ontology_text.py"],
            ["Change scenario schema or validation", "genai_engine/schemas.py and validator.py"],
            ["Change ontology or CQs", "ontology/ontology/personashield-psq-sco-v9.1.owl and ontology/queries/v9_1/"],
            ["Run regression suites", "genai_engine/tests/ and genai_engine/targeted_evaluation_repair/tests/"],
        ],
        [3000, 6360],
        font_size=8.8,
    )
    add_callout(
        doc,
        "Minimal versus full operation",
        "The root launchers default to a model-free dry run and the included lexical RAG record. Use -Live with a supported Ollama model for live generation. Restore only approved corpora before a full RAG experiment.",
        color=GOLD,
        fill="FFF8E8",
    )
    doc.add_heading("Evidence pointers", level=2)
    add_table(
        doc,
        ["Evidence", "Path"],
        [
            ["Ontology release", "ontology/outputs/v9_1/release-validation-report.json"],
            ["Frozen method comparison", "genai_engine/targeted_evaluation_repair/evaluation_rerun/method_summary.csv"],
            ["Separate Graph-Walk ablation", "genai_engine/evidence/graph_walk_v1_separate_ablation_20260723/graph_walk_summary.json"],
            ["Latest manuscript", "genai_engine/targeted_evaluation_repair/overleaf/main.tex"],
            ["Minimal four-mode evaluation", "genai_engine/output/minimal_four_modes_evaluation/<timestamp>/evaluation_report.md"],
        ],
        [2800, 6560],
        font_size=8.2,
    )

    # Page 9: references and ownership handoff.
    references_heading = doc.add_heading("References and ownership handoff", level=1)
    references_heading.paragraph_format.page_break_before = True
    add_body(
        doc,
        "The full academic reference list and evidence trail are in the internship report and manuscript. The sources below anchor the technical handover.",
    )
    references = [
        ("W3C OWL 2 Web Ontology Language overview", "https://www.w3.org/TR/owl2-overview/"),
        ("W3C SPARQL 1.1 Query Language", "https://www.w3.org/TR/sparql11-query/"),
        ("W3C PROV-O provenance ontology", "https://www.w3.org/TR/prov-o/"),
        ("W3C Shapes Constraint Language (SHACL)", "https://www.w3.org/TR/shacl/"),
        ("Lewis et al. (2020), Retrieval-Augmented Generation", "https://proceedings.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html"),
        ("Glimm et al. (2014), HermiT OWL reasoner", "https://doi.org/10.1007/s10817-014-9305-1"),
        ("Jin et al. (2024), Graph Chain-of-Thought", "https://aclanthology.org/2024.findings-acl.11/"),
        ("Pineau et al. (2021), reproducibility in machine learning research", "https://www.jmlr.org/papers/v22/20-303.html"),
        ("Greco et al. (2019), composite-index methodology", "https://doi.org/10.1007/s11205-017-1832-9"),
    ]
    for index, (label, url) in enumerate(references, start=1):
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.18)
        p.paragraph_format.first_line_indent = Inches(-0.18)
        p.paragraph_format.space_after = Pt(5)
        p.paragraph_format.line_spacing = 1.1
        r = p.add_run(f"{index}. ")
        set_run_font(r, size=9.5, color=INK)
        add_hyperlink(p, label, url)

    doc.add_heading("Handoff roles", level=2)
    add_table(
        doc,
        ["Role", "Handoff record"],
        [
            ["Primary researcher", "Chanphot Wongtaweesup"],
            ["Host lab lead", "Teeradaj Racharak, ReaLearn (Trustworthy AI Lab)"],
            ["Receiving maintainer", "Assign in the project repository and record the acceptance date."],
            ["Research authority", "Use the internship report and frozen evidence; label later work as continuation."],
            ["Operational authority", "The receiving maintainer owns new environments, credentials, datasets, CI, and run records."],
        ],
        [2700, 6660],
        font_size=8.9,
    )
    add_callout(
        doc,
        "Handover acceptance",
        "A maintainer should confirm checksum verification, successful minimum tests, access to approved datasets/models, and agreement on repository ownership before beginning a new experiment.",
        color=GREEN,
        fill="EEF7F2",
    )

    # Apply section settings again in case Word created additional section objects.
    for section in doc.sections:
        set_page_geometry(section)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    build_document()
