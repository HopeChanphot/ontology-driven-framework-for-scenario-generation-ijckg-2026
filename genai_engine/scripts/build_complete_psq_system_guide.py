"""Build the complete PersonaShield Quest ontology/generation/evaluation guide."""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path
from typing import Iterable, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "PERSONASHIELD_QUEST_COMPLETE_ONTOLOGY_GENERATION_EVALUATION_GUIDE.md"
OUT_DOCX = ROOT / "docs" / "PersonaShield_Quest_Complete_Ontology_Scenario_Generation_and_Evaluation_Guide_v1.0.docx"
FIG_DIR = ROOT / "docs" / "figures"
RESULT_DIR = (
    ROOT
    / "output"
    / "three_layer_eval_3models_120cases_4modes_live_recovered_standard_no_bertscore"
    / "20260712_184750"
)

NAVY = "17365D"
BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
PALE_BLUE = "E8EEF5"
LIGHT_BLUE = "D9EAF7"
TEAL = "2A7F86"
GREEN = "3D7F5F"
GOLD = "B88A2B"
RED = "A64B4B"
GRAY = "5F6B78"
LIGHT_GRAY = "F4F6F9"
WHITE = "FFFFFF"
BLACK = "202124"

CONTENT_WIDTH_DXA = 9360
TABLE_INDENT_DXA = 120


def rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def setup_plot() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 10,
            "axes.titlesize": 14,
            "axes.titleweight": "bold",
            "axes.labelsize": 10,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#CAD3DE",
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def box(
    ax,
    xy: tuple[float, float],
    width: float,
    height: float,
    title: str,
    body: str,
    *,
    face: str = "#E8EEF5",
    edge: str = "#2E74B5",
    title_color: str = "#17365D",
    fontsize: float = 9,
) -> None:
    x, y = xy
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.012,rounding_size=0.02",
        linewidth=1.4,
        edgecolor=edge,
        facecolor=face,
    )
    ax.add_patch(patch)
    ax.text(x + 0.02, y + height - 0.04, title, ha="left", va="top", fontsize=fontsize + 1, weight="bold", color=title_color)
    ax.text(x + 0.02, y + height - 0.105, body, ha="left", va="top", fontsize=fontsize, color="#344454", linespacing=1.25)


def arrow(ax, start: tuple[float, float], end: tuple[float, float], *, color: str = "#65788A", curved: float = 0.0) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=14,
            linewidth=1.35,
            color=color,
            connectionstyle=f"arc3,rad={curved}",
        )
    )


def save_figure(fig, name: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / name, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def make_architecture_figure() -> None:
    fig, ax = plt.subplots(figsize=(12, 6.3))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("PersonaShield Quest: end-to-end research system", color="#17365D", pad=12)
    box(ax, (0.04, 0.58), 0.23, 0.25, "PSQ-SCO v9.1 ontology", "CQ1-CQ4 scope\nTemplates and quality rules\nEvidence and provenance\nRead-only semantic control", face="#E5F1EA", edge="#3D7F5F")
    box(ax, (0.37, 0.58), 0.25, 0.25, "Scenario generation engine", "Frozen case and persona\nOptional vector retrieval\nOntology packet or graph-to-text\nLocal open-weight LLM + repair", face="#E8EEF5")
    box(ax, (0.72, 0.58), 0.23, 0.25, "Structured game scenarios", "Player-facing communication\nChoices, feedback, safe action\nEvidence and ontology traces\nJSONL audit records", face="#FFF4D8", edge="#B88A2B")
    box(ax, (0.14, 0.16), 0.28, 0.23, "Three-layer experiment evaluator", "Ontology validation\nScenario conformance and grounding\nMatched method/model comparison\nDiversity, timing, statistics", face="#E6F2F3", edge="#2A7F86")
    box(ax, (0.58, 0.16), 0.28, 0.23, "PCUE quality validator", "Pedagogy, cyber realism\nUsability and ethical safety\nQualifiers, vetoes, decisions\nRevision and human-review routing", face="#F6E9E9", edge="#A64B4B")
    arrow(ax, (0.27, 0.705), (0.37, 0.705))
    arrow(ax, (0.62, 0.705), (0.72, 0.705))
    arrow(ax, (0.80, 0.58), (0.69, 0.39), curved=0.08)
    arrow(ax, (0.73, 0.58), (0.38, 0.39), curved=-0.08)
    ax.text(0.5, 0.045, "Human experts approve disputed or safety-critical content; learner data calibrate later weighting phases.", ha="center", color="#5F6B78", fontsize=9.5)
    save_figure(fig, "psq_complete_architecture.png")


def make_ontology_validation_figure() -> None:
    fig, ax = plt.subplots(figsize=(12, 5.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Four complementary ontology validation views", color="#17365D", pad=10)
    box(ax, (0.03, 0.58), 0.19, 0.25, "OWL ontology", "73 release-counted classes\n133 named individuals\n3,229 triples\nCQ1-CQ4 bounded scope", face="#E8EEF5")
    box(ax, (0.29, 0.58), 0.19, 0.25, "HermiT", "Logical consistency: PASS\nUnsatisfiable classes: 0\nDuration: 3.636 s", face="#E5F1EA", edge="#3D7F5F")
    box(ax, (0.55, 0.58), 0.19, 0.25, "SPARQL ASK", "Eight competency-query tests\nPassed: 8 of 8\nRDFLib 7.6.0", face="#E5F1EA", edge="#3D7F5F")
    box(ax, (0.81, 0.58), 0.16, 0.25, "CQ completeness", "4,362 / 4,362\nComplete only for\nCQ1-CQ4", face="#FFF4D8", edge="#B88A2B")
    box(ax, (0.22, 0.14), 0.23, 0.22, "Runtime mappings", "1,440 of 1,440 final rows\nmap to frozen case controls\nPipeline preservation evidence", face="#E6F2F3", edge="#2A7F86")
    box(ax, (0.56, 0.14), 0.23, 0.22, "Release evidence", "Reasoner, CQ, completeness,\nnoise, source, and provenance\nreports retained for audit", face="#F4F6F9", edge="#65788A")
    for x in (0.22, 0.48, 0.74):
        arrow(ax, (x, 0.79), (x + 0.07, 0.79))
    arrow(ax, (0.63, 0.58), (0.68, 0.36))
    arrow(ax, (0.38, 0.58), (0.35, 0.36))
    save_figure(fig, "psq_ontology_validation_flow.png")


def make_four_modes_figure() -> None:
    fig, ax = plt.subplots(figsize=(12, 6.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Matched four-mode generation comparison", color="#17365D", pad=12)
    labels = [
        ("1  Prompt-only", "Frozen case + persona\nPrompt template\nNo external retrieval\nNo ontology context", "#F4F6F9", "#65788A"),
        ("2  Prompt + RAG", "Same case and prompt\nExternal Chroma retrieval\nFiltered examples and evidence\nNo ontology context", "#E6F2F3", "#2A7F86"),
        ("3  Direct ontology packet", "Ontology + Prompt + RAG\nSame external RAG\nTemplate, rules, evidence\nSelected ontology constraints", "#E5F1EA", "#3D7F5F"),
        ("4  Ontology-to-text RAG", "Ontology-text + Prompt + RAG\nSame external RAG\nSelected-subgraph walk\nGraph-CoT-inspired trace", "#FFF4D8", "#B88A2B"),
    ]
    xs = [0.025, 0.27, 0.515, 0.76]
    for x, (title, body, face, edge) in zip(xs, labels):
        box(ax, (x, 0.40), 0.215, 0.38, title, body, face=face, edge=edge, fontsize=8.7)
    ax.text(0.5, 0.27, "Every condition receives the same case ID, role, stage, age group, channel, variant, and model pairing.", ha="center", fontsize=10.5, weight="bold", color="#17365D")
    ax.text(0.5, 0.18, "The controlled difference is the information source added to the prompt. Final outputs still pass through deterministic parsing and repair.", ha="center", fontsize=9.5, color="#5F6B78")
    ax.plot([0.06, 0.94], [0.11, 0.11], color="#CBD5DF", linewidth=2)
    for x in [0.13, 0.377, 0.622, 0.868]:
        ax.scatter([x], [0.11], s=80, color="#2E74B5", zorder=3)
    save_figure(fig, "psq_four_modes.png")


def make_paper120_figure() -> None:
    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Why the paper experiment contains 120 matched cases", color="#17365D", pad=12)
    box(ax, (0.03, 0.55), 0.19, 0.25, "30 base groups", "3 channels\n× 2 variants\n× 5 roles\n= 30", face="#E8EEF5")
    box(ax, (0.29, 0.55), 0.19, 0.25, "90 anchor cases", "30 groups\n× 3 difficulty anchors\n= 90", face="#E5F1EA", edge="#3D7F5F")
    box(ax, (0.55, 0.55), 0.19, 0.25, "30 repetitions", "One balanced repetition\nper base group\n= 30", face="#FFF4D8", edge="#B88A2B")
    box(ax, (0.81, 0.55), 0.16, 0.25, "120 cases", "90 anchors\n+ 30 balanced\n= 120", face="#E6F2F3", edge="#2A7F86")
    arrow(ax, (0.22, 0.675), (0.29, 0.675))
    arrow(ax, (0.48, 0.675), (0.55, 0.675))
    arrow(ax, (0.74, 0.675), (0.81, 0.675))
    box(ax, (0.18, 0.14), 0.26, 0.20, "Matched generation", "120 cases × 3 local models\n× 4 methods", face="#F4F6F9", edge="#65788A")
    box(ax, (0.56, 0.14), 0.26, 0.20, "Final experiment", "1,440 live LLM outputs\n0 fallback rows after recovery", face="#E5F1EA", edge="#3D7F5F")
    arrow(ax, (0.44, 0.24), (0.56, 0.24))
    save_figure(fig, "psq_paper120_design.png")


def make_three_layer_figure() -> None:
    fig, ax = plt.subplots(figsize=(12, 5.8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Three-layer experiment evaluation", color="#17365D", pad=12)
    box(ax, (0.04, 0.48), 0.26, 0.34, "Layer 1  Ontology validation", "HermiT consistency\nSPARQL CQ ASK tests\nCQ-bounded completeness\nRuntime mapping checks", face="#E5F1EA", edge="#3D7F5F")
    box(ax, (0.37, 0.48), 0.26, 0.34, "Layer 2  Scenario validation", "JSON and schema\nControl adherence\nConcept P/R/F1\nGrounding, scope, contradiction", face="#E8EEF5", edge="#2E74B5")
    box(ax, (0.70, 0.48), 0.26, 0.34, "Layer 3  Method comparison", "Matched pairs and bootstrap CI\nWilcoxon and Friedman\nEmbedding Diversity and Self-BLEU\nTiming and failure analysis", face="#E6F2F3", edge="#2A7F86")
    arrow(ax, (0.30, 0.65), (0.37, 0.65))
    arrow(ax, (0.63, 0.65), (0.70, 0.65))
    ax.text(0.5, 0.30, "Primary interpretation", ha="center", fontsize=11, weight="bold", color="#17365D")
    ax.text(0.5, 0.22, "Does ontology guidance improve automated conformance and traceability under matched generation conditions?", ha="center", fontsize=10.3, color="#344454")
    ax.text(0.5, 0.12, "This does not replace human content-quality review or learner-outcome validation.", ha="center", fontsize=9.7, color="#A64B4B", weight="bold")
    save_figure(fig, "psq_three_layer_evaluation.png")


def make_method_results_figure() -> None:
    rows = load_csv(RESULT_DIR / "method_summary.csv")
    display = {
        "prompt_only": "Prompt-only",
        "prompt_rag": "Prompt+RAG",
        "ontology_prompt_rag": "Ontology+Prompt+RAG",
        "ontology_text_rag": "Ontology-text+RAG",
    }
    metrics = [
        ("overall_conformance", "Overall conformance"),
        ("required_concept_f1", "Required-concept F1"),
        ("grounding_completeness", "Grounding completeness"),
        ("ontology_semantic_scope", "Ontology semantic scope"),
    ]
    colors = ["#65788A", "#2A7F86", "#3D7F5F", "#B88A2B"]
    fig, ax = plt.subplots(figsize=(12, 6.4))
    x = np.arange(len(metrics))
    width = 0.19
    for idx, row in enumerate(rows):
        vals = [float(row[key]) for key, _ in metrics]
        bars = ax.bar(x + (idx - 1.5) * width, vals, width, label=display[row["method"]], color=colors[idx])
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, val + 0.015, f"{val:.3f}", ha="center", va="bottom", fontsize=7.6, rotation=90)
    ax.set_ylim(0, 1.12)
    ax.set_xticks(x, [label for _, label in metrics])
    ax.set_ylabel("Mean score (0 to 1)")
    ax.set_title("Latest method-level automated evaluation (n = 360 per method)", color="#17365D", pad=12)
    ax.grid(axis="y", color="#E1E6EC", linewidth=0.8)
    ax.legend(ncol=2, frameon=False, loc="upper left")
    ax.text(0.0, -0.17, "Overall conformance is a project composite. Component scores remain the primary evidence.", transform=ax.transAxes, fontsize=9, color="#5F6B78")
    fig.tight_layout()
    save_figure(fig, "psq_method_results.png")


def make_model_heatmap_figure() -> None:
    rows = load_csv(RESULT_DIR / "model_method_matrix.csv")
    columns = ["prompt_only", "prompt_rag", "ontology_prompt_rag", "ontology_text_rag"]
    model_labels = ["Mistral 7B", "Qwen2.5 7B", "Qwen3 8B"]
    method_labels = ["Prompt-only", "Prompt+RAG", "Ontology+Prompt+RAG", "Ontology-text+RAG"]
    data = np.array([[float(row[c]) for c in columns] for row in rows])
    fig, ax = plt.subplots(figsize=(10.5, 4.7))
    im = ax.imshow(data, cmap="Blues", vmin=0.72, vmax=0.92, aspect="auto")
    ax.set_xticks(range(4), method_labels)
    ax.set_yticks(range(3), model_labels)
    ax.set_title("Overall conformance by local model and generation method", color="#17365D", pad=12)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            color = "white" if data[i, j] > 0.87 else "#17365D"
            ax.text(j, i, f"{data[i, j]:.4f}", ha="center", va="center", color=color, fontsize=11, weight="bold")
    cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.04)
    cbar.set_label("Mean overall conformance")
    fig.tight_layout()
    save_figure(fig, "psq_model_method_heatmap.png")


def make_diversity_figure() -> None:
    rows = load_csv(RESULT_DIR / "semantic_diversity_method_summary.csv")
    labels = ["Prompt-only", "Prompt+RAG", "Ontology+Prompt+RAG", "Ontology-text+RAG"]
    embed = [float(row["embedding_diversity_mean"]) for row in rows]
    self_bleu = [float(row["self_bleu_mean"]) for row in rows]
    colors = ["#65788A", "#2A7F86", "#3D7F5F", "#B88A2B"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8))
    x = np.arange(4)
    bars = axes[0].bar(x, embed, color=colors)
    axes[0].set_title("Embedding Diversity (higher is more diverse)", color="#17365D")
    axes[0].set_ylim(0, 0.28)
    axes[0].set_xticks(x, labels, rotation=22, ha="right")
    axes[0].grid(axis="y", color="#E1E6EC")
    for bar, val in zip(bars, embed):
        axes[0].text(bar.get_x() + bar.get_width() / 2, val + 0.006, f"{val:.3f}", ha="center", fontsize=9)
    bars = axes[1].bar(x, self_bleu, color=colors)
    axes[1].set_title("Self-BLEU (lower is less repetitive)", color="#17365D")
    axes[1].set_ylim(0.72, 0.92)
    axes[1].set_xticks(x, labels, rotation=22, ha="right")
    axes[1].grid(axis="y", color="#E1E6EC")
    for bar, val in zip(bars, self_bleu):
        axes[1].text(bar.get_x() + bar.get_width() / 2, val + 0.006, f"{val:.3f}", ha="center", fontsize=9)
    fig.suptitle("Latest set-level diversity analysis using LaBSE and sacreBLEU", fontsize=15, weight="bold", color="#17365D", y=1.02)
    fig.text(0.5, -0.01, "Neither metric has a universal pass threshold; inspect high-similarity pairs and human-rated quality.", ha="center", fontsize=9, color="#5F6B78")
    fig.tight_layout()
    save_figure(fig, "psq_diversity_results.png")


def make_revision_cycle_figure() -> None:
    fig, ax = plt.subplots(figsize=(12, 6.3))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title("Bounded scenario revision and approval workflow", color="#17365D", pad=12)
    nodes = [
        ((0.04, 0.61), "Generate", "Frozen case + selected method\nLocal open-weight LLM"),
        ((0.29, 0.61), "Validate", "Deterministic checks + PCUE\nStore criterion evidence"),
        ((0.54, 0.61), "Decide", "Accept / Minor / Major\nReject-Regenerate"),
        ((0.79, 0.61), "Deploy", "Only after no veto, no open\nblocking issue, and approval"),
        ((0.29, 0.18), "Track issues", "Stable issue code, owner,\nevidence, revision ID"),
        ((0.61, 0.18), "Revise and re-test", "Verify old issues and scan\nfor newly introduced defects"),
    ]
    for idx, (xy, title, body) in enumerate(nodes):
        face, edge = ("#E5F1EA", "#3D7F5F") if title == "Deploy" else ("#E8EEF5", "#2E74B5")
        if title in {"Track issues", "Revise and re-test"}:
            face, edge = "#FFF4D8", "#B88A2B"
        box(ax, xy, 0.18 if idx < 4 else 0.23, 0.22, title, body, face=face, edge=edge, fontsize=8.5)
    arrow(ax, (0.22, 0.72), (0.29, 0.72))
    arrow(ax, (0.47, 0.72), (0.54, 0.72))
    arrow(ax, (0.72, 0.72), (0.79, 0.72))
    arrow(ax, (0.63, 0.61), (0.43, 0.40), curved=0.10)
    arrow(ax, (0.52, 0.29), (0.61, 0.29))
    arrow(ax, (0.73, 0.40), (0.39, 0.61), curved=0.18)
    ax.text(0.51, 0.49, "Minor / Major", ha="center", fontsize=8.5, color="#A64B4B", weight="bold")
    ax.text(0.84, 0.47, "Re-evaluate every criterion", ha="center", fontsize=8.5, color="#5F6B78")
    ax.text(0.5, 0.055, "Loop controls: >2 repeated Minor outcomes -> Major; >1 repeated Major outcome -> Reject-Regenerate.", ha="center", fontsize=9.2, color="#5F6B78")
    save_figure(fig, "psq_revision_cycle.png")


def create_figures() -> None:
    setup_plot()
    make_architecture_figure()
    make_ontology_validation_figure()
    make_four_modes_figure()
    make_paper120_figure()
    make_three_layer_figure()
    make_method_results_figure()
    make_model_heatmap_figure()
    make_diversity_figure()
    make_revision_cycle_figure()


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top: int = 80, start: int = 120, bottom: int = 80, end: int = 120) -> None:
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


def set_table_borders(table, color: str = "B8C4D1", size: str = "4") -> None:
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.find(qn("w:tblBorders"))
    if borders is None:
        borders = OxmlElement("w:tblBorders")
        tbl_pr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        tag = borders.find(qn(f"w:{edge}"))
        if tag is None:
            tag = OxmlElement(f"w:{edge}")
            borders.append(tag)
        tag.set(qn("w:val"), "single")
        tag.set(qn("w:sz"), size)
        tag.set(qn("w:space"), "0")
        tag.set(qn("w:color"), color)


def set_table_geometry(table, widths: Sequence[int]) -> None:
    if sum(widths) != CONTENT_WIDTH_DXA:
        raise ValueError(f"Table widths must sum to {CONTENT_WIDTH_DXA}: {widths}")
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
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
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)
    for row in table.rows:
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        for idx, cell in enumerate(row.cells):
            cell.width = Inches(widths[idx] / 1440)
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(widths[idx]))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def table_widths(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[int]:
    count = len(headers)
    if count == 1:
        return [CONTENT_WIDTH_DXA]
    if count == 2:
        first = headers[0].lower()
        if first in {"term", "purpose", "actor", "criterion", "score interval", "final weighted score"}:
            return [2700, CONTENT_WIDTH_DXA - 2700]
        return [3100, CONTENT_WIDTH_DXA - 3100]
    lengths = []
    all_rows = [headers, *rows]
    for idx in range(count):
        max_len = max(min(len(str(row[idx])) if idx < len(row) else 0, 80) for row in all_rows)
        lengths.append(max(10, max_len))
    total = sum(lengths)
    # Reserve a feasible minimum for every column before distributing the
    # remaining width proportionally. A fixed 900-DXA minimum overcommits the
    # page for tables with more than ten columns and can create a negative last
    # column when the rounding delta is applied.
    minimum = min(900, CONTENT_WIDTH_DXA // count)
    remainder = CONTENT_WIDTH_DXA - (minimum * count)
    widths = [minimum + int(remainder * length / total) for length in lengths]
    delta = CONTENT_WIDTH_DXA - sum(widths)
    widths[max(range(count), key=lambda idx: lengths[idx])] += delta
    return widths


def set_repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def set_paragraph_border(paragraph, *, bottom: bool = True, color: str = "D5DDE6", size: str = "8") -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    edge_name = "bottom" if bottom else "top"
    edge = OxmlElement(f"w:{edge_name}")
    edge.set(qn("w:val"), "single")
    edge.set(qn("w:sz"), size)
    edge.set(qn("w:space"), "4")
    edge.set(qn("w:color"), color)
    p_bdr.append(edge)


def set_paragraph_shading(paragraph, fill: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    shd = p_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        p_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def add_field(paragraph, instruction: str) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend([begin, instr, separate, end])


def add_hyperlink(paragraph, text: str, url: str, *, color: str = BLUE, underline: bool = True):
    part = paragraph.part
    rel_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rel_id)
    new_run = OxmlElement("w:r")
    r_pr = OxmlElement("w:rPr")
    color_node = OxmlElement("w:color")
    color_node.set(qn("w:val"), color)
    r_pr.append(color_node)
    if underline:
        u = OxmlElement("w:u")
        u.set(qn("w:val"), "single")
        r_pr.append(u)
    new_run.append(r_pr)
    text_node = OxmlElement("w:t")
    text_node.text = text
    new_run.append(text_node)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


INLINE_RE = re.compile(r"(\[[^\]]+\]\(https?://[^)]+\)|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)")


def add_inline(paragraph, text: str, *, default_size: float | None = None) -> None:
    for token in INLINE_RE.split(text):
        if not token:
            continue
        link = re.fullmatch(r"\[([^\]]+)\]\((https?://[^)]+)\)", token)
        if link:
            add_hyperlink(paragraph, link.group(1), link.group(2))
            continue
        if token.startswith("`") and token.endswith("`"):
            run = paragraph.add_run(token[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(default_size or 9.2)
            run.font.color.rgb = rgb(DARK_BLUE)
            r_pr = run._r.get_or_add_rPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:fill"), "EEF2F6")
            r_pr.append(shd)
            continue
        if token.startswith("**") and token.endswith("**"):
            run = paragraph.add_run(token[2:-2])
            run.bold = True
        elif token.startswith("*") and token.endswith("*"):
            run = paragraph.add_run(token[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(token)
        if default_size:
            run.font.size = Pt(default_size)


def add_numbering_definitions(doc: Document) -> tuple[int, int]:
    numbering = doc.part.numbering_part.element
    existing_abstract = [int(el.get(qn("w:abstractNumId"))) for el in numbering.findall(qn("w:abstractNum"))]
    existing_num = [int(el.get(qn("w:numId"))) for el in numbering.findall(qn("w:num"))]
    next_abs = max(existing_abstract, default=0) + 1
    next_num = max(existing_num, default=0) + 1

    def create(abstract_id: int, num_id: int, fmt: str, text: str, font: str | None = None) -> None:
        abstract = OxmlElement("w:abstractNum")
        abstract.set(qn("w:abstractNumId"), str(abstract_id))
        multi = OxmlElement("w:multiLevelType")
        multi.set(qn("w:val"), "singleLevel")
        abstract.append(multi)
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), "0")
        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        num_fmt = OxmlElement("w:numFmt")
        num_fmt.set(qn("w:val"), fmt)
        lvl_text = OxmlElement("w:lvlText")
        lvl_text.set(qn("w:val"), text)
        suff = OxmlElement("w:suff")
        suff.set(qn("w:val"), "tab")
        lvl.append(start)
        lvl.append(num_fmt)
        lvl.append(lvl_text)
        lvl.append(suff)
        p_pr = OxmlElement("w:pPr")
        tabs = OxmlElement("w:tabs")
        tab = OxmlElement("w:tab")
        tab.set(qn("w:val"), "num")
        tab.set(qn("w:pos"), "540")
        tabs.append(tab)
        ind = OxmlElement("w:ind")
        ind.set(qn("w:left"), "540")
        ind.set(qn("w:hanging"), "270")
        p_pr.append(tabs)
        p_pr.append(ind)
        lvl.append(p_pr)
        if font:
            r_pr = OxmlElement("w:rPr")
            fonts = OxmlElement("w:rFonts")
            fonts.set(qn("w:ascii"), font)
            fonts.set(qn("w:hAnsi"), font)
            r_pr.append(fonts)
            lvl.append(r_pr)
        abstract.append(lvl)
        numbering.append(abstract)
        num = OxmlElement("w:num")
        num.set(qn("w:numId"), str(num_id))
        abstract_ref = OxmlElement("w:abstractNumId")
        abstract_ref.set(qn("w:val"), str(abstract_id))
        num.append(abstract_ref)
        numbering.append(num)

    create(next_abs, next_num, "bullet", "•", "Symbol")
    create(next_abs + 1, next_num + 1, "decimal", "%1.")
    return next_num, next_num + 1


def apply_num(paragraph, num_id: int) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), "0")
    num_id_node = OxmlElement("w:numId")
    num_id_node.set(qn("w:val"), str(num_id))
    num_pr.append(ilvl)
    num_pr.append(num_id_node)
    p_pr.append(num_pr)


def configure_styles(doc: Document) -> None:
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.font.color.rgb = rgb(BLACK)
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
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = rgb(color)
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True
        style.paragraph_format.keep_together = True

    if "Code Block" not in styles:
        code = styles.add_style("Code Block", WD_STYLE_TYPE.PARAGRAPH)
    else:
        code = styles["Code Block"]
    code.font.name = "Consolas"
    code.font.size = Pt(8.5)
    code.font.color.rgb = rgb(DARK_BLUE)
    code.paragraph_format.left_indent = Inches(0.18)
    code.paragraph_format.right_indent = Inches(0.12)
    code.paragraph_format.space_before = Pt(4)
    code.paragraph_format.space_after = Pt(7)
    code.paragraph_format.line_spacing = 1.05

    if "Figure Caption" not in styles:
        cap = styles.add_style("Figure Caption", WD_STYLE_TYPE.PARAGRAPH)
    else:
        cap = styles["Figure Caption"]
    cap.font.name = "Calibri"
    cap.font.size = Pt(9)
    cap.font.italic = True
    cap.font.color.rgb = rgb(GRAY)
    cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_before = Pt(3)
    cap.paragraph_format.space_after = Pt(10)
    cap.paragraph_format.keep_with_next = False

    if "Table Text" not in styles:
        table_text = styles.add_style("Table Text", WD_STYLE_TYPE.PARAGRAPH)
    else:
        table_text = styles["Table Text"]
    table_text.font.name = "Calibri"
    table_text.font.size = Pt(9)
    table_text.paragraph_format.space_before = Pt(0)
    table_text.paragraph_format.space_after = Pt(0)
    table_text.paragraph_format.line_spacing = 1.08


def configure_section(section) -> None:
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.42)
    section.footer_distance = Inches(0.42)
    section.different_first_page_header_footer = True


def configure_header_footer(section) -> None:
    header = section.header
    p = header.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run("PERSONASHIELD QUEST  |  ONTOLOGY, GENERATION, AND EVALUATION GUIDE")
    run.font.name = "Calibri"
    run.font.size = Pt(8.2)
    run.font.bold = True
    run.font.color.rgb = rgb(GRAY)
    set_paragraph_border(p, color="D5DDE6", size="5")

    footer = section.footer
    p = footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_before = Pt(2)
    run = p.add_run("PSQ research reference  |  ")
    run.font.name = "Calibri"
    run.font.size = Pt(8.2)
    run.font.color.rgb = rgb(GRAY)
    add_field(p, "PAGE")


def add_cover(doc: Document) -> None:
    for _ in range(5):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(6)
    kicker = doc.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_after = Pt(18)
    run = kicker.add_run("RESEARCH SYSTEM GUIDE  |  VERSION 1.0")
    run.font.name = "Calibri"
    run.font.size = Pt(10)
    run.font.bold = True
    run.font.color.rgb = rgb(GOLD)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(10)
    run = title.add_run("PersonaShield Quest")
    run.font.name = "Calibri"
    run.font.size = Pt(31)
    run.font.bold = True
    run.font.color.rgb = rgb(NAVY)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(8)
    run = subtitle.add_run("Ontology, Scenario Generation, and Evaluation")
    run.font.name = "Calibri"
    run.font.size = Pt(17)
    run.font.bold = True
    run.font.color.rgb = rgb(DARK_BLUE)

    desc = doc.add_paragraph()
    desc.alignment = WD_ALIGN_PARAGRAPH.CENTER
    desc.paragraph_format.space_after = Pt(34)
    run = desc.add_run("A complete technical and research guide to PSQ-SCO v9.1, local open-weight generation, the matched 120-case experiment, and PCUE scenario validation")
    run.font.name = "Calibri"
    run.font.size = Pt(11.5)
    run.font.color.rgb = rgb(GRAY)

    rule = doc.add_paragraph()
    rule.paragraph_format.left_indent = Inches(1.3)
    rule.paragraph_format.right_indent = Inches(1.3)
    rule.paragraph_format.space_after = Pt(32)
    set_paragraph_border(rule, color=BLUE, size="18")

    quick = doc.add_paragraph()
    quick.alignment = WD_ALIGN_PARAGRAPH.CENTER
    quick.paragraph_format.space_after = Pt(12)
    run = quick.add_run("1,350 scenario slots  |  120 matched cases  |  3 local models  |  4 generation methods  |  1,440 final live outputs")
    run.font.name = "Calibri"
    run.font.size = Pt(10.2)
    run.font.bold = True
    run.font.color.rgb = rgb(TEAL)

    date = doc.add_paragraph()
    date.alignment = WD_ALIGN_PARAGRAPH.CENTER
    date.paragraph_format.space_before = Pt(36)
    run = date.add_run("Based on the latest inspected local implementation and evaluation\n14 July 2026")
    run.font.name = "Calibri"
    run.font.size = Pt(10)
    run.font.color.rgb = rgb(GRAY)
    doc.add_page_break()


def add_contents(doc: Document, headings: Sequence[str]) -> None:
    p = doc.add_paragraph("Contents", style="Heading 1")
    p.paragraph_format.space_before = Pt(0)
    lead = doc.add_paragraph("This guide is organized from system concepts to implementation, results, operation, and publication readiness.")
    lead.paragraph_format.space_after = Pt(10)
    for heading in headings:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.12)
        p.paragraph_format.space_after = Pt(3)
        run = p.add_run(heading)
        run.font.size = Pt(9.5)
        if heading in {"Document Purpose", "Executive Summary"}:
            run.font.bold = True
            run.font.color.rgb = rgb(DARK_BLUE)
    note = doc.add_paragraph()
    note.paragraph_format.space_before = Pt(8)
    note.paragraph_format.space_after = Pt(8)
    set_paragraph_shading(note, "EEF4F8")
    add_inline(note, "Navigation note: Word users can use the Navigation Pane because every section uses real heading styles.")
    doc.add_page_break()


def add_markdown_table(doc: Document, header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.style = "Table Grid"
    set_table_geometry(table, table_widths(header, rows))
    set_table_borders(table)
    set_repeat_table_header(table.rows[0])
    for col, value in enumerate(header):
        cell = table.cell(0, col)
        set_cell_shading(cell, PALE_BLUE)
        p = cell.paragraphs[0]
        p.style = "Table Text"
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        add_inline(p, value, default_size=9)
        for run in p.runs:
            run.bold = True
            run.font.color.rgb = rgb(NAVY)
    for row_idx, values in enumerate(rows, start=1):
        for col, value in enumerate(values):
            cell = table.cell(row_idx, col)
            if row_idx % 2 == 0:
                set_cell_shading(cell, "F8FAFC")
            p = cell.paragraphs[0]
            p.style = "Table Text"
            if re.fullmatch(r"[0-9.<>=% -]+", value.strip()):
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            add_inline(p, value, default_size=9)
    after = doc.add_paragraph()
    after.paragraph_format.space_after = Pt(2)


def add_figure(doc: Document, path: Path, caption: str) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(5)
    run = p.add_run()
    run.add_picture(str(path), width=Inches(6.25))
    inline = doc.inline_shapes[-1]._inline
    inline.docPr.set("descr", caption)
    inline.docPr.set("title", caption.split(".", 1)[0])
    cap = doc.add_paragraph(caption, style="Figure Caption")
    cap.paragraph_format.keep_with_next = False


def add_code_block(doc: Document, code_lines: Sequence[str]) -> None:
    p = doc.add_paragraph(style="Code Block")
    set_paragraph_shading(p, "F1F4F7")
    p.paragraph_format.keep_together = True
    for idx, line in enumerate(code_lines):
        if idx:
            p.add_run().add_break()
        run = p.add_run(line)
        run.font.name = "Consolas"
        run.font.size = Pt(8.5)


SPECIAL_RE = re.compile(r"^(#{1,3})\s+|^```|^\[\[FIGURE:|^\|.*\|\s*$|^-\s+|^\d+\.\s+")


def parse_table(lines: Sequence[str], start: int) -> tuple[list[str], list[list[str]], int]:
    def split(line: str) -> list[str]:
        return [part.strip() for part in line.strip().strip("|").split("|")]

    header = split(lines[start])
    rows: list[list[str]] = []
    idx = start + 2
    while idx < len(lines) and lines[idx].strip().startswith("|"):
        row = split(lines[idx])
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))
        rows.append(row[: len(header)])
        idx += 1
    return header, rows, idx


def should_page_break_before(title: str) -> bool:
    prefixes = (
        "4. PSQ-SCO",
        "6. Scenario Generation",
        "10. Three-Layer",
        "13. Latest",
        "14. Separate PCUE",
        "16. Revision",
        "18. Research Theory",
        "19. Step-by-Step",
        "20. Latest Artifact",
        "22. Plain-Language",
        "24. References",
    )
    return title.startswith(prefixes)


def render_markdown(
    doc: Document,
    source: str,
    bullet_num_id: int,
    decimal_num_id: int,
    *,
    figure_base: Path | None = None,
) -> None:
    lines = source.splitlines()
    resolved_figure_base = figure_base or (ROOT / "docs")
    idx = 0
    skipped_title = False
    while idx < len(lines):
        raw = lines[idx]
        line = raw.strip()
        if not line:
            idx += 1
            continue
        if line.startswith("# ") and not skipped_title:
            skipped_title = True
            idx += 1
            if idx < len(lines) and lines[idx].startswith("Version "):
                idx += 1
            continue
        if line.startswith("```"):
            code_lines: list[str] = []
            idx += 1
            while idx < len(lines) and not lines[idx].strip().startswith("```"):
                code_lines.append(lines[idx])
                idx += 1
            idx += 1
            add_code_block(doc, code_lines)
            continue
        fig_match = re.fullmatch(r"\[\[FIGURE:([^|]+)\|(.+)\]\]", line)
        if fig_match:
            add_figure(doc, resolved_figure_base / fig_match.group(1), fig_match.group(2))
            idx += 1
            continue
        if line.startswith("|") and idx + 1 < len(lines) and re.match(r"^\|?\s*:?-+", lines[idx + 1].strip()):
            header, rows, idx = parse_table(lines, idx)
            add_markdown_table(doc, header, rows)
            continue
        heading = re.match(r"^(#{2,3})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1)) - 1
            title = heading.group(2)
            if level == 1 and should_page_break_before(title) and len(doc.paragraphs) > 2:
                doc.add_page_break()
            p = doc.add_paragraph(style=f"Heading {level}")
            add_inline(p, title)
            idx += 1
            continue
        unordered = re.match(r"^-\s+(.+)$", line)
        if unordered:
            p = doc.add_paragraph()
            apply_num(p, bullet_num_id)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.line_spacing = 1.25
            add_inline(p, unordered.group(1))
            idx += 1
            continue
        ordered = re.match(r"^\d+\.\s+(.+)$", line)
        if ordered:
            p = doc.add_paragraph()
            apply_num(p, decimal_num_id)
            p.paragraph_format.space_after = Pt(4)
            p.paragraph_format.line_spacing = 1.25
            add_inline(p, ordered.group(1))
            idx += 1
            continue
        para_lines = [line]
        idx += 1
        while idx < len(lines) and lines[idx].strip() and not SPECIAL_RE.match(lines[idx].strip()):
            para_lines.append(lines[idx].strip())
            idx += 1
        text = " ".join(para_lines)
        p = doc.add_paragraph()
        add_inline(p, text)


def build_document() -> Path:
    source_text = SOURCE.read_text(encoding="utf-8")
    doc = Document()
    configure_styles(doc)
    section = doc.sections[0]
    configure_section(section)
    configure_header_footer(section)
    doc.core_properties.title = "PersonaShield Quest: Complete Ontology, Scenario Generation, and Evaluation Guide"
    doc.core_properties.subject = "PSQ-SCO v9.1, local open-weight generation, three-layer evaluation, and PCUE validation"
    doc.core_properties.author = "PersonaShield Quest research project"
    doc.core_properties.keywords = "PersonaShield Quest, ontology, RAG, serious game, scenario generation, evaluation"

    bullet_num_id, decimal_num_id = add_numbering_definitions(doc)
    add_cover(doc)
    contents = [re.sub(r"^##\s+", "", line) for line in source_text.splitlines() if line.startswith("## ")]
    add_contents(doc, contents)
    render_markdown(doc, source_text, bullet_num_id, decimal_num_id)

    for paragraph in doc.paragraphs:
        if paragraph.style.name.startswith("Heading"):
            paragraph.paragraph_format.keep_with_next = True
        for run in paragraph.runs:
            if run.font.name is None:
                run.font.name = "Calibri"

    OUT_DOCX.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT_DOCX)
    return OUT_DOCX


def main() -> None:
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".matplotlib_cache"))
    create_figures()
    output = build_document()
    print(output)


if __name__ == "__main__":
    main()
