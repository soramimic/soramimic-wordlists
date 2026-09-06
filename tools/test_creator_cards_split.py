import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_youtuber_cards as cards
from creator_csv import write_creator_csvs


class SplitCreatorCardsTest(unittest.TestCase):
    def test_prune_retains_cards_from_both_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = (root / "youtuber.csv", root / "vtuber.csv")
            columns = ["id", "original", "category", "org"]
            rows = [
                {"id": "1", "original": "動画の人", "category": "youtuber", "org": "NA"},
                {"id": "2", "original": "仮想の人", "category": "vtuber", "org": "NA"},
            ]
            write_creator_csvs(columns, rows, paths=paths)
            originals = [path.read_bytes() for path in paths]
            out_dir = root / "cards"
            out_dir.mkdir()
            expected = {cards.asset_name(row["original"]) for row in rows}
            for name in expected | {"yt_stale.svg"}:
                (out_dir / name).write_text("old", encoding="utf-8")

            with mock.patch.object(cards, "CSV_PATHS", paths), \
                    mock.patch.object(cards, "load_colors", return_value={}), \
                    mock.patch.object(cards, "build_card", return_value="<svg/>"), \
                    mock.patch.object(sys, "argv", [
                        "gen_youtuber_cards.py", "--no-apply", "--prune",
                        "--out", str(out_dir),
                    ]), contextlib.redirect_stdout(io.StringIO()):
                result = cards.main()

            self.assertEqual(result, 0)
            self.assertEqual({path.name for path in out_dir.iterdir()}, expected)
            self.assertEqual([path.read_bytes() for path in paths], originals)


if __name__ == "__main__":
    unittest.main()
