"""植物の安全確認済みWikidata対応と分類の永続override。"""

# 日本語名だけではなく、学名と上位分類を外部分類データでも確認した項目だけを置く。
# 自動取得で候補が消えたり複数化しても、月次更新でこの対応を失わないための台帳。
MANUAL_TAXA = {
    "サクラバラ": {
        "wikidata": "Q87642005",
        "scientific_name": "Rosa uchiyamana",
        "family": "バラ科",
        "family_wikidata": "Q46299",
        "genus": "バラ属",
        "evidence": "Wikidata Q87642005; GBIF taxon 3006955",
    },
    "ムニンノキ": {
        "wikidata": "Q15319651",
        "scientific_name": "Planchonella boninensis",
        "family": "アカテツ科",
        "family_wikidata": "Q158981",
        "genus": "Planchonella",
        "evidence": "Wikidata Q15319651; GBIF accepted taxon 5334075; 環境省RDB第5次",
    },
    "ユズ": {
        "wikidata": "Q867776",
        "scientific_name": "Citrus × junos",
        "family": "ミカン科",
        "family_wikidata": "Q146030",
        "genus": "ミカン属",
        "evidence": "Wikidata Q867776; GBIF accepted taxon 3831766",
    },
}

# P18 だが実写ではないことを確認済みのファイル。QID全体を拒否せずファイル単位に
# することで、後日同じtaxonへ実写が追加・選択された場合は利用できる。
REJECTED_P18_FILES = {
    "Sargassum_fulvellum_as_Fucus_fulvellus_in_Turner_1808.jpg":
        "1808年の植物図版であり実写ではない",
}


def is_rejected_p18(image_url: str) -> bool:
    return any(filename in (image_url or "") for filename in REJECTED_P18_FILES)


def apply_manual_taxon(row: dict[str, str]) -> None:
    """空欄だけを確認済み値で補う。実写等の既存値は変更しない。"""
    manual = MANUAL_TAXA.get(row.get("original", ""), {})
    for column in (
        "wikidata", "scientific_name", "family", "family_wikidata", "genus",
    ):
        if manual.get(column) and not (row.get(column) or "").strip():
            row[column] = manual[column]
