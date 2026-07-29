"""Build the polished Word edition of the four-condition PSQ research monograph.

The Markdown source remains the research-document source of truth.  This script
creates a deterministic DOCX for supervisors, thesis appendices, and archival
sharing without introducing a second independently edited content copy.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, Sequence

from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
INK = "243447"
MUTED = "5B6770"
LIGHT_BLUE = "E8EEF5"
LIGHT_GRAY = "F4F6F9"
GRID = "B8C4CE"
WHITE = "FFFFFF"

PORTRAIT_WIDTH_DXA = 9360
LANDSCAPE_WIDTH_DXA = 13680
TABLE_INDENT_DXA = 120


def rgb(hex_value: str) -> RGBColor:
    """Convert a six-character hex string to a Word RGBColor."""

    return RGBColor.from_string(hex_value)


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
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = rgb(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_page_geometry(section, *, landscape: bool = False) -> None:
    """Apply the compact-reference geometry and the named wide-table override."""

    if landscape:
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width = Inches(11)
        section.page_height = Inches(8.5)
        section.left_margin = Inches(0.75)
        section.right_margin = Inches(0.75)
    else:
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width = Inches(8.5)
        section.page_height = Inches(11)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
    section.top_margin = Inches(0.85)
    section.bottom_margin = Inches(0.8)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)


def add_page_field(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run("Page ")
    set_run_font(run, size=8.5, color=MUTED)
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    value = OxmlElement("w:t")
    value.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, separate, value, end])


def configure_header_footer(
    section,
    *,
    header_label: str = "FOUR-CONDITION GENAI RESEARCH MONOGRAPH",
) -> None:
    header = section.header
    header.is_linked_to_previous = True
    paragraph = header.paragraphs[0]
    paragraph.clear()
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(6.4))
    left = paragraph.add_run("PERSONASHIELD QUEST")
    set_run_font(left, size=8, bold=True, color=DARK_BLUE)
    right = paragraph.add_run(f"\t{header_label}")
    set_run_font(right, size=8, color=MUTED)
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "2")
    bottom.set(qn("w:color"), "D7DEE5")
    borders.append(bottom)
    p_pr.append(borders)

    footer = section.footer
    footer.is_linked_to_previous = True
    footer_p = footer.paragraphs[0]
    footer_p.clear()
    add_page_field(footer_p)


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    repeat = OxmlElement("w:tblHeader")
    repeat.set(qn("w:val"), "true")
    tr_pr.append(repeat)


def keep_row_together(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    cant_split = OxmlElement("w:cantSplit")
    tr_pr.append(cant_split)


def set_cell_margins(cell, *, top: int = 80, start: int = 120, bottom: int = 80, end: int = 120) -> None:
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:fill"), fill)


def set_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = borders.find(qn(f"w:{edge}"))
        if node is None:
            node = OxmlElement(f"w:{edge}")
            borders.append(node)
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), "4")
        node.set(qn("w:color"), GRID)


def normalized_widths(rows: Sequence[Sequence[str]], total_dxa: int) -> list[int]:
    """Choose deterministic content-aware widths whose sum is exactly total_dxa."""

    cols = len(rows[0])
    scores: list[float] = []
    for col in range(cols):
        lengths = [len(re.sub(r"[`*_]", "", row[col])) for row in rows]
        scores.append(max(8.0, min(42.0, max(lengths[:1] + [sum(lengths) / len(lengths)]))))
    if cols >= 7:
        floor = 720
    elif cols >= 5:
        floor = 1000
    elif cols == 4:
        floor = 1350
    elif cols == 3:
        floor = 1800
    else:
        floor = 2100
    available = total_dxa - floor * cols
    if available < 0:
        floor = max(540, total_dxa // cols // 2)
        available = total_dxa - floor * cols
    score_total = sum(scores)
    widths = [floor + int(available * score / score_total) for score in scores]
    widths[-1] += total_dxa - sum(widths)
    return widths


def set_table_geometry(table, widths: Sequence[int], total_dxa: int) -> None:
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total_dxa))
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
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(widths[idx]))
            tc_w.set(qn("w:type"), "dxa")
            cell.width = Inches(widths[idx] / 1440)


def add_hyperlink(paragraph, label: str, url: str, *, size: float = 9.5) -> None:
    part = paragraph.part
    relationship = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship)
    run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), BLUE)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    size_node = OxmlElement("w:sz")
    size_node.set(qn("w:val"), str(int(size * 2)))
    size_cs = OxmlElement("w:szCs")
    size_cs.set(qn("w:val"), str(int(size * 2)))
    fonts = OxmlElement("w:rFonts")
    fonts.set(qn("w:ascii"), "Calibri")
    fonts.set(qn("w:hAnsi"), "Calibri")
    r_pr.extend([fonts, color, underline, size_node, size_cs])
    text = OxmlElement("w:t")
    text.text = label
    run.extend([r_pr, text])
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


INLINE_PATTERN = re.compile(
    r"(\[[^\]]+\]\(https?://[^)]+\)|\*\*[^*]+\*\*|`[^`]+`|(?<!\*)\*[^*]+\*(?!\*))"
)


def add_inline(paragraph, text: str, *, base_size: float = 10.5, base_color: str = INK) -> None:
    """Add the Markdown inline forms used by the monograph."""

    position = 0
    for match in INLINE_PATTERN.finditer(text):
        if match.start() > position:
            run = paragraph.add_run(text[position : match.start()])
            set_run_font(run, size=base_size, color=base_color)
        token = match.group(0)
        link = re.fullmatch(r"\[([^\]]+)\]\((https?://[^)]+)\)", token)
        if link:
            add_hyperlink(paragraph, link.group(1), link.group(2), size=base_size)
        elif token.startswith("**"):
            run = paragraph.add_run(token[2:-2])
            set_run_font(run, size=base_size, color=base_color, bold=True)
        elif token.startswith("`"):
            run = paragraph.add_run(token[1:-1])
            set_run_font(run, name="Consolas", size=max(8.0, base_size - 0.5), color=DARK_BLUE)
        elif token.startswith("*"):
            run = paragraph.add_run(token[1:-1])
            set_run_font(run, size=base_size, color=base_color, italic=True)
        position = match.end()
    if position < len(text):
        run = paragraph.add_run(text[position:])
        set_run_font(run, size=base_size, color=base_color)


def paragraph_shading(paragraph, fill: str, *, left_border: str | None = None) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    shade = OxmlElement("w:shd")
    shade.set(qn("w:fill"), fill)
    p_pr.append(shade)
    if left_border:
        borders = OxmlElement("w:pBdr")
        left = OxmlElement("w:left")
        left.set(qn("w:val"), "single")
        left.set(qn("w:sz"), "14")
        left.set(qn("w:space"), "6")
        left.set(qn("w:color"), left_border)
        borders.append(left)
        p_pr.append(borders)


def configure_styles(document: Document) -> None:
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = rgb(INK)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    for name, size, color, before, after in (
        ("Heading 1", 16, BLUE, 18, 10),
        ("Heading 2", 13, BLUE, 14, 7),
        ("Heading 3", 12, DARK_BLUE, 10, 5),
    ):
        style = styles[name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = rgb(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.keep_together = True

    for name in ("List Bullet", "List Number"):
        style = styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(10.5)
        style.font.color.rgb = rgb(INK)
        style.paragraph_format.left_indent = Inches(0.375)
        style.paragraph_format.first_line_indent = Inches(-0.188)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.25

    code = styles.add_style("PSQ Code", WD_STYLE_TYPE.PARAGRAPH)
    code.font.name = "Consolas"
    code._element.rPr.rFonts.set(qn("w:ascii"), "Consolas")
    code._element.rPr.rFonts.set(qn("w:hAnsi"), "Consolas")
    code.font.size = Pt(8.5)
    code.font.color.rgb = rgb(DARK_BLUE)
    code.paragraph_format.left_indent = Inches(0.18)
    code.paragraph_format.right_indent = Inches(0.18)
    code.paragraph_format.space_before = Pt(3)
    code.paragraph_format.space_after = Pt(5)
    code.paragraph_format.line_spacing = 1.05

    contents = styles.add_style("PSQ Contents Entry", WD_STYLE_TYPE.PARAGRAPH)
    contents.font.name = "Calibri"
    contents.font.size = Pt(10.5)
    contents.font.color.rgb = rgb(DARK_BLUE)
    contents.paragraph_format.left_indent = Inches(0.12)
    contents.paragraph_format.space_after = Pt(3)


def add_cover(
    document: Document,
    markdown_lines: Sequence[str],
    *,
    kicker_text: str = "PERSONASHIELD QUEST RESEARCH MONOGRAPH",
    title_text: str = "Four-Condition GenAI\nScenario Engine",
    subtitle_text: str = (
        "Technical Architecture, Development Methodology,\n"
        "Evaluation Contracts, Results, and Research Protocol"
    ),
    metadata_text: str = "PSQ-SCO v9.1 | Frozen evaluation run 20260718_065435",
    edition_text: str = "Implementation-grounded edition | 18 July 2026",
) -> None:
    add = document.add_paragraph
    spacer = add()
    spacer.paragraph_format.space_after = Pt(55)

    kicker = add()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_after = Pt(16)
    run = kicker.add_run(kicker_text)
    set_run_font(run, size=10, bold=True, color=BLUE)

    title = add()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(8)
    run = title.add_run(title_text)
    set_run_font(run, size=29, bold=True, color=DARK_BLUE)

    subtitle = add()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(24)
    run = subtitle.add_run(subtitle_text)
    set_run_font(run, size=14, color=MUTED)

    strip = document.add_table(rows=2, cols=4)
    set_repeat_table_header(strip.rows[0])
    values = (("4", "CONDITIONS"), ("3", "LOCAL LLMS"), ("120", "MATCHED CASES"), ("1,440", "LIVE OUTPUTS"))
    for col, (value, label) in enumerate(values):
        cell = strip.cell(0, col)
        cell.text = value
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        shade_cell(cell, LIGHT_BLUE)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        set_run_font(p.runs[0], size=17, bold=True, color=DARK_BLUE)
        label_cell = strip.cell(1, col)
        label_cell.text = label
        label_cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = label_cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        set_run_font(p.runs[0], size=7.5, bold=True, color=MUTED)
        for item in (cell, label_cell):
            set_cell_margins(item, top=90, bottom=90, start=120, end=120)
    set_table_geometry(strip, [2340, 2340, 2340, 2340], PORTRAIT_WIDTH_DXA)
    set_table_borders(strip)

    meta = add()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta.paragraph_format.space_before = Pt(36)
    meta.paragraph_format.space_after = Pt(5)
    run = meta.add_run(metadata_text)
    set_run_font(run, size=10, bold=True, color=DARK_BLUE)

    date = add()
    date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = date.add_run(edition_text)
    set_run_font(run, size=9.5, italic=True, color=MUTED)

    document.add_page_break()

    h = add("Contents", style="Heading 1")
    h.paragraph_format.space_before = Pt(0)
    for line in markdown_lines:
        if not line.startswith("## "):
            continue
        heading = line[3:].strip()
        if heading.startswith("Complete Technical"):
            continue
        p = add(style="PSQ Contents Entry")
        add_inline(p, heading, base_size=10.5, base_color=DARK_BLUE)
    document.add_page_break()


def parse_table(lines: Sequence[str], start: int) -> tuple[list[list[str]], int] | None:
    if start + 1 >= len(lines) or not lines[start].lstrip().startswith("|"):
        return None
    if not re.match(r"^\s*\|?\s*:?-{3,}", lines[start + 1]):
        return None
    table_lines: list[str] = []
    index = start
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        table_lines.append(lines[index])
        index += 1
    rows: list[list[str]] = []
    for row_index, line in enumerate(table_lines):
        if row_index == 1:
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        return None
    return rows, index


def add_markdown_table(document: Document, rows: Sequence[Sequence[str]], *, landscape: bool) -> None:
    total = LANDSCAPE_WIDTH_DXA if landscape else PORTRAIT_WIDTH_DXA
    widths = normalized_widths(rows, total)
    table = document.add_table(rows=len(rows), cols=len(rows[0]))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    font_size = 7.0 if len(rows[0]) >= 8 else 7.8 if len(rows[0]) >= 6 else 8.5 if len(rows[0]) >= 4 else 9.0
    for row_index, row in enumerate(rows):
        word_row = table.rows[row_index]
        keep_row_together(word_row)
        if row_index == 0:
            set_repeat_table_header(word_row)
        for col_index, value in enumerate(row):
            cell = word_row.cells[col_index]
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            set_cell_margins(cell)
            if row_index == 0:
                shade_cell(cell, LIGHT_BLUE)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.0
            add_inline(p, value, base_size=font_size, base_color=DARK_BLUE if row_index == 0 else INK)
            for run in p.runs:
                run.bold = row_index == 0 or run.bold
    set_table_geometry(table, widths, total)
    set_table_borders(table)
    after = document.add_paragraph()
    after.paragraph_format.space_after = Pt(2)


def add_code_block(document: Document, code_lines: Iterable[str]) -> None:
    p = document.add_paragraph(style="PSQ Code")
    text = "\n".join(code_lines).rstrip()
    run = p.add_run(text)
    set_run_font(run, name="Consolas", size=8.5, color=DARK_BLUE)
    paragraph_shading(p, LIGHT_GRAY, left_border=BLUE)


def build_docx(
    markdown_path: Path,
    output_path: Path,
    *,
    title_text: str = "Four-Condition GenAI\nScenario Engine",
    subtitle_text: str = (
        "Technical Architecture, Development Methodology,\n"
        "Evaluation Contracts, Results, and Research Protocol"
    ),
    kicker_text: str = "PERSONASHIELD QUEST RESEARCH MONOGRAPH",
    metadata_text: str = "PSQ-SCO v9.1 | Frozen evaluation run 20260718_065435",
    edition_text: str = "Implementation-grounded edition | 18 July 2026",
    header_label: str = "FOUR-CONDITION GENAI RESEARCH MONOGRAPH",
) -> None:
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    document = Document()
    document.core_properties.title = title_text.replace("\n", " ")
    document.core_properties.subject = "Technical, evaluation, and research methodology monograph"
    document.core_properties.keywords = "PersonaShield Quest, PSQ-SCO, RAG, ontology, scenario generation, evaluation"
    document.core_properties.comments = "Generated from the implementation-grounded Markdown source."

    configure_styles(document)
    set_page_geometry(document.sections[0], landscape=False)
    configure_header_footer(document.sections[0], header_label=header_label)
    add_cover(
        document,
        lines,
        kicker_text=kicker_text,
        title_text=title_text,
        subtitle_text=subtitle_text,
        metadata_text=metadata_text,
        edition_text=edition_text,
    )

    # The cover contains the title and metadata; body begins at the Abstract.
    start = next(i for i, line in enumerate(lines) if line.strip() == "## Abstract")
    index = start
    in_code = False
    code_lines: list[str] = []
    quote_lines: list[str] = []
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if in_code:
            if stripped.startswith("```"):
                add_code_block(document, code_lines)
                code_lines = []
                in_code = False
            else:
                code_lines.append(line)
            index += 1
            continue
        if stripped.startswith("```"):
            in_code = True
            index += 1
            continue

        parsed = parse_table(lines, index)
        if parsed is not None:
            rows, next_index = parsed
            use_landscape = len(rows[0]) >= 7
            if use_landscape:
                section = document.add_section(WD_SECTION.NEW_PAGE)
                set_page_geometry(section, landscape=True)
                configure_header_footer(section, header_label=header_label)
            add_markdown_table(document, rows, landscape=use_landscape)
            if use_landscape:
                section = document.add_section(WD_SECTION.NEW_PAGE)
                set_page_geometry(section, landscape=False)
                configure_header_footer(section, header_label=header_label)
            index = next_index
            continue

        if stripped.startswith(">"):
            quote_lines = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip()[1:].strip())
                index += 1
            p = document.add_paragraph()
            p.paragraph_format.left_indent = Inches(0.18)
            p.paragraph_format.right_indent = Inches(0.18)
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(7)
            add_inline(p, " ".join(quote_lines), base_size=10, base_color=DARK_BLUE)
            paragraph_shading(p, LIGHT_GRAY, left_border=BLUE)
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            if level == 1:
                index += 1
                continue
            style = "Heading 1" if level == 2 else "Heading 2" if level == 3 else "Heading 3"
            p = document.add_paragraph(style=style)
            add_inline(p, text, base_size={"Heading 1": 16, "Heading 2": 13, "Heading 3": 12}[style], base_color=BLUE if style != "Heading 3" else DARK_BLUE)
            index += 1
            continue

        if stripped in {"---", "***"}:
            index += 1
            continue
        if not stripped:
            index += 1
            continue

        bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
        number = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if bullet or number:
            p = document.add_paragraph(style="List Bullet" if bullet else "List Number")
            add_inline(p, (bullet or number).group(1), base_size=10.5)
            index += 1
            continue

        # Join ordinary wrapped Markdown lines into one paragraph until a block boundary.
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            candidate = lines[index]
            c = candidate.strip()
            if not c:
                break
            if c.startswith(("#", "```", ">", "|", "---")):
                break
            if re.match(r"^\s*[-*]\s+", candidate) or re.match(r"^\s*\d+\.\s+", candidate):
                break
            paragraph_lines.append(c)
            index += 1
        p = document.add_paragraph()
        add_inline(p, " ".join(paragraph_lines), base_size=10.5)

    if in_code and code_lines:
        add_code_block(document, code_lines)

    for section in document.sections:
        configure_header_footer(section, header_label=header_label)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    document.save(output_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("docs/PERSONASHIELD_QUEST_FOUR_CONDITION_GENAI_ENGINE_COMPLETE_RESEARCH_MONOGRAPH.md"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("docs/PERSONASHIELD_QUEST_FOUR_CONDITION_GENAI_ENGINE_COMPLETE_RESEARCH_MONOGRAPH.docx"),
    )
    parser.add_argument(
        "--title",
        default="Four-Condition GenAI|Scenario Engine",
        help="Cover title; use | for an intentional line break.",
    )
    parser.add_argument(
        "--subtitle",
        default=(
            "Technical Architecture, Development Methodology,|"
            "Evaluation Contracts, Results, and Research Protocol"
        ),
        help="Cover subtitle; use | for an intentional line break.",
    )
    parser.add_argument(
        "--kicker",
        default="PERSONASHIELD QUEST RESEARCH MONOGRAPH",
    )
    parser.add_argument(
        "--metadata",
        default="PSQ-SCO v9.1 | Frozen evaluation run 20260718_065435",
    )
    parser.add_argument(
        "--edition",
        default="Implementation-grounded edition | 18 July 2026",
    )
    parser.add_argument(
        "--header-label",
        default="FOUR-CONDITION GENAI RESEARCH MONOGRAPH",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_docx(
        args.source.resolve(),
        args.out.resolve(),
        title_text=args.title.replace("|", "\n"),
        subtitle_text=args.subtitle.replace("|", "\n"),
        kicker_text=args.kicker,
        metadata_text=args.metadata,
        edition_text=args.edition,
        header_label=args.header_label,
    )
    print(args.out.resolve())
