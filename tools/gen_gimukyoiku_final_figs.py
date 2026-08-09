#!/usr/bin/env python3
"""Generate the final deterministic SVGs used to eliminate image gaps."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    from . import gen_gimukyoiku_math_figs as g
except ImportError:
    import gen_gimukyoiku_math_figs as g

PLAN = Path(__file__).with_name("gimukyoiku_final_image_plan.json")
KINDS = {"flow", "compare", "sequence", "table", "formula", "grammar",
         "cycle", "spokes", "timeline"}
EXPECTED_PLAN_COUNT = 122
EXPECTED_SVG_COUNT = 16
EXPECTED_SVG_SET_SHA256 = "c606dc06210fda495bcd1bf1b93cc1241640ef625c737edaa726534682ceac2c"


def wrapped(text: str, width: int = 31, max_lines: int | None = None) -> list[str]:
    lines, line = [], ""
    for char in text:
        if len(line) >= width and char not in "、。，．・）」』】":
            lines.append(line)
            line = ""
        line += char
    if line:
        lines.append(line)
    return lines if max_lines is None else lines[:max_lines]


def box(x, y, width, height, text, *, fill=g.FILL, color=g.INK, size=11):
    limit = max(5, int(width / (size * .92)))
    lines = wrapped(text, limit, 3)
    actual = min(size, 10 if len(lines) > 1 else size)
    start = y + height / 2 - (len(lines) - 1) * actual * .55 + actual * .34
    body = [g.rect(x, y, width, height, g.SUB, 1.1, fill, rx=7)]
    body += [
        g.t(x + width / 2, start + i * actual * 1.12, line, actual, color)
        for i, line in enumerate(lines)
    ]
    return body


def render(word: str, spec: dict) -> str:
    kind = spec["kind"]
    items = spec.get("items", [])
    main = spec.get("main", "")
    note = spec.get("note", "")
    body: list[str] = []

    if kind in {"flow", "sequence", "timeline"}:
        width = 252 / max(len(items), 1)
        for i, label in enumerate(items):
            x = 22 + i * width
            body += box(
                x, 70, width - 10, 48, label,
                fill=g.FILL2 if i == len(items) - 1 else g.FILL,
                color=g.ACCENT if i == len(items) - 1 else g.INK,
                size=10 if len(label) > 8 else 11,
            )
            if i + 1 < len(items):
                body.append(g.arrow(x + width - 9, 94, x + width + 1, 94, g.ACCENT, 1.4))
        if main:
            body.append(g.t(160, 50, main, 11, g.ACCENT))
    elif kind == "compare":
        body += box(22, 60, 124, 68, items[0], fill=g.FILL, size=10.5)
        body += box(174, 60, 124, 68, items[1], fill=g.FILL2, size=10.5, color=g.ACCENT)
        body.append(g.t(160, 96, spec.get("symbol", "↔"), 18, g.ACCENT))
        if main:
            body.append(g.t(160, 151, main, 11, g.INK))
    elif kind == "formula":
        body += box(
            35, 55, 250, 58, main, fill=g.FILL2, color=g.ACCENT,
            size=16 if len(main) < 24 else 12,
        )
        if items:
            body.append(g.t(160, 139, "　｜　".join(items), 10.5, g.INK))
    elif kind == "grammar":
        body.append(g.t(160, 48, main, 11, g.SUB))
        width = 270 / max(len(items), 1)
        focus = spec.get("focus", len(items) - 1)
        for i, label in enumerate(items):
            x = 20 + i * width
            body += box(
                x, 70, width - 8, 52, label,
                fill=g.FILL2 if i == focus else g.FILL,
                color=g.ACCENT if i == focus else g.INK,
                size=10 if len(label) > 10 else 12,
            )
        if spec.get("example"):
            body.append(g.t(160, 150, spec["example"], 10.5, g.ACCENT))
    elif kind == "table":
        rows = items
        columns = max(len(row) for row in rows)
        cell_width, row_height = 270 / columns, min(31, 100 / len(rows))
        for row_index, row in enumerate(rows):
            for column, label in enumerate(row):
                fill = g.FILL2 if row_index == 0 else ("#ffffff" if row_index % 2 else g.FILL)
                x, y = 25 + column * cell_width, 49 + row_index * row_height
                body.append(g.rect(x, y, cell_width, row_height, g.SUB, .9, fill))
                body.append(g.t(
                    x + cell_width / 2, y + row_height / 2 + 3.5,
                    label, 9.5, g.ACCENT if row_index == 0 else g.INK,
                ))
        if main:
            body.append(g.t(160, 164, main, 10, g.ACCENT))
    elif kind == "cycle":
        points = [(160, 54), (245, 102), (160, 150), (75, 102)]
        cycle_items = items[:4]
        for i, label in enumerate(cycle_items):
            x, y = points[i]
            body += box(x - 42, y - 17, 84, 34, label, fill=g.FILL2 if i == 0 else g.FILL, size=9.5)
            nx, ny = points[(i + 1) % len(cycle_items)]
            body.append(g.arrow(
                x + (12 if nx > x else -12), y,
                nx + (-34 if nx > x else 34), ny, g.ACCENT, 1.2,
            ))
        if main:
            body.append(g.t(160, 105, main, 10, g.ACCENT))
    elif kind == "spokes":
        body += box(113, 74, 94, 45, main, fill=g.FILL2, color=g.ACCENT, size=11)
        positions = [(60, 48), (260, 48), (55, 145), (265, 145)]
        for (x, y), label in zip(positions, items):
            body += box(x - 43, y - 16, 86, 32, label, fill=g.FILL, size=9.5)
            body.append(g.line(160, 96, x, y, g.SUB, 1.1))
    else:
        raise ValueError(f"unknown diagram kind: {kind}")

    for i, line in enumerate(wrapped(note, 38, 3)):
        body.append(g.t(160, 166 + i * 11, line, 8.4, g.SUB))
    return g.titled(word, body)


def manuscript_paper() -> str:
    body: list[str] = []
    for block in range(2):
        x0, y0, cell = 30 + block * 137, 44, 13
        body.append(g.rect(x0, y0, 130, 104, "#c86f73", 1.5, "#fffdf9"))
        for column in range(1, 10):
            body.append(g.line(x0 + column * cell, y0, x0 + column * cell, y0 + 104, "#d99a9d", .7))
        for row in range(1, 8):
            body.append(g.line(x0, y0 + row * cell, x0 + 130, y0 + row * cell, "#d99a9d", .7))
    body += [
        g.line(160, 44, 160, 148, "#c86f73", 1.0, "3 3"),
        g.t(160, 166, "1マスに1字　句読点も1マス", 10.5, g.ACCENT),
    ]
    return g.titled("原稿用紙", body, "縦書きの作文に使うマス目の用紙")


def etenraku() -> str:
    body: list[str] = []
    for i, height in enumerate((50, 62, 72, 78, 74, 64, 52)):
        x = 53 + i * 7
        body.append(g.line(x, 126, x, 126 - height, "#b78642", 4.0, cap="butt"))
    body += [
        g.path("M48,126 Q76,148 104,126 L98,151 Q76,166 54,151 Z", "#8d5d34", 1.5, "#d9a45f"),
        g.t(76, 174, "笙", 11, g.ACCENT),
        g.rect(141, 67, 16, 86, "#8d5d34", 1.3, "#d9a45f", rx=4),
        g.rect(138, 55, 22, 16, "#8d5d34", 1.2, "#f0cf8a", rx=3),
        g.dot(149, 90, 2.0, g.INK), g.dot(149, 108, 2.0, g.INK), g.dot(149, 126, 2.0, g.INK),
        g.t(149, 174, "篳篥", 11, g.ACCENT),
        g.line(203, 105, 284, 82, "#8d5d34", 8.0, cap="round"),
        g.dot(224, 99, 2.2, "#fffdf9"), g.dot(244, 94, 2.2, "#fffdf9"),
        g.dot(264, 88, 2.2, "#fffdf9"), g.t(246, 174, "龍笛", 11, g.ACCENT),
        g.t(160, 44, "雅楽を代表する管絃曲", 11, g.SUB),
    ]
    return g.titled("越天楽", body, "笙・篳篥・龍笛などで奏する")


MEDIA_FIGURES = {"原稿用紙": manuscript_paper, "越天楽": etenraku}


def load_plan() -> list[dict]:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert len(plan) == EXPECTED_PLAN_COUNT
    assert len({row["word"] for row in plan}) == len(plan)
    selected = [row for row in plan if row["mode"] == "svg"]
    digest = hashlib.sha256(
        "\n".join(sorted(row["word"] for row in selected)).encode()
    ).hexdigest()
    assert len(selected) == EXPECTED_SVG_COUNT
    assert digest == EXPECTED_SVG_SET_SHA256
    assert all(row.get("diagram", {}).get("kind") in KINDS for row in selected)
    assert all(row.get("prompt") for row in plan if row["mode"] == "generate")
    return plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    figures = {
        row["word"]: render(row["word"], row["diagram"])
        for row in load_plan()
        if row["mode"] == "svg"
    }
    figures.update({word: draw() for word, draw in MEDIA_FIGURES.items()})
    for word, svg in figures.items():
        ET.fromstring(svg)
        if f">{word}</text>" not in svg:
            raise SystemExit(f"invalid title: {word}")
        (out / f"{g.key(word)}.svg").write_text(svg, encoding="utf-8")
    print(f"{len(figures)} final SVGs written to {out}")


if __name__ == "__main__":
    main()
