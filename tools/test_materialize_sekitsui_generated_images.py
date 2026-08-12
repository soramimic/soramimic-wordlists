import unittest
from pathlib import Path

from materialize_marine_generated_images import split_filename
from materialize_sekitsui_generated_images import load_base_manifest, locate, merge_base_records


class MaterializeSekitsuiGeneratedImagesTest(unittest.TestCase):
    def test_split_filename_is_stable_and_shared_with_grid_pipeline(self):
        self.assertEqual(split_filename("family:ネズミ科"), "gk_af901806dd.png")

    def test_locate_allows_reused_asset_without_split(self):
        self.assertIsNone(locate("family:ハゼ科", [Path("/nonexistent")]))

    def test_base_manifest_is_preserved_when_plan_does_not_overlap(self):
        base = [{"name": "既存科"}]
        self.assertEqual(load_base_manifest(None, [{"name": "新規科"}]), [])
        self.assertEqual(merge_base_records(base, [{"name": "新規科"}]), base)

    def test_base_manifest_overlap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "overlaps"):
            merge_base_records([{"name": "重複科"}], [{"name": "重複科"}])


if __name__ == "__main__":
    unittest.main()
