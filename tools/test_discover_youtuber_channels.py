import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import discover_youtuber_channels as discover


class DiscoverYoutuberChannelsTest(unittest.TestCase):
    def test_canonical_id_and_handle_are_allowed_but_video_and_custom_are_not(self):
        channel_id = "UC" + "a" * 22
        self.assertEqual(discover.youtube_locator(
            f"https://www.youtube.com/channel/{channel_id}"), ("id", channel_id))
        self.assertEqual(discover.youtube_locator(
            "https://youtube.com/@safe_handle"), ("forHandle", "@safe_handle"))
        self.assertIsNone(discover.youtube_locator(
            "https://youtube.com/watch?v=not-a-channel"))
        self.assertIsNone(discover.youtube_locator(
            "https://youtube.com/c/custom-name"))

    def test_only_explicit_person_link_is_auto_accepted(self):
        first = "UC" + "a" * 22
        second = "UC" + "b" * 22
        text = f"""
== 外部リンク ==
* [https://www.youtube.com/channel/{first} 山田花子 公式YouTube]
* [https://www.youtube.com/channel/{second} 関連動画]
== 脚注 ==
"""
        accepted, deferred = discover.wikipedia_links("山田花子", text)

        self.assertEqual([item["youtube_locator"][1] for item in accepted], [first])
        self.assertEqual([item["evidence_url"] for item in deferred],
                         [f"https://www.youtube.com/channel/{second}"])

    def test_links_outside_external_links_section_are_never_candidates(self):
        channel_id = "UC" + "a" * 22
        accepted, deferred = discover.wikipedia_links(
            "山田花子", f"本文 https://youtube.com/channel/{channel_id}")
        self.assertEqual((accepted, deferred), ([], []))

    def test_official_youtube_template_with_id_only_is_accepted(self):
        channel_id = "UC" + "a" * 22
        text = f"""
== 外部リンク ==
* {{{{YouTube|{channel_id}|山田花子 公式}}}}
"""

        accepted, deferred = discover.wikipedia_links("山田花子", text)

        self.assertEqual([item["youtube_locator"][1] for item in accepted],
                         [channel_id])
        self.assertEqual(deferred, [])

    @mock.patch.object(discover, "sparql")
    def test_jawiki_article_is_anchored_by_qid_sitelink(self, sparql):
        sparql.return_value = {"results": {"bindings": [{
            "p": {"value": "http://www.wikidata.org/entity/Q1"},
            "article": {"value": "https://ja.wikipedia.org/wiki/現行記事名"},
            "title": {"value": "現行記事名"},
        }]}}

        result = discover.fetch_jawiki_sitelinks(["Q1"])

        self.assertEqual(result["Q1"]["title"], "現行記事名")
        self.assertIn("schema:about ?p", sparql.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
