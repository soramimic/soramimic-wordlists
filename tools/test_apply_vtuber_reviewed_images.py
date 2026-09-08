"""Offline checks for reviewed image identity, attribution, and withdrawal."""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import apply_vtuber_reviewed_images as subject
from gen_youtuber_cards import asset_name
from wpnames import write_csv_no_trailing_newline


class ReviewedImagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv_path = self.root / 'vtuber.csv'
        self.manifest_path = self.root / 'manifest.json'
        self.record = dict(person_id='12', original='試験あお', org='試験社', enabled=True,
                           image_url='https://assets.example.org/a.png',
                           source_page='https://example.org/talent/ao',
                           credit='試験あお / 試験社', terms_page='https://example.org/terms',
                           conditions='非営利の範囲で利用。', reviewed='2026-09-08')
        self.rows = [dict(id='12', original='試験あお', category='vtuber', org='試験社',
                          surface=surface, image='', image_page='', image_credit='',
                          image_usage='', image_terms_page='') for surface in ['試験あお', 'あお']]
        self.fields = list(self.rows[0])
        self.save()

    def save(self):
        self.manifest_path.write_text(json.dumps(dict(schema_version=1, images=[self.record])))
        write_csv_no_trailing_newline(self.csv_path, self.fields, self.rows)

    def apply(self):
        return subject.apply(self.csv_path, self.manifest_path)

    def read(self):
        with self.csv_path.open(newline='') as handle:
            return list(csv.DictReader(handle))

    def test_all_name_variants_and_idempotence(self):
        self.assertEqual(self.apply(), (1, 2))
        after = self.csv_path.read_bytes()
        self.assertEqual(self.apply(), (0, 0))
        self.assertEqual(after, self.csv_path.read_bytes())
        rows = self.read()
        subject.validate_rows(rows, subject.load_manifest(self.manifest_path))
        self.assertEqual([r['surface'] for r in rows], ['試験あお', 'あお'])
        self.assertEqual({r['id'] for r in rows}, {'12'})
        self.assertFalse(after.endswith(b'\n'))

    def test_unrelated_image_is_preserved(self):
        other = dict(self.rows[0], id='13', original='別人', image='https://example.org/other.png')
        self.rows.append(other)
        self.save()
        self.apply()
        self.assertEqual(self.read()[-1], other)

    def test_disabled_image_restores_card_and_clears_terms(self):
        self.apply()
        self.rows = self.read()
        self.record['enabled'] = False
        self.save()
        self.assertEqual(self.apply(), (1, 2))
        rows = self.read()
        self.assertTrue((self.root / 'images/youtuber' / asset_name(self.record['original'])).is_file())
        self.assertTrue(all(r['image_credit'] == r['image_usage'] == r['image_terms_page'] == '' for r in rows))
        subject.validate_rows(rows, subject.load_manifest(self.manifest_path, include_inactive=True))
        self.assertEqual(self.apply(), (0, 0))

    def test_identity_mismatch_does_not_write(self):
        for field, value in [('id', '13'), ('category', 'youtuber'), ('org', '別社'), ('original', '別人')]:
            with self.subTest(field=field):
                original = self.rows[0][field]
                self.rows[0][field] = value
                self.save()
                before = self.csv_path.read_bytes()
                with self.assertRaises(ValueError):
                    self.apply()
                self.assertEqual(before, self.csv_path.read_bytes())
                self.rows[0][field] = original

    def test_image_cannot_be_assigned_to_another_person(self):
        self.apply()
        rows = self.read()
        rows.append(dict(rows[0], id='99', original='別人'))
        with self.assertRaises(ValueError):
            subject.validate_rows(rows, subject.load_manifest(self.manifest_path))

    def test_missing_person_is_an_error(self):
        self.rows = []
        self.save()
        with self.assertRaises(ValueError):
            self.apply()

    def test_every_image_field_is_checked(self):
        self.apply()
        rows = self.read()
        for field in subject.IMAGE_FIELDS:
            with self.subTest(field=field):
                bad_rows = [dict(r) for r in rows]
                bad_rows[0][field] = ''
                with self.assertRaises(ValueError):
                    subject.validate_rows(bad_rows, subject.load_manifest(self.manifest_path))

    def test_incomplete_or_unsafe_manifest_rejected(self):
        for field, value in [('credit', ''), ('terms_page', ''),
                             ('source_page', 'http://example.org/'), ('enabled', 'true'),
                             ('reviewed', '2026-02-30'), ('original', 'bad,name'),
                             ('person_id', '0')]:
            with self.subTest(field=field):
                original = self.record[field]
                self.record[field] = value
                self.save()
                with self.assertRaises(ValueError):
                    subject.load_manifest(self.manifest_path)
                self.record[field] = original

    def test_duplicate_ids_and_images_rejected(self):
        for field in ['person_id', 'original', 'image_url']:
            with self.subTest(field=field):
                other = dict(self.record, person_id='13', original='別人', image_url='https://assets.example.org/b.png')
                other[field] = self.record[field]
                self.manifest_path.write_text(json.dumps(dict(schema_version=1, images=[self.record, other])))
                with self.assertRaises(ValueError):
                    subject.load_manifest(self.manifest_path)


if __name__ == '__main__':
    unittest.main()
