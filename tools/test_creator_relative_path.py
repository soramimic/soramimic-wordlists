import contextlib
import functools
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_youtuber_japan as target
from creator_csv import read_creator_csvs, write_creator_csvs
from test_update_youtuber_japan import COLUMNS, person


class CreatorRelativePathTest(unittest.TestCase):
    def test_relative_canonical_csv_uses_global_ids_and_preserves_both_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            paths = (root / "youtuber.csv", root / "vtuber.csv")
            columns = [*COLUMNS, "channel_shared"]
            rows = [
                {**dict.fromkeys(columns, "NA"), "id": pid,
                 "original": name, "surface": name, "pronunciation": "ジンブツ",
                 "type": "full", "category": category}
                for pid, name, category in (
                    ("3", "動画の人", "youtuber"),
                    ("4", "仮想の人", "vtuber"),
                )
            ]
            write_creator_csvs(columns, rows, paths)
            vtuber_before = paths[1].read_bytes()
            people_path = root / "people.json"
            people_path.write_text(json.dumps({
                "schema_version": 1, "people": [person(name="追加の人")],
            }, ensure_ascii=False), encoding="utf-8")
            sources_path = root / "sources.jsonl"
            args = ["--csv", "youtuber.csv", "--people", str(people_path),
                    "--channel-sources", str(sources_path),
                    "--observed-on", "2026-08-17"]

            with contextlib.chdir(root), \
                    mock.patch.object(target, "CSV_PATH", paths[0]), \
                    mock.patch.object(target, "read_creator_csvs", side_effect=
                                      functools.partial(read_creator_csvs, paths)), \
                    mock.patch.object(target, "write_creator_csvs", side_effect=
                                      functools.partial(write_creator_csvs, paths=paths)), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(target.main(args), 0)
                first = [path.read_bytes() for path in (*paths, sources_path)]
                self.assertEqual(target.main(args), 0)

            self.assertEqual([path.read_bytes() for path in (*paths, sources_path)], first)
            self.assertEqual(paths[1].read_bytes(), vtuber_before)
            actual_columns, actual_rows = read_creator_csvs(paths)
            self.assertEqual(actual_columns, columns)
            for original in rows:
                self.assertIn(original, actual_rows)
            added = [row for row in actual_rows if row["original"] == "追加の人"]
            self.assertTrue(added)
            self.assertEqual({row["id"] for row in added}, {"5"})
            self.assertEqual({row["category"] for row in added}, {"youtuber"})
            sources = [json.loads(line) for line in sources_path.read_text(
                encoding="utf-8").splitlines()]
            self.assertEqual({record["person_id"] for record in sources}, {"5"})
            self.assertEqual({record["original"] for record in sources}, {"追加の人"})


if __name__ == "__main__":
    unittest.main()
