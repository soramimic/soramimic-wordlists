import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import enrich_youtuber_images as images


class CuratedSourcesTest(unittest.TestCase):
    def write_sources(self, records):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False)
        with tmp:
            json.dump({"images": records}, tmp, ensure_ascii=False)
        self.addCleanup(Path(tmp.name).unlink, missing_ok=True)
        return Path(tmp.name)

    def test_loads_valid_source(self):
        source = {
            "original": "例",
            "wikidata": "Q1",
            "file": "Example.jpg",
            "source_type": "commons_structured_depicts",
            "reviewed": "2026-08-16",
        }
        self.assertEqual(
            images.load_curated_sources(self.write_sources([source])),
            [source],
        )

    def test_rejects_duplicate_person(self):
        source = {
            "original": "例",
            "wikidata": "Q1",
            "file": "Example.jpg",
            "source_type": "commons_person_category",
            "reviewed": "2026-08-16",
        }
        with self.assertRaises(SystemExit):
            images.load_curated_sources(self.write_sources([source, source]))

    def test_rejects_unknown_source_type(self):
        source = {
            "original": "例",
            "wikidata": "Q1",
            "file": "Example.jpg",
            "source_type": "web_search",
            "reviewed": "2026-08-16",
        }
        with self.assertRaises(SystemExit):
            images.load_curated_sources(self.write_sources([source]))


if __name__ == "__main__":
    unittest.main()
