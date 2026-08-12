import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import materialize_marine_generated_images as materialize


class MaterializeMarineGeneratedImagesTest(unittest.TestCase):
    def test_split_filename_is_stable(self):
        self.assertEqual(
            "gk_085968adde.png",
            materialize.split_filename("family:ハゼ科"),
        )


if __name__ == "__main__":
    unittest.main()
