import json
import tempfile
import unittest
from pathlib import Path

import apply_myoji_review_rejections_to_ledger as subject


def row(s, r):
    return {"surface": s, "pronunciation": r, "status": "verified"}


class ApplyTest(unittest.TestCase):
    def files(self, ls, rs):
        td = tempfile.TemporaryDirectory()
        p = Path(td.name)
        l = p / "l"
        v = p / "v"
        l.write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in ls),
            encoding="utf-8",
        )
        v.write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rs),
            encoding="utf-8",
        )
        return td, l, v

    def test_dry_run(self):
        td, l, v = self.files(
            [row("A", "ア"), row("B", "イ")],
            [{"surface": "A", "pronunciation": "ア", "decision": "reject"}],
        )
        self.addCleanup(td.cleanup)
        q = l.parent / "q"
        b = l.parent / "b"
        old = l.read_bytes()
        self.assertEqual(
            subject.apply(l, [v], q, b),
            {"input": 2, "retained": 1, "removed": 1, "applied": False},
        )
        self.assertEqual(l.read_bytes(), old)
        self.assertFalse(q.exists())
        self.assertFalse(b.exists())

    def test_apply_backup_verified_ignored(self):
        td, l, v = self.files(
            [row("A", "ア"), row("B", "イ")],
            [
                {"surface": "A", "pronunciation": "ア", "decision": "reject"},
                {"surface": "B", "pronunciation": "イ", "decision": "verified"},
            ],
        )
        self.addCleanup(td.cleanup)
        q = l.parent / "q"
        b = l.parent / "b"
        old = l.read_bytes()
        self.assertEqual(subject.apply(l, [v], q, b, True)["removed"], 1)
        self.assertEqual(b.read_bytes(), old)
        self.assertEqual(json.loads(q.read_text())["surface"], "A")
        self.assertEqual(json.loads(l.read_text())["surface"], "B")

    def test_duplicate_missing(self):
        td, l, v = self.files(
            [row("A", "ア"), row("A", "ア")],
            [{"surface": "A", "pronunciation": "ア", "decision": "reject"}],
        )
        self.addCleanup(td.cleanup)
        self.assertRaises(
            ValueError, subject.apply, l, [v], l.parent / "q", l.parent / "b"
        )
        td, l, v = self.files(
            [row("A", "ア")],
            [{"surface": "Z", "pronunciation": "ゼ", "decision": "reject"}],
        )
        self.addCleanup(td.cleanup)
        self.assertRaises(
            ValueError, subject.apply, l, [v], l.parent / "q", l.parent / "b"
        )

    def test_duplicate_review_backup_mismatch(self):
        td, l, v = self.files(
            [row("A", "ア")],
            [
                {"surface": "A", "pronunciation": "ア", "decision": "reject"},
                {"surface": "A", "pronunciation": "ア", "decision": "ambiguous"},
            ],
        )
        self.addCleanup(td.cleanup)
        self.assertRaises(
            ValueError, subject.apply, l, [v], l.parent / "q", l.parent / "b"
        )
        td, l, v = self.files(
            [row("A", "ア")],
            [{"surface": "A", "pronunciation": "ア", "decision": "reject"}],
        )
        self.addCleanup(td.cleanup)
        b = l.parent / "b"
        b.write_bytes(b"x")
        self.assertRaises(ValueError, subject.apply, l, [v], l.parent / "q", b, True)

    def test_allow_already_absent_only_for_non_verified(self):
        td, l, v = self.files(
            [row("A", "ア")],
            [{"surface": "Z", "pronunciation": "ゼ", "decision": "reject"}],
        )
        self.addCleanup(td.cleanup)
        self.assertEqual(
            subject.apply(
                l, [v], l.parent / "q", l.parent / "b", allow_already_absent=True
            )["removed"],
            0,
        )
        td, l, v = self.files(
            [row("A", "ア")],
            [{"surface": "Z", "pronunciation": "ゼ", "decision": "verified"}],
        )
        self.addCleanup(td.cleanup)
        self.assertRaises(
            ValueError,
            subject.apply,
            l,
            [v],
            l.parent / "q",
            l.parent / "b",
            False,
            True,
        )


if __name__ == "__main__":
    unittest.main()
