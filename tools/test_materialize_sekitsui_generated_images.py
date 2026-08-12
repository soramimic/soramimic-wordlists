import unittest
from pathlib import Path

from materialize_marine_generated_images import split_filename
from materialize_sekitsui_generated_images import locate


class MaterializeSekitsuiGeneratedImagesTest(unittest.TestCase):
    def test_split_filename_is_stable_and_shared_with_grid_pipeline(self):
        self.assertEqual(split_filename("family:ネズミ科"), "gk_af901806dd.png")

    def test_locate_allows_reused_asset_without_split(self):
        self.assertIsNone(locate("family:ハゼ科", [Path("/nonexistent")]))


if __name__ == "__main__":
    unittest.main()
