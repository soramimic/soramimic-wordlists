import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plan_marine_generated_images as planner


class MarineGeneratedImagePlanTest(unittest.TestCase):
    def row(self, name, family, order="テスト目", group="魚類"):
        return {"name": name, "family": family, "order": order,
                "image_group": group, "scientific_name": f"Testus {name}"}

    def test_uses_family_then_order_then_group(self):
        rows = [self.row(f"魚{i}", "多数科") for i in range(5)]
        rows += [self.row(f"蟹{i}", f"少数科{i}", "共有目", "甲殻類") for i in range(5)]
        rows += [self.row("孤立", "孤立科", "孤立目", "軟体動物")]
        plan, assignment = planner.build_plan(rows)
        self.assertEqual("family:多数科", assignment["魚0"])
        self.assertEqual("order:共有目", assignment["蟹0"])
        self.assertEqual("group:軟体動物", assignment["孤立"])
        self.assertEqual(2, len(plan))
        planner.validate_plan(plan, assignment, rows)

    def test_validation_rejects_missing_assignment(self):
        rows = [self.row(f"魚{i}", "多数科") for i in range(5)]
        plan, assignment = planner.build_plan(rows)
        assignment.pop("魚0")
        with self.assertRaisesRegex(ValueError, "do not cover"):
            planner.validate_plan(plan, assignment, rows)

    def test_filename_is_stable_and_ascii(self):
        value = planner.stable_filename("family", "ハゼ科")
        self.assertRegex(value, r"^marine_family_[0-9a-f]{12}_generated\.webp$")


if __name__ == "__main__":
    unittest.main()
