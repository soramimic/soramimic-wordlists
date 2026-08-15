import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import plan_plant_generated_images as planner


class PlantGeneratedImagePlanTest(unittest.TestCase):
    def row(self, name, family, qid="", scientific="", plant_class="双子葉"):
        return {"original": name, "family": family, "family_wikidata": qid,
                "scientific_name": scientific, "class": plant_class,
                "image": "https://github.com/soramimic/soramimic-wordlists/releases/"
                         "download/class-image-v1/class_dicot.svg"}

    def test_qid_identity_and_filename_are_preferred(self):
        rows = [self.row("サクラバラ", "バラ科", "Q104779", "Rosa hirtula")]
        plan, assignment = planner.build_plan(rows)
        self.assertEqual("family:Q104779", plan[0]["word"])
        self.assertEqual("plant_family_q104779_generated.webp", plan[0]["filename"])
        self.assertEqual("family:Q104779", assignment["サクラバラ"])

    def test_family_hash_is_safe_fallback(self):
        digest = hashlib.sha1("family:バラ科".encode()).hexdigest()[:12]
        self.assertEqual(f"plant_family_{digest}_generated.webp",
                         planner.stable_filename("バラ科"))

    def test_family_qid_is_inferred_and_conflicts_are_rejected(self):
        rows = [self.row("ア", "テスト科", "Q1"), self.row("イ", "テスト科")]
        plan, assignment = planner.build_plan(rows)
        self.assertEqual("Q1", plan[0]["family_qid"])
        self.assertEqual("family:Q1", assignment["イ"])
        with self.assertRaisesRegex(ValueError, "conflicting QIDs"):
            planner.build_plan(rows + [self.row("ウ", "テスト科", "Q2")])

    def test_prompt_has_up_to_three_names_and_optional_scientific_names(self):
        rows = [self.row(f"植物{i}", "テスト科", "Q12", f"Species {i}") for i in range(5)]
        plan, assignment = planner.build_plan(rows)
        record = plan[0]
        self.assertEqual(3, len(record["japanese_examples"]))
        self.assertEqual(3, len(record["scientific_examples"]))
        self.assertIn("学名の例は", record["prompt"])
        self.assertIn("横長16:10", record["prompt"])
        planner.validate_plan(plan, assignment, rows)

    def test_unresolved_family_uses_class_assignment(self):
        plan, assignment = planner.build_plan([self.row("不明", "")])
        self.assertEqual([], plan)
        self.assertEqual("class:双子葉", assignment["不明"])

    def test_writes_all_outputs(self):
        rows = [self.row("ア", "テスト科", "Q12")]
        plan, assignment = planner.build_plan(rows)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            planner.write_outputs(out, plan, assignment)
            self.assertEqual(plan, json.loads((out / "plan.json").read_text()))
            self.assertEqual(assignment, json.loads((out / "assignment.json").read_text()))
            self.assertEqual(plan[0]["word"],
                             json.loads((out / "words.jsonl").read_text())["word"])


if __name__ == "__main__":
    unittest.main()
