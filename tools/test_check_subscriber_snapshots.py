import csv
import io
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_subscriber_snapshots import check_snapshots, FILES
import check_subscriber_snapshots as checker
from creator_csv import subscriber_band


COLUMNS = ["id", "original", "surface", "type", "channel", "channel_shared",
           "image", "subscribers", "subscribers_as_of", "subscriber_band"]
TODAY = "2026-11-06"


def row(pid="1", count="100000", as_of="2026-11-03", **extra):
    return {"id": pid, "original": "A", "surface": "A", "type": "full",
            "channel": "Official A", "channel_shared": "no", "image": "keep.png",
            "subscribers": count, "subscribers_as_of": as_of,
            "subscriber_band": subscriber_band(count), **extra}


def snapshot(rows, vtubers=()):
    result = {}
    for name, values in zip(FILES, (rows, vtubers)):
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(values)
        result[name] = output.getvalue()
    return result


class CheckSubscriberSnapshotsTest(unittest.TestCase):
    def check(self, before, after, **kwargs):
        return check_snapshots(before, after, today=TODAY, **kwargs)

    def test_refresh_updates_both_lists_and_aliases_without_changing_counts(self):
        alias = {"surface": "Alias", "type": "given"}
        before = snapshot([row(), row(**alias)], [row("2")])
        after = snapshot([row(as_of=TODAY), row(as_of=TODAY, **alias)],
                         [row("2", as_of=TODAY)])
        self.assertEqual(self.check(before, after, require_current=True), (2, 2))

    def test_real_decrease_is_allowed_and_band_changes_with_count(self):
        self.check(snapshot([row()]), snapshot([row(count="99900", as_of=TODAY)]),
                   require_current=True)

    def test_preserves_small_number_of_deferred_snapshots(self):
        before = snapshot([row(str(pid)) for pid in range(21)])
        after = snapshot([row(str(pid), as_of=TODAY if pid else "2026-11-03")
                          for pid in range(21)])
        self.assertEqual(self.check(before, after, require_current=True), (20, 21))

    def test_mostly_stale_success_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "95%"):
            self.check(snapshot([row()]), snapshot([row()]), require_current=True)

    def test_general_monthly_update_cannot_undo_newer_subscriber_refresh(self):
        with self.assertRaisesRegex(ValueError, "regressed"):
            self.check(snapshot([row(as_of=TODAY)]), snapshot([row()]))

    def test_general_monthly_update_can_add_people_without_refreshing_old_counts(self):
        self.check(snapshot([row()]), snapshot([row(), row("2", "NA", "NA")]))

    def test_known_counts_cannot_be_erased_or_people_removed(self):
        for after in (snapshot([row(count="NA", as_of="NA")]), snapshot([])):
            with self.subTest(after=after), self.assertRaises(ValueError):
                self.check(snapshot([row()]), after)

    def test_unrelated_metadata_row_order_and_channel_overwrites_are_rejected(self):
        for extra in ({"image": "other.png"}, {"original": "Other"},
                      {"surface": "Other"}, {"channel": "Other"}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.check(snapshot([row()]), snapshot([row(as_of=TODAY, **extra)]),
                           require_current=True)
        with self.assertRaises(ValueError):
            self.check(snapshot([row(), row("2")]),
                       snapshot([row("2", as_of=TODAY), row(as_of=TODAY)]),
                       require_current=True)

    def test_strict_refresh_cannot_add_or_drop_rows_or_change_schema(self):
        before = snapshot([row()])
        for after in (snapshot([]), snapshot([row(as_of=TODAY), row("2")]),
                      {**before, FILES[0]: before[FILES[0]].replace("image", "photo")}):
            with self.subTest(after=after), self.assertRaises(ValueError):
                self.check(before, after, require_current=True)

    def test_wrong_band_dates_missing_dates_and_mixed_aliases_are_rejected(self):
        for rows in ([row(as_of=TODAY, subscriber_band="1m_plus")],
                     [row(as_of="2026-11-07")], [row(as_of="20261106")],
                     [row(count="NA", as_of=TODAY)], [row(count="-1", as_of=TODAY)],
                     [row(as_of="NA")], [row(as_of=TODAY), row()]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.check(snapshot([row()]), snapshot(rows))

    def test_missing_channel_can_be_filled_and_unknown_count_populated(self):
        before = snapshot([row(), row("2", "NA", "NA", channel="NA")])
        after = snapshot([row(as_of=TODAY), row("2", as_of=TODAY)])
        self.check(before, after, require_current=True)

    def test_cli_checks_git_baseline_and_rejects_unrelated_changed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root,
                                               stderr=subprocess.DEVNULL)
            git("init", "-q")
            for name, text in snapshot([row()]).items():
                (root / name).write_text(text, encoding="utf-8")
            (root / "school.csv").write_text("keep", encoding="utf-8")
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                "-c", "commit.gpgsign=false", "commit", "-qm", "Baseline")
            for name, text in snapshot([row(as_of=TODAY)]).items():
                (root / name).write_text(text, encoding="utf-8")
            with mock.patch.object(checker, "ROOT", root), \
                    mock.patch.object(checker, "datetime") as clock:
                clock.now.return_value.date.return_value.isoformat.return_value = TODAY
                checker.main(["--base-ref", "HEAD", "--require-current"])
                (root / "school.csv").write_text("shrunk", encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "outside its scope"):
                    checker.main(["--base-ref", "HEAD", "--require-current"])
                git("checkout", "--", "school.csv")
                (root / FILES[0]).write_text(snapshot([row()])[FILES[0]], encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "95%"):
                    checker.main(["--base-ref", "HEAD", "--require-current"])


if __name__ == "__main__":
    unittest.main()
