#!/usr/bin/env python3
"""全CSVがsoramimic側パーサの前提を満たすか検証する(CI用)。

チェック内容:
- 引用符付きフィールドがない(利用側はクオート非対応の素朴なsplit(","))
- 改行コードがLFのみ・末尾改行なし(最終空行でパーサが落ちる)
- 全行がヘッダと同じ列数(素朴なsplitで列ズレしない)
- 必須列(id, original, surface)が存在し、値が空でない
- pronunciation にASCII英字の連続が無い(英名をそのまま読みに入れると、利用側の
  読み解析が異常に遅くなる。実際に3行で辞書構築が193秒かかっていた)
- image/image_page は生カンマを含まないURL
- 選手descriptionが文脈依存の接続語や未完の語尾を含まない
- 一意であるべき列の妥当性(stationsのwikidata重複など)

usage: python3 tools/validate_csvs.py
"""

import re
import sys
from pathlib import Path

from wpnames import is_standalone_player_description

ROOT = Path(__file__).resolve().parent.parent
REQUIRED = ("id", "original", "surface")
# image/image_page として許可するURLプレフィックス(明示的な許可リスト。any-httpsにはしない)
IMAGE_URL_RE = re.compile(
    r"^https?://commons\.wikimedia\.org/"
    r"|^https://github\.com/soramimic/soramimic-wordlists/releases/"
    # youtuber の象徴カードと baseball/football の選手カードは、リポジトリ内
    # (images/)に置いて raw で参照する(1枚3KB前後のSVGで、CSVと同じ
    # コミットに入る利点を採ってReleaseを介さない。詳細は ADR 00018, 00019)
    r"|^https://raw\.githubusercontent\.com/soramimic/soramimic-wordlists/"
    r"|^https://github\.com/soramimic/soramimic-wordlists/blob/"
)
# 読みにASCII英字が2文字以上続くのは、英名を読みに入れてしまった取り違え
# (例: sekitsui の "Azara's night monkey")。利用側の読み解析がこの手の行で
# 暴走するため、混入を止める。読みはカタカナのみが前提
PRON_ASCII_RE = re.compile(r"[A-Za-z]{2,}")

errors = []


def err(msg):
    errors.append(msg)
    print(f"NG: {msg}")


def validate(path: Path):
    raw = path.read_bytes()
    if b"\r" in raw:
        err(f"{path.name}: CR(\\r)を含む")
    if raw.endswith(b"\n"):
        err(f"{path.name}: 末尾に改行がある")
    text = raw.decode("utf-8")
    if '"' in text:
        err(f"{path.name}: 引用符付きフィールドがある(カンマ入りの値?)")
        return
    lines = text.split("\n")
    header = lines[0].split(",")
    ncol = len(header)
    for col in REQUIRED:
        if col not in header:
            err(f"{path.name}: 必須列 {col} がない")
            return
    idx = {c: i for i, c in enumerate(header)}
    img_cols = [c for c in ("image", "image_page") if c in idx]
    for lineno, line in enumerate(lines[1:], start=2):
        f = line.split(",")
        if len(f) != ncol:
            err(f"{path.name}:{lineno}: 列数が{len(f)}(期待{ncol}): {line[:60]}")
            continue
        for col in REQUIRED:
            if not f[idx[col]]:
                err(f"{path.name}:{lineno}: {col} が空")
        for col in img_cols:
            v = f[idx[col]]
            if v and not IMAGE_URL_RE.match(v):
                err(f"{path.name}:{lineno}: {col} が不正なURL: {v[:60]}")
        if "pronunciation" in idx:
            v = f[idx["pronunciation"]]
            if PRON_ASCII_RE.search(v):
                err(f"{path.name}:{lineno}: pronunciation にASCII英字が連続"
                    f"(英名の混入?): {v[:40]}")
        if path.name in ("baseball.csv", "football.csv") and "description" in idx:
            v = f[idx["description"]]
            if v and not is_standalone_player_description(v):
                err(f"{path.name}:{lineno}: descriptionが単独で完結していない: "
                    f"{v[:65]}")
    print(f"OK: {path.name} ({len(lines) - 1}行)")


def main() -> int:
    for p in sorted(ROOT.glob("*.csv")):
        validate(p)
    # tools のPythonが構文エラーでないこと
    import py_compile
    for p in sorted((ROOT / "tools").glob("*.py")):
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as ex:
            err(f"{p.name}: 構文エラー: {ex}")
    if errors:
        print(f"\n{len(errors)}件のエラー")
        return 1
    print("\nすべてOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
