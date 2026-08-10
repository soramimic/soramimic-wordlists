import importlib.util
import json
from pathlib import Path
import unittest


SCRIPT = Path(__file__).with_name("apply_gimukyoiku_semantic_images.py")
SPEC = importlib.util.spec_from_file_location("apply_semantic", SCRIPT)
TARGET = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(TARGET)


class ApplySemanticImagesTest(unittest.TestCase):
    def test_plan_has_expected_routes(self):
        plan = TARGET.load_plan()
        self.assertEqual(157, len(plan))
        counts = {method: sum(row["method"] == method for row in plan.values())
                  for method in TARGET.ALLOWED_METHODS}
        self.assertEqual({"svg": 98, "gpt-image": 56, "commons": 3}, counts)

    def test_manifest_updates_only_target_line(self):
        plan = {"句会": {"word": "句会", "file": "gk_9c6742cfa2.jpg", "bucket": "v1b",
                         "method": "gpt-image", "prompt": "prompt"}}
        untouched = {"word": "別語", "file": "old.jpg", "bucket": "v1", "method": "sd", "prompt": "old"}
        target = {"word": "句会", "file": "gk_9c6742cfa2.svg", "bucket": "v1b", "method": "svg",
                  "prompt": next(iter(TARGET.LEGACY_PROMPTS)), "card_main": "stale"}
        source = json.dumps(untouched, ensure_ascii=False) + "\n" + json.dumps(target, ensure_ascii=False) + "\n"
        result, found = TARGET.updated_manifest(source, plan)
        lines = result.splitlines()
        self.assertEqual(json.dumps(untouched, ensure_ascii=False), lines[0])
        updated = json.loads(lines[1])
        self.assertEqual("gk_9c6742cfa2.jpg", updated["file"])
        self.assertNotIn("card_main", updated)
        self.assertEqual({"句会"}, found)

    def test_manifest_refuses_to_overwrite_a_later_improvement(self):
        plan = {"句会": {"word": "句会", "file": "gk_9c6742cfa2.jpg", "bucket": "v1b",
                         "method": "gpt-image", "prompt": "prompt"}}
        improved = {"word": "句会", "file": "better.jpg", "bucket": "v1b",
                    "method": "gpt-image", "prompt": "newer"}
        with self.assertRaisesRegex(ValueError, "unexpected current manifest image"):
            TARGET.updated_manifest(json.dumps(improved, ensure_ascii=False) + "\n", plan)

    def test_csv_refuses_to_overwrite_a_later_improvement(self):
        plan = {"句会": {"word": "句会", "file": "gk_9c6742cfa2.jpg", "bucket": "v1b",
                         "method": "gpt-image", "prompt": "prompt"}}
        source = "id,original,image,image_page\n1,句会,https://example.com/better.jpg,https://example.com/source"
        with self.assertRaisesRegex(ValueError, "unexpected current CSV image"):
            TARGET.updated_csv(source, plan)

    def test_commons_csv_uses_source_page(self):
        plan = {"ニホニウム": {"word": "ニホニウム", "file": "gk_n.png", "bucket": "v1",
                              "method": "commons", "prompt": "source", "license": "CC BY-SA 4.0",
                              "image": "https://upload.wikimedia.example/nihonium.png",
                              "source_page": "https://commons.example/file"}}
        source = ("id,original,image,image_page\n0,そのまま,old,page\n"
                  "1,ニホニウム,https://github.com/soramimic/soramimic-wordlists/releases/"
                  "download/gimukyoiku-image-v1/gk_n.svg,https://github.com/soramimic/"
                  "soramimic-wordlists/releases/tag/gimukyoiku-image-v1\n")
        result, found = TARGET.updated_csv(source, plan)
        lines = result.splitlines()
        self.assertEqual("0,そのまま,old,page", lines[1])
        self.assertIn("https://upload.wikimedia.example/nihonium.png,https://commons.example/file", lines[2])
        self.assertEqual({"ニホニウム"}, found)

    def test_commons_manifest_is_preserved(self):
        plan = {"ニホニウム": {"word": "ニホニウム", "file": "gk_n.png", "bucket": "v1",
                              "method": "commons", "prompt": "source", "license": "CC BY-SA 4.0",
                              "image": "https://upload.wikimedia.example/nihonium.png",
                              "source_page": "https://commons.example/file"}}
        original = {"word": "ニホニウム", "file": "old.svg", "bucket": "v1",
                    "method": "svg", "prompt": "old"}
        source = json.dumps(original, ensure_ascii=False) + "\n"
        result, found = TARGET.updated_manifest(source, plan)
        self.assertEqual(source, result)
        self.assertEqual(set(), found)


if __name__ == "__main__":
    unittest.main()
