"""
CodeSweep — Exporters

1. build_pdf() — turns a scan result into a downloadable PDF, so someone
   can share a report without needing to share the live link.
2. build_badge_svg() — a small "shields.io style" badge image showing
   the last known score, for pasting into a GitHub README.
"""

import textwrap
from fpdf import FPDF
from fpdf.enums import XPos, YPos


def _safe_wrap(text: str, width: int = 95) -> str:
    """fpdf's PDF writer can't wrap a single unbroken run of characters
    (like a long file path with no spaces) — force a break every `width`
    characters regardless of word boundaries, so it never chokes."""
    return "\n".join(
        textwrap.fill(line, width=width, break_long_words=True, break_on_hyphens=False)
        for line in text.split("\n")
    )


def build_pdf(repo_url: str, health: dict, duplicates: list, complex_fns: list, dead_fns: list) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "CodeSweep Report", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, repo_url, ln=True)
    pdf.ln(4)

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"Health Score: {health['score']}/100 - {health['verdict']}", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, f"Duplicated blocks: {health['duplicate_count']}   "
                    f"Complex functions: {health['complex_count']}   "
                    f"Dead code: {health['dead_count']}", ln=True)
    pdf.ln(6)

    def section(title, items, render_row):
        nonlocal pdf
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 9, title, ln=True)
        pdf.set_font("Helvetica", "", 9)
        if not items:
            pdf.cell(0, 7, "None found.", ln=True)
        for item in items[:15]:
            pdf.multi_cell(0, 6, _safe_wrap(render_row(item)), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)

    section("Duplicated Code", duplicates,
             lambda d: f"- {d['places']} places: " + ", ".join(d["files"]))
    section("Complex Functions", complex_fns,
             lambda f: f"- {f['function']}() in {f['file']} (line {f['line']}) - {f['decision_points']} decision points")
    section("Possibly Dead Code", dead_fns,
             lambda f: f"- {f['function']}() in {f['file']} (line {f['line']}) - never called elsewhere")

    return bytes(pdf.output())


def build_badge_svg(score: int) -> str:
    if score >= 85:
        color = "#4c9a5a"
    elif score >= 65:
        color = "#c9a15a"
    elif score >= 40:
        color = "#d08a3e"
    else:
        color = "#a8453a"

    label = "codesweep"
    value = f"{score}/100"
    label_w, value_w = 72, 56
    total_w = label_w + value_w

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="a"><rect width="{total_w}" height="20" rx="3" fill="#fff"/></mask>
  <g mask="url(#a)">
    <rect width="{label_w}" height="20" fill="#2b2b2b"/>
    <rect x="{label_w}" width="{value_w}" height="20" fill="{color}"/>
    <rect width="{total_w}" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_w/2}" y="14">{label}</text>
    <text x="{label_w + value_w/2}" y="14">{value}</text>
  </g>
</svg>'''
