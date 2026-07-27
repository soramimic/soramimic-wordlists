#!/usr/bin/env python3
"""実写画像が無い行に、分類(class列)レベルの概念イメージ画像を設定する。

種ごとの実写画像は Wikidata の P18 から取れるが、取れない種も多い(sekitsui は
約2,700行、plant は約740行)。個体の写真を用意するのは不可能なので、`class` 列の
単位で1枚ずつ用意した概念イメージ(tools/gen_class_images.py が生成し GitHub
Release で配布)を共有で割り当てる。画像内に「イメージ」と明記してあり、実写
ではないことが見た目で分かるようにしてある。

- **実写がある行は触らない**。image が空の行だけ埋める(冪等)
- 既に概念イメージが入っている行は、class が変わっていたら現在の class の
  ものに貼り替える(実写への上書きはしない)
- ネットワークアクセスなし。月次バッチ(update-wordlists)で updater の後に
  実行し、新規追加行にも概念イメージが付くようにする
- 実写が後から取れたときは概念イメージを上書きしてよい(改善方向。判定は
  enrich_sekitsui_images.py / enrich_plant_images.py 側の is_class_image())

usage:
  python3 tools/apply_class_images.py            # 全対象リスト
  python3 tools/apply_class_images.py plant      # リストを指定
"""

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gen_class_images import GROUPS  # noqa: E402
from wpnames import write_csv_no_trailing_newline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RELEASES = "https://github.com/soramimic/soramimic-wordlists/releases"

# リスト名 -> (CSVファイル名, gen_class_images のグループ名, リリースタグ)
# タグは「絵柄のバージョン」であってリスト単位ではない。plant の6枚は既存の
# class-image-v1 に追加アセットとして載せてある(既存URLは変わらない)。
# 分類不明の class_unknown.svg は sekitsui と共用する
TARGETS = {
    "sekitsui": ("sekitsui.csv", "sekitsui", "class-image-v1"),
    "plant": ("plant.csv", "plant", "class-image-v1"),
}
# 概念イメージのURLはこの接頭辞で始まる(実写かどうかの判定に使う)
URL_PREFIX = f"{RELEASES}/download/class-image-"


def is_class_image(url: str) -> bool:
    """概念イメージのURLか(=実写ではないので上書きしてよいか)。"""
    return url.startswith(URL_PREFIX)


def urls(group: str, tag: str) -> dict[str, tuple[str, str]]:
    """class列の値 -> (image, image_page)。"""
    page = f"{RELEASES}/tag/{tag}"
    return {label: (f"{RELEASES}/download/{tag}/{fname}", page)
            for label, fname, _shape, _palette in GROUPS[group]}


def apply(name: str) -> int:
    csv_name, group, tag = TARGETS[name]
    path = ROOT / csv_name
    by_class = urls(group, tag)
    # class が定義に無い値(将来の分類追加など)は「分類不明」の絵に寄せる
    fallback = by_class.get("NA")

    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [dict(r) for r in reader]
        cols = list(reader.fieldnames)
    for c in ("image", "image_page"):
        if c not in cols:
            cols.append(c)

    filled: Counter[str] = Counter()
    rebound = photo = 0
    for r in rows:
        for c in cols:
            r.setdefault(c, "")
        cur = r["image"]
        if cur and not is_class_image(cur):
            photo += 1
            continue  # 実写がある行は絶対に触らない
        cls = (r.get("class") or "").strip()
        hit = by_class.get(cls, fallback)
        if not hit:
            continue
        if cur == hit[0]:
            continue  # 既に同じ概念イメージ(冪等)
        if cur:
            rebound += 1  # class が変わったので貼り替え
        else:
            filled[cls or "NA"] += 1
        r["image"], r["image_page"] = hit

    write_csv_no_trailing_newline(path, cols, rows)
    total = sum(1 for r in rows if r["image"] and is_class_image(r["image"]))
    breakdown = ", ".join(f"{k} {v}" for k, v in sorted(filled.items()))
    print(f"{csv_name}: 概念イメージを付与 +{sum(filled.values())}行"
          f"{' (' + breakdown + ')' if breakdown else ''}, "
          f"class変更による貼り替え {rebound}行, "
          f"実写あり {photo}行, 概念イメージ計 {total}行")
    return 0


def main() -> int:
    names = sys.argv[1:] or list(TARGETS)
    for n in names:
        if n not in TARGETS:
            print(f"error: unknown list: {n} (available: {', '.join(TARGETS)})",
                  file=sys.stderr)
            return 1
    for n in names:
        apply(n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
