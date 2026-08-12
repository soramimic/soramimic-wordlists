import unittest

import apply_sekitsui_generated_images as generated


class ApplySekitsuiGeneratedImagesTest(unittest.TestCase):
    def test_replaces_class_image_but_preserves_photo(self):
        rows = [
            {"family": "ネズミ科", "image": "https://github.com/soramimic/soramimic-wordlists/releases/download/class-image-v1/class_mammal.svg", "image_page": "old"},
            {"family": "ネズミ科", "image": "https://commons.wikimedia.org/photo.jpg", "image_page": "photo"},
        ]
        records = [{"scope": "family", "name": "ネズミ科", "filename": "sekitsui_family_deadbeef0000_generated.webp"}]
        rendered, changed = generated.render(rows, records)
        self.assertEqual(changed, 1)
        self.assertTrue(rendered[0]["image"].endswith("sekitsui_family_deadbeef0000_generated.webp"))
        self.assertEqual(rendered[1]["image_page"], "photo")

    def test_clears_stale_generated_image(self):
        rows = [{"family": "別の科", "image": generated.GENERATED_PREFIX + "deadbeef0000_generated.webp", "image_page": "old"}]
        rendered, changed = generated.render(rows, [])
        self.assertEqual(changed, 1)
        self.assertIn("class-image-v1", rendered[0]["image"])


if __name__ == "__main__":
    unittest.main()
