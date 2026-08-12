import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_sekitsui_generated_images as planner


class SekitsuiGeneratedImagePlanTest(unittest.TestCase):
    def row(self, name, family, animal_class="哺乳類"):
        return {
            "original": name,
            "family": family,
            "class": animal_class,
            "image": (
                "https://github.com/soramimic/soramimic-wordlists/releases/"
                "download/class-image-v1/class_mammal.svg"
            ),
        }

    def test_load_rows_keeps_existing_family_generated_images(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sekitsui.csv"
            path.write_text(
                "original,image\n"
                "ア,https://raw.githubusercontent.com/soramimic/soramimic-wordlists/"
                "main/images/sekitsui/sekitsui_family_deadbeef0000_generated.webp",
                encoding="utf-8",
            )
            self.assertEqual(planner.load_rows(path)[0]["original"], "ア")

    def test_threshold_and_full_assignment_coverage(self):
        rows = [self.row(f"多数{i}", "多数科") for i in range(5)]
        rows += [self.row(f"少数{i}", "少数科", "鳥類") for i in range(4)]
        rows += [self.row(f"不正{i}", "科でない分類", "爬虫類") for i in range(5)]
        rows += [self.row("分類のみ", "", "魚類")]

        plan, assignment = planner.build_plan(rows)

        self.assertEqual(
            ["family:多数科", "family:少数科"],
            [record["word"] for record in plan],
        )
        self.assertTrue(all(
            assignment[f"多数{i}"] == "family:多数科" for i in range(5)
        ))
        self.assertTrue(all(
            assignment[f"少数{i}"] == "family:少数科" for i in range(4)
        ))
        self.assertTrue(all(
            assignment[f"不正{i}"] == "class:爬虫類" for i in range(5)
        ))
        self.assertEqual("class:魚類", assignment["分類のみ"])
        self.assertEqual(len(rows), len(assignment))
        planner.validate_plan(plan, assignment, rows)

    def test_filename_uses_family_sha1(self):
        digest = hashlib.sha1("family:リス科".encode()).hexdigest()[:12]
        self.assertEqual(
            f"sekitsui_family_{digest}_generated.webp",
            planner.stable_filename("リス科"),
        )

    def test_examples_are_japanese_names_and_limited_to_three(self):
        rows = [self.row(name, "リス科") for name in (
            "ニホンリス", "シマリス", "ムササビ", "モモンガ", "プレーリードッグ"
        )]
        plan, assignment = planner.build_plan(rows)
        record = plan[0]

        self.assertEqual(3, len(record["japanese_examples"]))
        self.assertEqual(
            sorted(row["original"] for row in rows)[:3],
            record["japanese_examples"],
        )
        for example in record["japanese_examples"]:
            self.assertIn(example, record["prompt"])
        self.assertIn("1〜3個体", record["prompt"])
        self.assertIn("特定の一種を正確に再現した画像とは主張せず", record["prompt"])
        planner.validate_plan(plan, assignment, rows)

    def test_writes_all_three_output_files(self):
        rows = [self.row(f"動物{i}", "テスト科") for i in range(5)]
        plan, assignment = planner.build_plan(rows)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            planner.write_outputs(output, plan, assignment)
            self.assertEqual(plan, json.loads((output / "plan.json").read_text()))
            self.assertEqual(
                assignment, json.loads((output / "assignment.json").read_text())
            )
            words = [json.loads(line) for line in
                     (output / "words.jsonl").read_text().splitlines()]
            self.assertEqual(
                [{"word": plan[0]["word"], "prompt": plan[0]["prompt"]}], words
            )

    def test_validation_rejects_missing_assignment(self):
        rows = [self.row(f"動物{i}", "テスト科") for i in range(5)]
        plan, assignment = planner.build_plan(rows)
        assignment.pop("動物0")
        with self.assertRaisesRegex(ValueError, "do not cover"):
            planner.validate_plan(plan, assignment, rows)


if __name__ == "__main__":
    unittest.main()
