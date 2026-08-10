#!/usr/bin/env python3
"""Generate compact semantic SVG figures for weak definition-box images.

The input JSONL stores short labels and visual relationships.  Long dictionary
definitions are deliberately metadata-only: the rendered card must communicate
sequence, contrast, hierarchy, cause, or system structure at a glance.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    from . import gen_gimukyoiku_math_figs as g
except ImportError:
    import gen_gimukyoiku_math_figs as g

DEFAULT_SPECS = Path(__file__).with_name("gimukyoiku_semantic_fig_specs.jsonl")
KINDS = {"sequence", "cycle", "cause_effect", "hierarchy", "comparison",
         "network", "timeline", "formula", "classification", "scale",
         "process", "system"}


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def short_lines(value: object, width: int = 7) -> list[str]:
    text = str(value)
    if len(text) <= width:
        return [text]
    return [text[:width], text[width:width * 2]]


def icon(name: str, x: float, y: float, color: str = g.INK) -> list[str]:
    """Small deterministic line pictograms selected by forgiving keywords."""
    n = name.lower().replace("_", " ")
    out: list[str] = []
    if "and gate" in n:
        out += [g.path(f"M{x-11},{y-11} H{x} A11,11 0 0 1 {x},{y+11} H{x-11}Z", color, 1.4, "#fff"),
                g.line(x - 15, y - 6, x - 11, y - 6, color, 1.2),
                g.line(x - 15, y + 6, x - 11, y + 6, color, 1.2),
                g.line(x + 11, y, x + 15, y, color, 1.2)]
    elif "not gate" in n:
        out += [g.poly([(x - 12, y - 11), (x - 12, y + 11), (x + 7, y)], color, 1.4, "#fff"),
                g.circle(x + 11, y, 3, color, 1.2, "#fff")]
    elif "switch" in n:
        out += [g.circle(x - 9, y + 5, 2.5, color, 1.1, "#fff"),
                g.circle(x + 9, y + 5, 2.5, color, 1.1, "#fff"),
                g.line(x - 7, y + 3, x + 5, y - 7, g.ACCENT, 1.8)]
    elif "led" in n:
        out += [g.circle(x, y, 7, color, 1.2, "#fff")]
        for a in (-45, 45):
            dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
            out.append(g.arrow(x + 7 * dx, y + 7 * dy, x + 14 * dx, y + 14 * dy, g.ACCENT, 1.1))
    elif "burette" in n:
        out += [g.rect(x - 3, y - 14, 6, 24, color, 1.2, "#fff", rx=1),
                g.line(x - 8, y + 7, x + 8, y + 7, color, 1.3),
                g.line(x, y + 10, x, y + 15, color, 1.2)]
        for dy in (-9, -4, 1):
            out.append(g.line(x - 3, y + dy, x, y + dy, color, .8))
    elif any(k in n for k in ("document", "paper", "law", "certificate", "book")):
        out += [g.rect(x - 9, y - 12, 18, 24, color, 1.3, "#fff", rx=2),
                g.line(x - 5, y - 4, x + 5, y - 4, color, 1.1),
                g.line(x - 5, y + 1, x + 5, y + 1, color, 1.1),
                g.line(x - 5, y + 6, x + 2, y + 6, color, 1.1)]
    elif any(k in n for k in ("person", "people", "citizen", "worker", "speaker")):
        out += [g.circle(x, y - 6, 5, color, 1.2, "#fff"),
                g.path(f"M{x-9},{y+12} Q{x},{y-1} {x+9},{y+12}", color, 1.5)]
    elif any(k in n for k in ("factory", "industry", "plant")):
        out += [g.rect(x - 12, y - 2, 24, 14, color, 1.2, "#fff"),
                g.poly([(x - 12, y - 2), (x - 5, y - 9), (x - 5, y - 2),
                        (x + 2, y - 9), (x + 2, y - 2)], color, 1.2, "#fff"),
                g.rect(x + 6, y - 13, 5, 11, color, 1.1, "#fff")]
    elif any(k in n for k in ("money", "coin", "income", "tax", "budget")):
        out += [g.circle(x, y, 11, color, 1.4, "#fff"), g.t(x, y + 5, "¥", 14, color)]
    elif any(k in n for k in ("leaf", "farm", "crop", "food")):
        out += [g.path(f"M{x},{y+11} Q{x-2},{y-2} {x+9},{y-10} Q{x+13},{y+4} {x},{y+11}Z", color, 1.3, "#fff"),
                g.line(x, y + 11, x + 7, y - 6, color, 1.0)]
    elif any(k in n for k in ("database", "data", "table")):
        out += [f'<ellipse cx="{x}" cy="{y-8}" rx="11" ry="4" fill="#fff" stroke="{color}" stroke-width="1.2"/>',
                g.path(f"M{x-11},{y-8} V{y+8} Q{x},{y+15} {x+11},{y+8} V{y-8}", color, 1.2)]
    elif any(k in n for k in ("lock", "security", "shield", "rights")):
        out += [g.rect(x - 10, y - 2, 20, 14, color, 1.3, "#fff", rx=3),
                g.path(f"M{x-6},{y-2} V{y-7} Q{x-6},{y-14} {x},{y-14} Q{x+6},{y-14} {x+6},{y-7} V{y-2}", color, 1.3)]
    elif any(k in n for k in ("government", "court", "state", "institution")):
        out += [g.poly([(x - 13, y - 6), (x, y - 14), (x + 13, y - 6)], color, 1.2, "#fff"),
                g.line(x - 12, y + 10, x + 12, y + 10, color, 1.3)]
        for dx in (-8, 0, 8):
            out.append(g.line(x + dx, y - 5, x + dx, y + 8, color, 2.0))
    elif any(k in n for k in ("temperature", "thermometer", "heat")):
        out += [g.circle(x, y + 8, 5, color, 1.2, "#fff"),
                g.rect(x - 2.5, y - 13, 5, 20, color, 1.2, "#fff", rx=3),
                g.line(x, y + 7, x, y - 7, g.ACCENT, 2.0)]
    elif any(k in n for k in ("sound", "wave", "music")):
        out.append(g.path(f"M{x-13},{y} Q{x-8},{y-13} {x-3},{y} T{x+7},{y} T{x+17},{y}", color, 1.7))
    elif any(k in n for k in ("atom", "chemical", "molecule", "cell")):
        out += [g.circle(x, y, 3, color, 1, color)]
        for a in (0, 60, -60):
            out.append(f'<ellipse cx="{x}" cy="{y}" rx="13" ry="5" fill="none" stroke="{color}" stroke-width="1.1" transform="rotate({a} {x} {y})"/>')
    elif any(k in n for k in ("home", "house", "family")):
        out += [g.poly([(x - 13, y - 2), (x, y - 14), (x + 13, y - 2)], color, 1.3, "#fff"),
                g.rect(x - 10, y - 2, 20, 14, color, 1.3, "#fff")]
    elif any(k in n for k in ("graph", "growth", "economy", "cycle")):
        out += [g.line(x - 12, y + 11, x - 12, y - 11, color, 1.1),
                g.line(x - 12, y + 11, x + 13, y + 11, color, 1.1),
                g.path(f"M{x-9},{y+6} L{x-2},{y} L{x+4},{y+3} L{x+11},{y-8}", g.ACCENT, 1.8)]
    elif any(k in n for k in ("computer", "protocol", "network", "logic")):
        out += [g.rect(x - 13, y - 10, 26, 18, color, 1.2, "#fff", rx=2),
                g.line(x - 5, y + 12, x + 5, y + 12, color, 1.3),
                g.line(x, y + 8, x, y + 12, color, 1.3)]
    elif any(k in n for k in ("eye", "reader", "look", "observe")):
        out += [g.path(f"M{x-14},{y} Q{x},{y-12} {x+14},{y} Q{x},{y+12} {x-14},{y}Z", color, 1.3, "#fff"),
                g.circle(x, y, 4, color, 1.1, g.ACCENT)]
    elif any(k in n for k in ("heart", "pulse")):
        out.append(g.path(f"M{x},{y+11} C{x-17},{y} {x-10},{y-13} {x},{y-5} C{x+10},{y-13} {x+17},{y} {x},{y+11}Z", color, 1.3, "#fff"))
    elif any(k in n for k in ("water", "drop", "rain", "sweat")):
        out.append(g.path(f"M{x},{y-13} C{x-8},{y-2} {x-10},{y+3} {x-10},{y+7} C{x-10},{y+18} {x+10},{y+18} {x+10},{y+7} C{x+10},{y+3} {x+8},{y-2} {x},{y-13}Z", color, 1.3, "#fff"))
    elif any(k in n for k in ("balance", "scale")):
        out += [g.line(x, y - 12, x, y + 11, color, 1.3),
                g.line(x - 12, y - 7, x + 12, y - 7, color, 1.3),
                g.path(f"M{x-12},{y-7} L{x-17},{y+5} H{x-7}Z", color, 1.1, "#fff"),
                g.path(f"M{x+12},{y-7} L{x+7},{y+5} H{x+17}Z", color, 1.1, "#fff")]
    elif "key" in n:
        out += [g.circle(x - 5, y - 2, 6, color, 1.4, "#fff"),
                g.line(x, y + 2, x + 13, y + 11, color, 2.0),
                g.line(x + 8, y + 8, x + 12, y + 4, color, 1.5)]
    elif any(k in n for k in ("gear", "process", "function")):
        out += [g.circle(x, y, 10, color, 1.4, "#fff"), g.circle(x, y, 4, color, 1.2, "#fff")]
        for a in range(0, 360, 45):
            dx, dy = 13 * math.cos(math.radians(a)), 13 * math.sin(math.radians(a))
            out.append(g.line(x + dx * .7, y + dy * .7, x + dx, y + dy, color, 2.2))
    elif any(k in n for k in ("funnel", "filter")):
        out += [g.path(f"M{x-14},{y-11} H{x+14} L{x+5},{y} V{y+12} H{x-3} V{y}Z", color, 1.3, "#fff")]
    elif any(k in n for k in ("flask", "beaker", "burette", "acid", "base")):
        out += [g.path(f"M{x-5},{y-13} V{y-3} L{x-12},{y+11} H{x+12} L{x+5},{y-3} V{y-13}Z", color, 1.3, "#fff"),
                g.line(x - 8, y + 5, x + 8, y + 5, g.ACCENT, 1.3)]
    elif any(k in n for k in ("sun", "light", "uv")):
        out += [g.circle(x, y, 7, color, 1.2, "#fff")]
        for a in range(0, 360, 45):
            dx, dy = math.cos(math.radians(a)), math.sin(math.radians(a))
            out.append(g.line(x + 10 * dx, y + 10 * dy, x + 14 * dx, y + 14 * dy, color, 1.2))
    elif any(k in n for k in ("dog", "animal")):
        out += [g.circle(x, y, 9, color, 1.2, "#fff"),
                g.poly([(x - 8, y - 7), (x - 14, y - 13), (x - 11, y)], color, 1.1, "#fff"),
                g.poly([(x + 8, y - 7), (x + 14, y - 13), (x + 11, y)], color, 1.1, "#fff")]
    elif any(k in n for k in ("map", "field", "land", "province")):
        out += [g.path(f"M{x-13},{y-10} L{x-4},{y-13} L{x+4},{y-9} L{x+13},{y-12} V{y+10} L{x+4},{y+13} L{x-4},{y+9} L{x-13},{y+12}Z", color, 1.2, "#fff"),
                g.line(x - 4, y - 12, x - 4, y + 9, color, 1.0),
                g.line(x + 4, y - 9, x + 4, y + 12, color, 1.0)]
    else:
        # Unknown icon words are intentionally left blank. A neutral empty node
        # is less misleading than inventing the same diamond for every concept.
        pass
    return out


def node(x: float, y: float, label: str, icon_name: str = "", *, accent=False,
         radius: float = 22, label_y: float | None = None) -> list[str]:
    stroke = g.ACCENT if accent else g.SUB
    fill = g.FILL2 if accent else g.FILL
    body = [g.circle(x, y, radius, stroke, 1.4, fill)]
    body += icon(icon_name, x, y, g.INK)
    lines = short_lines(label)
    start_y = label_y if label_y is not None else y + radius + 14
    for i, line in enumerate(lines):
        body.append(g.t(x, start_y + i * 10, esc(line), 9.2,
                        g.ACCENT if accent else g.INK))
    return body


def shaped_node(x: float, y: float, label: str, shape: str, icon_name: str = "",
                *, accent: bool = False, radius: float = 15,
                attrs: dict | None = None) -> list[str]:
    """Draw the few conventional symbols whose geometry carries meaning."""
    stroke = g.ACCENT if accent else g.SUB
    fill = g.FILL2 if accent else g.FILL
    s = shape.lower()
    attrs = attrs or {}
    body: list[str] = []
    label_radius = radius
    if s in {"table", "crosstab", "comparison_matrix"}:
        mode = attrs.get("mode", "")
        if mode == "crosstab":
            columns = [attrs.get("row_axis", "")] + attrs.get("column_headers", []) + ["合計"]
            rows = [[head] + list(values) + [total] for head, values, total in zip(
                attrs.get("row_headers", []), attrs.get("cells", []), attrs.get("row_totals", []))]
            rows.append(["合計"] + attrs.get("column_totals", []) + [attrs.get("grand_total", "")])
        elif mode == "comparison_matrix":
            columns = [""] + attrs.get("column_headers", [])
            rows = [[head] + list(values) for head, values in zip(
                attrs.get("row_headers", []), attrs.get("cells", []))]
        else:
            columns = attrs.get("columns", ["", "", ""])
            rows = attrs.get("rows", [["", "", ""], ["", "", ""]])
        cols = max(2, len(columns)); row_count = max(2, len(rows) + 1)
        if mode == "comparison_matrix":
            w, h = 120, 48
        elif mode == "crosstab":
            w, h = 92, 48
        else:
            w, h = min(72, 18 * cols), min(48, 9 * row_count)
        x0, y0 = x - w / 2, y - h / 2
        body.append(g.rect(x0, y0, w, h, stroke, 1.2, "#fff", rx=1))
        key_col = attrs.get("key_column")
        hi_row = attrs.get("highlighted_row")
        if isinstance(key_col, int):
            body.append(g.rect(x0 + w * key_col / cols, y0, w / cols, h,
                               "none", 0, "#fce3dd"))
        if isinstance(hi_row, int):
            ry = y0 + h * (hi_row + 1) / row_count
            body.append(g.rect(x0, ry, w, h / row_count, "none", 0, "#e7eff8"))
        for i in range(1, cols):
            body.append(g.line(x0 + w * i / cols, y0, x0 + w * i / cols, y0 + h, stroke, .7))
        for i in range(1, row_count):
            body.append(g.line(x0, y0 + h * i / row_count, x0 + w, y0 + h * i / row_count, stroke, .7))
        values = [columns] + rows
        for ri, row in enumerate(values[:row_count]):
            for ci, value in enumerate(row[:cols]):
                tx = x0 + w * (ci + .5) / cols
                ty = y0 + h * (ri + .72) / row_count
                if ri == 0 and len(str(value)) > 4:
                    for li, text_line in enumerate(short_lines(value, 4)):
                        body.append(g.t(tx, ty - 2.5 + li * 5, esc(text_line), 4.7, g.INK))
                else:
                    body.append(g.t(tx, ty, esc(value), 5.4, g.INK))
        label_radius = h / 2 + 3
    elif s == "benzene":
        pts = [(x + 14 * math.cos(math.radians(60 * i - 30)),
                y + 14 * math.sin(math.radians(60 * i - 30))) for i in range(6)]
        body += [g.poly(pts, stroke, 1.5, "#fff"), g.circle(x, y, 7, stroke, 1.1, "none")]
        sub = attrs.get("substituent")
        if sub:
            body += [g.line(x + 12, y - 7, x + 21, y - 12, stroke, 1.1),
                     g.t(x + 26, y - 12, esc(sub), 7.5, g.INK)]
    elif s in {"charge_plus", "charge_minus"}:
        body += [g.circle(x, y, 13, stroke, 1.4, fill),
                 g.t(x, y + 5, "+" if s.endswith("plus") else "−", 16, stroke)]
    elif s == "junction":
        body += [g.line(x - 15, y, x + 15, y, stroke, 1.5),
                 g.line(x, y - 15, x, y + 15, stroke, 1.5),
                 g.dot(x, y, 4, g.ACCENT)]
    elif s == "coil":
        body.append(g.path(f"M{x-16},{y} q4,-12 8,0 t8,0 t8,0 t8,0", stroke, 1.8))
    elif s == "charged_rod":
        body.append(g.rect(x - 5, y - 16, 10, 32, stroke, 1.4, fill, rx=4))
        symbols = attrs.get("symbols", ["−", "−", "−"])
        for i, mark in enumerate(symbols[:3]):
            body.append(g.t(x, y - 8 + i * 8, esc(mark), 8, stroke))
    elif s == "conductor":
        # Keep the interior transparent so charge-separation arrows, which are
        # deliberately routed inside the conductor, remain visible.
        body.append(g.rect(x - 28, y - 14, 56, 28, stroke, 1.4, "none", rx=12))
        label_radius = 17
    elif s == "circuit_loop":
        body += [g.rect(x - 24, y - 15, 48, 30, stroke, 1.3, "none", rx=5),
                 g.line(x - 8, y - 18, x - 8, y - 12, stroke, 2.0),
                 g.line(x - 3, y - 20, x - 3, y - 10, stroke, 1.0),
                 g.rect(x + 7, y - 18, 13, 6, stroke, 1.0, "#fff", rx=1)]
        if attrs.get("loop_arrow"):
            body.append(g.arrow(x - 18, y + 15, x + 18, y + 15, g.ACCENT, 1.1))
        label_radius = 18
    elif s == "panel_title":
        body.append(g.rect(x - 25, y - 10, 50, 20, stroke, 1.2, fill, rx=9))
        body.append(g.t(x, y + 4, esc(label), 8.8, g.INK, weight="600"))
        label = ""
    elif s in {"ph_gauge", "range_gauge", "glucose_gauge"}:
        body += [g.line(x - 17, y, x + 17, y, stroke, 2.2),
                 g.dot(x, y, 4, g.ACCENT)]
    elif s in {"carbon_skeleton", "molecule"}:
        body.append(g.path(f"M{x-16},{y+7} L{x-8},{y-5} L{x},{y+7} L{x+8},{y-5} L{x+16},{y+7}", stroke, 1.7))
    elif s in {"magnetic_field", "music_phrase"}:
        body.append(g.path(f"M{x-17},{y} Q{x-9},{y-13} {x-1},{y} T{x+15},{y}", stroke, 1.6))
    elif s == "music_staff":
        for dy in (-8, -4, 0, 4, 8):
            body.append(g.line(x - 18, y + dy, x + 18, y + dy, g.SUB, .6))
        pattern = attrs.get("pattern", "chords" if attrs.get("render") == "chords" else "quarter-quarter-half")
        notes = [(-10, 3), (0, -3), (10, 2)]
        for i, (dx, dy) in enumerate(notes):
            if pattern == "chords":
                for extra in (-4, 0, 4):
                    body.append(g.circle(x + dx, y + dy + extra, 2.2, stroke, .8, stroke))
            else:
                body.append(g.circle(x + dx, y + dy, 2.5, stroke, .8,
                                     "#fff" if pattern.endswith("half") and i == 2 else stroke))
            body.append(g.line(x + dx + 2, y + dy, x + dx + 2, y + dy - 9, stroke, .9))
        if pattern.startswith("eighth"):
            body += [g.line(x - 8, y - 6, x + 2, y - 12, stroke, 1.5),
                     g.line(x + 2, y - 12, x + 12, y - 7, stroke, 1.5)]
        elif pattern == "ornamented":
            body += [g.t(x - 14, y - 9, "♪", 8, g.ACCENT),
                     g.path(f"M{x+5},{y-12} q4,-5 8,0", g.ACCENT, 1.0)]
    elif s == "organ":
        which = attrs.get("path_id", "organ")
        if which == "liver":
            body.append(g.path(f"M{x-15},{y-7} Q{x},{y-15} {x+15},{y-4} Q{x+8},{y+12} {x-12},{y+8}Z", stroke, 1.2, "#ead0bd"))
        else:
            body.append(g.path(f"M{x-16},{y+2} Q{x-7},{y-10} {x},{y-1} Q{x+8},{y+8} {x+16},{y-3}", stroke, 3.0))
    elif s == "hormone_dots":
        count = int(attrs.get("dot_count", 5))
        for i in range(min(7, count)):
            a = 2 * math.pi * i / max(1, count)
            body.append(g.dot(x + 9 * math.cos(a), y + 7 * math.sin(a), 2.2, g.ACCENT))
    elif s == "equation":
        body.append(g.rect(x - 28, y - 10, 56, 20, stroke, 1.1, "#fff", rx=7))
        body.append(g.t(x, y + 4, esc(label), 8.5, g.INK, font=g.MATHFONT))
        label = ""
    elif s == "periodic_table_7_13":
        cell = 3.2
        for row in range(7):
            for col in range(18):
                if row == 0 and col not in (0, 17):
                    continue
                body.append(g.rect(x - 29 + col * cell, y - 12 + row * cell,
                                   cell, cell, stroke, .35,
                                   "#fce3dd" if (row, col) == (6, 12) else "#fff"))
        label_radius = 15
    elif s == "element_card":
        body += [g.rect(x - 16, y - 17, 32, 34, stroke, 1.3, fill, rx=3),
                 g.t(x - 10, y - 7, esc(attrs.get("atomic_number", attrs.get("element_number", "113"))), 6.5, g.SUB, anchor="start"),
                 g.t(x, y + 7, esc(attrs.get("symbol", "Nh")), 14, g.INK, weight="600")]
        label_radius = 19
    elif s == "fiber":
        body += [g.path(f"M{x-16},{y-6} Q{x-8},{y-13} {x},{y-6} T{x+16},{y-6}", stroke, 1.3),
                 g.path(f"M{x-16},{y} Q{x-8},{y-7} {x},{y} T{x+16},{y}", g.ACCENT, 1.3),
                 g.path(f"M{x-16},{y+6} Q{x-8},{y-1} {x},{y+6} T{x+16},{y+6}", stroke, 1.3)]
    elif s == "wave_smooth":
        body.append(g.path(f"M{x-17},{y} Q{x-9},{y-13} {x-1},{y} T{x+15},{y}", stroke, 1.8))
    elif s == "wave_complex":
        body.append(g.path(f"M{x-17},{y} q4,-13 8,0 t7,0 t5,0 t3,0 t9,0", stroke, 1.8))
    elif s == "diamond":
        body.append(g.poly([(x, y - 14), (x + 18, y), (x, y + 14), (x - 18, y)], stroke, 1.4, fill))
    elif s in {"flask_pink", "flask_pale_pink"}:
        body += icon("flask", x, y, stroke)
        body.append(g.path(f"M{x-8},{y+5} H{x+8} L{x+11},{y+11} H{x-11}Z", "none", 0, "#f3b7b1"))
    else:
        aliases = {
            "key": "key", "money": "money", "document": "document",
            "document_locked": "document lock", "document_publish": "document eye",
            "file": "document", "ledger": "book", "shield": "shield",
            "shopping_basket": "food", "savings_jar": "money",
            "tax_receipt": "tax document", "pancreas": "organ",
            "liver": "organ", "beaker": "beaker", "acid_drop": "acid drop",
            "base_drop": "base drop", "sensor": "eye", "effector": "gear",
            "control_center": "computer", "product_design": "document",
            "tag": "document", "name_tag": "document", "fiber_bar": "fiber",
        }
        offset = float(attrs.get("label_offset_y", 0))
        label_y = (y - radius - 8 + offset if attrs.get("label_position") == "top"
                   else y + radius + 14 + offset)
        return node(x, y, label, icon_name or aliases.get(s, s.replace("_", " ")),
                    accent=accent, radius=radius, label_y=label_y)
    offset = float(attrs.get("label_offset_y", 0))
    label_y = (y - label_radius - 8 + offset if attrs.get("label_position") == "top"
               else y + label_radius + 14 + offset)
    for i, line in enumerate(short_lines(label)):
        body.append(g.t(x, label_y + i * 10, esc(line), 9.2,
                        g.ACCENT if accent else g.INK))
    return body


def subtitle(spec: dict) -> list[str]:
    title = str(spec.get("title", "")).strip()
    if not title or title == spec["word"]:
        return []
    return [g.t(160, 39, esc(title), 9.5, g.SUB)]


def render_graph(spec: dict) -> list[str]:
    """Render an explicitly positioned semantic graph.

    Coordinates in the spec are normalized so the data stays independent of
    the small 320x200 output size.  Edges are painted first and disappear
    cleanly beneath nodes; this avoids the misleading topology produced when a
    detailed relation is forced into a generic row or radial template.
    """
    raw_nodes = spec.get("nodes", [])
    lookup = {str(n["id"]): n for n in raw_nodes}

    def point(node_id: object) -> tuple[float, float]:
        n = lookup[str(node_id)]
        return 25 + 270 * float(n["x"]), 50 + 100 * float(n["y"])

    def extent(node_id: object) -> float:
        n = lookup[str(node_id)]
        shape = str(n.get("shape", n.get("node_shape", ""))).lower()
        if n.get("attrs", {}).get("visible") is False or shape == "point":
            return 2.0
        if shape in {"table", "crosstab", "comparison_matrix", "circuit_loop", "conductor"}:
            return 27.0
        if shape in {"panel_title", "charged_rod"}:
            return 20.0
        return float(n.get("radius", 15)) + 2

    def clipped(a: object, b: object) -> tuple[float, float, float, float]:
        x1, y1 = point(a); x2, y2 = point(b)
        distance = max(1.0, math.hypot(x2 - x1, y2 - y1))
        ux, uy = (x2 - x1) / distance, (y2 - y1) / distance
        ra, rb = extent(a), extent(b)
        if ra + rb + 4 >= distance:
            ra = rb = max(2.0, distance * .22)
        return x1 + ux * ra, y1 + uy * ra, x2 - ux * rb, y2 - uy * rb

    body: list[str] = subtitle(spec)
    for edge in spec.get("edges", []):
        cx1, cy1 = point(edge["from"])
        cx2, cy2 = point(edge["to"])
        kind = edge.get("type", "arrow")
        edge_attrs = edge.get("attrs", {})
        if edge_attrs.get("marker_end") == "inhibit":
            kind = "inhibit"
        x1, y1, x2, y2 = clipped(edge["from"], edge["to"])
        if edge_attrs.get("route") == "inside_bottom":
            route_y = max(cy1, cy2) + 9
            body += [g.line(cx1, cy1 + 4, cx1, route_y, g.ACCENT, 1.2),
                     g.arrow(cx1, route_y, cx2 - extent(edge["to"]), route_y, g.ACCENT, 1.4)]
        elif kind == "noncontact":
            pass
        elif kind == "dashed":
            body.append(g.line(x1, y1, x2, y2, g.SUB, 1.2, dash="4 3"))
        elif kind == "line":
            body.append(g.line(cx1, cy1, cx2, cy2, g.SUB, 1.4))
        elif kind == "bidirectional":
            body.append(g.arrow(x1, y1, x2, y2, g.ACCENT, 1.5, head="both"))
        elif kind == "inhibit":
            body.append(g.line(x1, y1, x2, y2, g.ACCENT, 1.6))
            length = max(1.0, math.hypot(x2 - x1, y2 - y1))
            px, py = -(y2 - y1) / length, (x2 - x1) / length
            body.append(g.line(x2 - 6 * px, y2 - 6 * py,
                               x2 + 6 * px, y2 + 6 * py, g.ACCENT, 2.0))
        else:
            body.append(g.arrow(x1, y1, x2, y2, g.ACCENT, 1.5))
        label = str(edge.get("label", "")).strip()
        if label:
            offset_y = float(edge_attrs.get("label_offset_y", edge_attrs.get("offset_y", 0)))
            if edge_attrs.get("route") == "inside_bottom":
                offset_y += 25
            body.append(g.t((cx1 + cx2) / 2, (cy1 + cy2) / 2 - 5 + offset_y,
                            esc(label), 8.0, g.SUB))

    for item in raw_nodes:
        if item.get("attrs", {}).get("visible") is False:
            continue
        x, y = point(item["id"])
        radius = float(item.get("radius", 15))
        if "radius" in item.get("attrs", {}):
            radius = max(10.0, float(item["attrs"]["radius"]) * 100)
        body += shaped_node(x, y, str(item.get("label", "")),
                            str(item.get("shape", item.get("node_shape", ""))),
                            str(item.get("icon", "")),
                            accent=bool(item.get("accent")),
                            radius=radius,
                            attrs=item.get("attrs"))
    return body


def render(spec: dict) -> str:
    word, kind = spec["word"], spec["kind"]
    labels = [str(x) for x in spec.get("labels", [])]
    icons = [str(x) for x in spec.get("icons", [])]
    icons += [""] * max(0, len(labels) - len(icons))
    if spec.get("nodes") and spec.get("edges") is not None:
        return g.titled(word, render_graph(spec))

    body: list[str] = subtitle(spec)

    if kind in {"sequence", "process"}:
        n = max(1, len(labels)); xs = [40 + i * 240 / max(1, n - 1) for i in range(n)]
        for i, (x, label) in enumerate(zip(xs, labels)):
            body += node(x, 91, label, icons[i], accent=i == n - 1, radius=18 if n > 4 else 21)
            if i + 1 < n:
                body.append(g.arrow(x + 23, 91, xs[i + 1] - 23, 91, g.ACCENT, 1.5))
    elif kind == "timeline":
        n = max(1, len(labels)); xs = [35 + i * 250 / max(1, n - 1) for i in range(n)]
        body += [g.arrow(27, 105, 297, 105, g.SUB, 1.4)]
        for i, (x, label) in enumerate(zip(xs, labels)):
            body += [g.dot(x, 105, 4, g.ACCENT), g.line(x, 99, x, 76 if i % 2 == 0 else 134, g.SUB, 1.0)]
            y = 68 if i % 2 == 0 else 149
            for j, line in enumerate(short_lines(label, 6)):
                body.append(g.t(x, y + j * 10, esc(line), 8.8))
    elif kind == "cycle":
        n = min(5, max(2, len(labels))); pts=[]
        for i in range(n):
            a = -math.pi / 2 + 2 * math.pi * i / n
            pts.append((160 + 84 * math.cos(a), 103 + 52 * math.sin(a)))
        for i, ((x, y), label) in enumerate(zip(pts, labels)):
            nx, ny = pts[(i + 1) % n]
            body.append(g.arrow(x, y, nx, ny, g.ACCENT, 1.3))
            body += node(x, y, label, icons[i], accent=i == 0, radius=16)
    elif kind == "cause_effect":
        causes = labels[:-1] or labels[:1]; effect = labels[-1] if labels else word
        ys = [63 + i * 75 / max(1, len(causes) - 1) for i in range(len(causes))]
        for i, (label, y) in enumerate(zip(causes, ys)):
            body += node(76, y, label, icons[i], radius=17)
            body.append(g.arrow(98, y, 212, 100, g.ACCENT, 1.4))
        body += node(244, 100, effect, icons[len(labels)-1] if labels else "", accent=True, radius=24)
    elif kind in {"hierarchy", "classification"}:
        root = labels[0] if labels else word; children = labels[1:]
        body += node(160, 64, root, icons[0] if icons else "", accent=True, radius=21)
        xs = [40 + i * 240 / max(1, len(children) - 1) for i in range(len(children))]
        for i, (x, label) in enumerate(zip(xs, children), 1):
            body.append(g.line(160, 87, x, 119, g.SUB, 1.3))
            body += node(x, 130, label, icons[i], radius=16)
    elif kind == "comparison":
        left = labels[0] if labels else "A"; right = labels[1] if len(labels) > 1 else "B"
        body += node(82, 101, left, icons[0] if icons else "", radius=29)
        body += node(238, 101, right, icons[1] if len(icons) > 1 else "", accent=True, radius=29)
        body += [g.arrow(117, 101, 203, 101, g.ACCENT, 1.6, head="both")]
        if len(labels) > 2:
            body.append(g.t(160, 148, esc(" / ".join(labels[2:])), 9.2, g.SUB))
    elif kind in {"network", "system"}:
        center = labels[0] if labels else word; outer = labels[1:]
        body += node(160, 101, center, icons[0] if icons else "", accent=True, radius=24)
        n = max(1, len(outer))
        for i, label in enumerate(outer):
            a = -math.pi / 2 + 2 * math.pi * i / n
            x, y = 160 + 95 * math.cos(a), 101 + 57 * math.sin(a)
            body.append(g.line(160, 101, x, y, g.SUB, 1.3))
            body += node(x, y, label, icons[i + 1], radius=15)
    elif kind == "scale":
        n = max(2, len(labels)); xs = [36 + i * 248 / (n - 1) for i in range(n)]
        body += [g.arrow(28, 103, 294, 103, g.ACCENT, 2.0)]
        for i, (x, label) in enumerate(zip(xs, labels)):
            body += [g.line(x, 95, x, 111, g.INK, 1.2)]
            for j, line in enumerate(short_lines(label, 6)):
                body.append(g.t(x, 129 + j * 10, esc(line), 8.8))
            if icons[i]: body += icon(icons[i], x, 72)
    elif kind == "formula":
        main = labels[0] if labels else spec.get("title", word)
        size = 21 if len(main) <= 16 else 15
        body += [g.rect(38, 60, 244, 58, g.ACCENT, 1.5, g.FILL2, rx=10),
                 g.t(160, 96, esc(main), size, g.INK, font=g.MATHFONT)]
        if len(labels) > 1:
            body.append(g.t(160, 144, esc("　".join(labels[1:])), 9.5, g.SUB))
    else:
        raise ValueError(f"unknown kind: {kind}")
    return g.titled(word, body)


def load_specs(path: Path) -> list[dict]:
    specs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    words = [x["word"] for x in specs]
    assert len(words) == len(set(words)), "duplicate words"
    assert all(x.get("kind") in KINDS for x in specs)
    assert all(isinstance(x.get("labels"), list) and x["labels"] for x in specs)
    assert all(all(len(str(label)) <= 12 for label in x["labels"]) for x in specs)
    return specs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--specs", type=Path, default=DEFAULT_SPECS)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sheet", action="store_true")
    args = ap.parse_args()
    specs = load_specs(args.specs)
    args.out.mkdir(parents=True, exist_ok=True)
    cards = []
    for spec in specs:
        content = render(spec)
        ET.fromstring(content)
        name = f"{g.key(spec['word'])}.svg"
        (args.out / name).write_text(content, encoding="utf-8")
        cards.append((spec["word"], name))
    if args.sheet:
        cells = "".join(f'<figure><img src="{name}"><figcaption>{esc(word)}</figcaption></figure>' for word, name in cards)
        (args.out / "index.html").write_text(
            '<meta charset="utf-8"><style>body{font-family:sans-serif;background:#eee}'
            'main{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:8px}'
            'figure{margin:0;background:white;padding:5px}img{width:100%}figcaption{text-align:center}</style>'
            f'<main>{cells}</main>', encoding="utf-8")
    print(f"{len(specs)} semantic SVGs written to {args.out}")


if __name__ == "__main__":
    main()
