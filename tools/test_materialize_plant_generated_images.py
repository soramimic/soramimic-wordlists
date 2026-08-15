import tempfile
import unittest
from pathlib import Path

from materialize_marine_generated_images import split_filename
from materialize_plant_generated_images import load_base_manifest, locate, merge_base_records


class MaterializePlantGeneratedImagesTest(unittest.TestCase):
    def test_split_filename_is_shared_with_grid_pipeline(self):
        self.assertEqual(split_filename("family:Q104779"), "gk_dd7eb51801.png")

    def test_locate_requires_at_most_one_file(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            filename = split_filename("family:Q1")
            (Path(first) / filename).touch()
            self.assertEqual(Path(first) / filename, locate("family:Q1", [Path(first)]))
            (Path(second) / filename).touch()
            with self.assertRaisesRegex(ValueError, "at most one"):
                locate("family:Q1", [Path(first), Path(second)])

    def test_base_manifest_merge_and_overlap(self):
        base = [{"name": "既存科", "family_qid": "Q1"}]
        plan = [{"name": "新規科", "family_qid": "Q2"}]
        self.assertEqual([], load_base_manifest(None, plan))
        self.assertEqual(base, merge_base_records(base, plan))
        with self.assertRaisesRegex(ValueError, "overlaps"):
            merge_base_records(base, [{"name": "既存科", "family_qid": "Q1"}])


if __name__ == "__main__":
    unittest.main()
