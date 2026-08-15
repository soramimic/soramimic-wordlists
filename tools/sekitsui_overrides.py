"""脊椎動物の手動分類と、目・科から大分類を安全に補う処理。"""

from collections import defaultdict

# update_sekitsui.py は rank=種だけを取得するため、種より広い一般名はここで補う。
# 目・科は sekitsui.csv で使っている日本語名に合わせる。
MANUAL_TAXONOMY = {
    "モモンガ": {"class": "哺乳類", "order": "ネズミ目", "family": "リス科"},
    "ヒト": {"class": "哺乳類", "order": "サル目", "family": "ヒト科"},
    "クマ": {"class": "哺乳類", "order": "ネコ目", "family": "クマ科"},
    "ノウサギ": {"class": "哺乳類", "order": "ウサギ目", "family": "ウサギ科"},
    # 「サル」は複数の科を含む一般名なので、科は限定せず目までを補う。
    "サル": {"class": "哺乳類", "order": "サル目"},
}

# 種ランク・和名完全一致の画像取得では拾えない総称の代表画像。
# 値は (Wikidata QID, Wikimedia Commons のファイル名)。
MANUAL_IMAGES = {
    "モモンガ": ("Q1766561", "Pteromys momonga by OpenCage.jpg"),
    "ヒト": ("Q5", "Group of People (NIH BioArt 185).png"),
    "クマ": ("Q11788", "European Brown Bear.jpg"),
    # 種ランクの検索では拾えない家畜名・一般名。広い総称には、その概念の
    # Wikidata項目とCommonsファイルを個別確認した代表画像を明示的に採用する。
    "ネコ": ("Q146", "Cat grooming.jpg"),
    "イエネコ": ("Q57818409", "Cat November 2010-1a.jpg"),
    "イエイヌ": ("Q144", "Greenland 467 (35130903436) (cropped).jpg"),
    "ウシ": ("Q830", "Cow female black white.jpg"),
    "ウマ": ("Q726", "Biandintz eta zaldiak - modified2.jpg"),
    "ブタ": ("Q787", "Sow with piglet.jpg"),
    "ヒツジ": ("Q7368", "Yorkshire dales sheep.jpg"),
    "ヤギ": ("Q2934", "Billy goat.jpg"),
    "ウサギ": ("Q9394", "Ikesbunny.jpg"),
    "ノウサギ": ("Q46076", "Hare Hare (20300967221).jpg"),
    "ハムスター": (
        "Q6573",
        "Syrian hamster filling his cheek pouches with Dandelion leaves cropped.jpg",
    ),
    "ラクダ": ("Q7375", "Chameau de bactriane.JPG"),
    "キリン": ("Q862089", "Giraffe Mikumi National Park.jpg"),
    "ゾウ": (
        "Q7378",
        "178 Male African bush elephant in Etosha National Park Photo by Giles Laurent.jpg",
    ),
    "サイ": ("Q34718", "Waterberg Nashorn1.jpg"),
    "シマウマ": ("Q32789", "Plains Zebra Equus quagga.jpg"),
    "シカ": ("Q29838690", "Rothirsch.jpg"),
    "キツネ": ("Q8331", "Genus vulpes.jpg"),
    "イタチ": ("Q145201", "Mustela nivalis -British Wildlife Centre-4.jpg"),
    "カワウソ": ("Q200184", "LutraCanadensis fullres.jpg"),
    "リス": ("Q9482", "Sciurus carolinensis.jpg"),
    "ビーバー": ("Q47542", "American Beaver.jpg"),
    "モグラ": ("Q104825", "Talpa europaea MHNT.jpg"),
    "ハリネズミ": ("Q6120", "Erinaceus europaeus (Linnaeus, 1758).jpg"),
    "ニワトリ": ("Q780", "Kruppert Cubalaya cropped.JPG"),
    "ゴリラ": ("Q36611", "Lowland Gorilla (8973697544).jpg"),
    "パンダ": ("Q33602", "Giant Panda 2004-03-2.jpg"),
    "イルカ": ("Q7369", "Parc Asterix 20.jpg"),
    "クジラ": ("Q160", "Graywhale MMC.jpg"),
    "サル": ("Q1367", "Cebus albifrons edit.jpg"),
    "ネズミ": ("Q2751034", "Мышь 2.jpg"),
    "オランウータン": (
        "Q41050",
        "Bornean, Sumatran & Tapanuli orangs (horizontal).jpg",
    ),
    "コウモリ": ("Q28425", "Big-eared-townsend-fledermaus.jpg"),
    "カンガルー": ("Q5070208", "Kangaroo and joey03.jpg"),
    "ナマケモノ": ("Q2274076", "Bradypus.jpg"),
    "アリクイ": ("Q203033", "Myresluger2.jpg"),
    "アルマジロ": ("Q1242326", "Cingulata2.jpg"),
    "アザラシ": ("Q25587", "Нерпичий взгляд.jpg"),
    "オットセイ": ("Q1043473", "Adult male Northern Fur Seal.jpg"),
    "マナティー": (
        "Q42797",
        "Endangered Florida manatee (Trichechus manatus) (7636816484).jpg",
    ),
    "キーウィ": ("Q43642", "Kiwifugl.jpg"),
    "ウナギ": ("Q1140081", "Anguilla japonica.jpg"),
    "メダカ": ("Q1142975", "Nihonmedaka.jpg"),
    "ヌー": ("Q7609", "Blue Wildebeest, Ngorongoro.jpg"),
    "バイソン": ("Q18099", "American bison k5680-1.jpg"),
    "ガゼル": (
        "Q29001815",
        "Gacela de Thomson (Eudorcas thomsonii), parque nacional de Amboseli, "
        "Kenia, 2024-05-23, DD 11.jpg",
    ),
    "ヒヒ": ("Q159429", "Papio anubis (Serengeti, 2009).jpg"),
    "ジャッカル": ("Q125525", "Jackal Cape cross 2009.JPG"),
    "ハイエナ": ("Q42046", "Crocuta-hejda.jpg"),
    "スカンク": ("Q83244", "Striped skunk, close (21303507080).jpg"),
    "マングース": ("Q80479", "Dwarf mongoose Korkeasaari zoo.jpg"),
    "アナグマ": ("Q1576038", "Meles meles anakuma at Inokashira Park Zoo.jpg"),
    "マウス": ("Q83310", "Maus außer Haus.JPG"),
    "ラット": ("Q184224", "Rattus norvegicus 1.jpg"),
    "シマリス": (
        "Q22364",
        "Chipmunk with stuffed cheeks in Prospect Park (05980).jpg",
    ),
    "ヤマアラシ": ("Q302006", "Porcupine Berlin Zoo.jpg"),
    "ナキウサギ": (
        "Q184067",
        "American pika (ochotona princeps) with a mouthful of flowers.jpg",
    ),
    "ワラビー": ("Q623169", "Bennetwallaby.jpg"),
    "オポッサム": ("Q21834", "Opossum 2.jpg"),
    "ラバ": ("Q41692", "Juancito.jpg"),
    "マーモット": (
        "Q131567",
        "071 Wild marmot at Grand Muveran Nature Reserve Photo by Giles Laurent.jpg",
    ),
    "ハクジラ": ("Q144144", "Tursiops truncatus 01.jpg"),
    # CSV内に同じ動物の別名で検証済み画像があるもの。
    "シロクマ": ("Q33609", "Polar Bear - Alaska (cropped).jpg"),
    "オルカ": ("Q26843", "Killerwhales jumping.jpg"),
    "ベルーガ": ("Q132072", "Beluga oceanografic.jpg"),
    "アホロートル": (
        "Q22718",
        "Ambystoma mexicanum Natural History Museum University of Pisa (cropped).jpg",
    ),
    "ナミチンパンジー": (
        "Q4126704",
        "013 Alpha male chimpanzee at Kibale forest National Park Photo by Giles Laurent.jpg",
    ),
}


def apply_manual_ranks(name: str, row: dict[str, str]) -> None:
    """手動定義がある語の目・科を行へ適用する。"""
    manual = MANUAL_TAXONOMY.get(name, {})
    for column in ("order", "family"):
        if manual.get(column):
            row[column] = manual[column]


def build_rank_class_maps(
    rows: list[dict[str, str]],
) -> dict[str, dict[str, str]]:
    """既知行から、分類が一意に決まる目・科と大分類の対応を作る。"""
    observed: dict[str, dict[str, set[str]]] = {
        "order": defaultdict(set),
        "family": defaultdict(set),
    }
    for row in rows:
        animal_class = (row.get("class") or "").strip()
        if not animal_class or animal_class == "NA":
            continue
        for rank in observed:
            value = (row.get(rank) or "").strip()
            if value:
                observed[rank][value].add(animal_class)
    return {
        rank: {
            value: next(iter(classes))
            for value, classes in values.items()
            if len(classes) == 1
        }
        for rank, values in observed.items()
    }


def class_from_ranks(
    row: dict[str, str], rank_classes: dict[str, dict[str, str]],
) -> str | None:
    """目・科の既知対応が矛盾なく同じ大分類を示す場合だけ返す。"""
    candidates = {
        rank_classes.get(rank, {}).get((row.get(rank) or "").strip())
        for rank in ("order", "family")
        if (row.get(rank) or "").strip()
    }
    candidates.discard(None)
    return next(iter(candidates)) if len(candidates) == 1 else None
