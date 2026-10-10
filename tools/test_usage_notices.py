import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usage_notices import validate_usage_notices


class UsageNoticesTest(unittest.TestCase):
    def test_optional_metadata_and_consistent_aliases(self):
        validate_usage_notices([{"id": "1", "original": "通常語"}])
        row = {"id": "2", "original": "活動名", "usage_notice": "guidelines",
               "usage_terms_page": "https://example.com/terms"}
        validate_usage_notices([row, dict(row, surface="別表記")])
        with self.assertRaisesRegex(ValueError, "differs"):
            validate_usage_notices([row, dict(row, usage_terms_page="")])

    def test_invalid_notice_or_link_is_rejected(self):
        for notice, url in (("unknown", ""), ("", "https://example.com"),
                            ("guidelines", "javascript:alert(1)"),
                            ("guidelines", "https://[invalid"),
                            ("guidelines", "https://user:secret@example.com")):
            with self.subTest(notice=notice, url=url), self.assertRaises(ValueError):
                validate_usage_notices([{"id": "1", "original": "活動名",
                                         "usage_notice": notice, "usage_terms_page": url}])


if __name__ == "__main__":
    unittest.main()
