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

    def test_channel_and_handle_subpages_resolve_to_the_same_channel(self):
        channel_id = "UC" + "a" * 22
        self.assertEqual(discover.youtube_locator(
            f"https://www.youtube.com/channel/{channel_id}/videos"),
            ("id", channel_id))
        self.assertEqual(discover.youtube_locator(
            "https://youtube.com/@safe_handle/featured"),
            ("forHandle", "@safe_handle"))
        self.assertIsNone(discover.youtube_locator(
            f"https://youtube.com/channel/{channel_id}/watch"))

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

    def test_channel_operated_by_a_relative_is_not_auto_accepted(self):
        channel_id = "UC" + "a" * 22
        text = ("\n== 外部リンク ==\n* [https://www.youtube.com/channel/"
                + channel_id + " 山田花子 公式] - 弟が運営している。\n")

        accepted, deferred = discover.wikipedia_links("山田花子", text)

        self.assertEqual(accepted, [])
        self.assertEqual(deferred[0]["reason"],
                         "本人以外による運営・管理が明記されている")

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

    @mock.patch.object(discover, "sparql")
    def test_youtube_handles_are_anchored_by_non_deprecated_qid_statement(
            self, sparql):
        sparql.return_value = {"results": {"bindings": [{
            "p": {"value": "http://www.wikidata.org/entity/Q1"},
            "handle": {"value": "safe%20handle"},
        }]}}

        result = discover.fetch_youtube_handles(["Q1"])

        self.assertEqual(result, {"Q1": ["@safe handle"]})
        query = sparql.call_args.args[0]
        self.assertIn("p:P11245", query)
        self.assertIn("DeprecatedRank", query)

    def test_infobox_channels_are_extracted_but_comments_and_body_are_not(self):
        channel_id = "UC" + "a" * 22
        ignored = "UC" + "b" * 22
        text = f"""
{{{{Infobox YouTube personality
| channels = [https://www.youtube.com/user/main Main]<br>
  [https://www.youtube.com/@sub/videos Sub]
| channel_url2 = {channel_id}/about
<!-- | channel_url3 = {ignored} -->
}}}}
本文 https://www.youtube.com/channel/{ignored}
"""

        result = discover.infobox_links(text)

        self.assertEqual({item["youtube_locator"] for item in result}, {
            ("forUsername", "main"), ("forHandle", "@sub"),
            ("id", channel_id),
        })

    @mock.patch.object(discover, "_request_json")
    def test_fetch_wikitext_reports_redirects(self, request_json):
        request_json.return_value = {"query": {
            "redirects": [{"from": "人物", "to": "グループ"}],
            "pages": [{"title": "グループ", "revisions": [{"slots": {
                "main": {"content": "body"}}}]}],
        }}

        self.assertEqual(discover.fetch_wikitext("人物"),
                         ("グループ", "body", True))

    def test_successful_reaudit_replaces_stale_source_but_failure_retains_it(self):
        old = [{"person_id": "1", "channel_id": "old",
                "source_type": "jawiki_external_link"}]
        new = [{"person_id": "1", "channel_id": "new",
                "source_type": "jawiki_infobox"}]

        replaced = discover.merge_source_records(old, new, {"1"}, set())
        retained = discover.merge_source_records(old, [], {"1"}, {"1"})
        manual = discover.merge_source_records([{
            "person_id": "1", "channel_id": "manual",
            "source_type": "wikidata_official_site_page",
        }], [], {"1"}, set())
        web_research = discover.merge_source_records([{
            "person_id": "1", "channel_id": "web",
            "source_type": "web_search_primary_link",
        }], [], {"1"}, set())

        self.assertEqual([record["channel_id"] for record in replaced], ["new"])
        self.assertEqual([record["channel_id"] for record in retained], ["old"])
        self.assertEqual([record["channel_id"] for record in manual], ["manual"])
        self.assertEqual([record["channel_id"] for record in web_research], ["web"])


if __name__ == "__main__":
    unittest.main()
