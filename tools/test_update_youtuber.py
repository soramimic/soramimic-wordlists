import json
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import update_youtuber as target  # noqa: E402
from creator_csv import read_creator_csvs
import yt_common


class YouTuberExclusionTest(unittest.TestCase):
    def test_reviewed_real_person_creators_stay_in_youtuber_list(self):
        expected = {"AmaLee", "ポキメイン", "ヴィーナス・アンジェリック"}
        self.assertEqual(
            {name for name, category in target.CATEGORY_OVERRIDES.items()
             if category == "youtuber"},
            expected,
        )

        _, rows = read_creator_csvs()
        categories = {row["original"]: row["category"] for row in rows
                      if row["original"] in expected}
        self.assertEqual(categories, {name: "youtuber" for name in expected})

    def test_reviewed_channel_exclusions_are_absent_from_csv(self):
        excluded = {"うごくちゃん", "佐々木康平", "熱田隆介", "懲役太郎"}
        self.assertTrue(excluded <= target.EXCLUDED)

        _, rows = read_creator_csvs()
        originals = {row["original"] for row in rows}
        self.assertFalse(excluded & originals)

    def test_membership_review_survives_a_wikidata_refresh(self):
        root = Path(__file__).resolve().parent
        decisions = [json.loads(line) for line in
                     (root / "vtuber_membership_sources.jsonl").read_text().splitlines()]
        excluded = {d.get("previous_original", d["original"]) for d in decisions
                    if d["decision"] != "youtuber"}
        names = sorted(excluded | {"ヴィーナス・アンジェリック"})
        people = {f"Q{i}": name for i, name in enumerate(names)}
        specs = [{**s, "guard": (0, 100)} for s in target.SPECS]
        columns, rows = read_creator_csvs()
        # Simulate a fresh candidate for Venus and old article names returning.
        rows = [r for r in rows if r["id"] != "904"]
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(yt_common, "assert_occupation"))
            stack.enter_context(patch.object(yt_common, "fetch_persons",
                                             side_effect=[{}, people]))
            stack.enter_context(patch.object(yt_common, "fetch_attrs", return_value={}))
            stack.enter_context(patch.object(yt_common, "fetch_extracts", return_value={}))
            stack.enter_context(patch.object(yt_common, "read_creator_csvs",
                                             return_value=(columns, rows)))
            parse = stack.enter_context(patch.object(
                yt_common, "parse_entry", side_effect=lambda name, text:
                (name, [(name, "カナ", "full")])))
            write = stack.enter_context(patch.object(yt_common, "write_creator_csvs"))
            stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
            result = target.build_list(
                ("youtuber.csv", "vtuber.csv"), specs, "UNUSED_TEST_CACHE",
                target.EXCLUDED, category_overrides=target.CATEGORY_OVERRIDES)
        self.assertEqual(result, 0)
        parse.assert_called_once_with("ヴィーナス・アンジェリック", "")
        output = write.call_args.args[1]
        self.assertFalse(excluded & {r["original"] for r in output})
        self.assertEqual(output[-1]["category"], "youtuber")
        for decision in decisions:
            if decision["decision"] == "vtuber_name":
                self.assertTrue(any(r["id"] == decision["person_id"] and
                                    r["original"] == decision["original"]
                                    for r in output))

    def test_channel_ledgers_only_reference_current_people(self):
        root = Path(__file__).resolve().parent.parent
        _, rows = read_creator_csvs()
        people = {row["id"]: row for row in rows}

        for name in (
                "youtuber_channel_sources.jsonl",
                "youtuber_channel_candidates.jsonl"):
            path = root / "tools" / name
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                person = people.get(record["person_id"])
                self.assertIsNotNone(person, record)
                self.assertEqual(record["original"], person["original"])
                self.assertEqual(
                    record.get("qid", "NA"), person["wikidata"] or "NA")


if __name__ == "__main__":
    unittest.main()
