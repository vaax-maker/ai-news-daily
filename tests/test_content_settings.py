import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily.customer_stories import pipeline as customer_pipeline
from aidaily.customer_stories import sources as customer_sources
from aidaily.integrations import content_settings


class ContentSettingsTests(unittest.TestCase):
    def test_defaults_keep_aiofmodu_as_operator_policy(self):
        with tempfile.TemporaryDirectory() as root:
            settings = content_settings.load(Path(root) / "missing.json")
        source = content_settings.source_by_id("aiofmodu", settings)
        self.assertEqual(source["limit_mode"], "all_today")
        self.assertTrue(source["infographic_candidate"])
        self.assertEqual(settings["infographics"]["ai_news"]["source_ids"], ["aiofmodu"])
        self.assertEqual(settings["infographics"]["ai_news"]["article_count"], 3)

    def test_upsert_and_archive_source_are_persistent(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "settings.json"
            row = content_settings.upsert_source({
                "name": "경제 테스트", "content_type": "economy_news",
                "connector": "rss", "url": "https://example.com/feed.xml",
                "limit_mode": "fixed", "limit": 4, "priority": 5,
            }, path)
            self.assertEqual(row["id"], "example-com")  # Korean-only names use URL domain.
            self.assertTrue(content_settings.archive_source(row["id"], path))
            saved = json.loads(path.read_text(encoding="utf-8"))
            restored = next(item for item in saved["sources"] if item["id"] == row["id"])
            self.assertFalse(restored["enabled"])

    def test_market_image_is_retained_as_template_png(self):
        with tempfile.TemporaryDirectory() as root:
            settings = content_settings.load(Path(root) / "missing.json")
        market = settings["infographics"]["market_summary"]
        self.assertTrue(market["enabled"])
        self.assertEqual((market["renderer"], market["format"]), ("template", "png"))

    def test_customer_rss_parser_supports_rss2(self):
        raw = b"""<rss><channel><item><title>Agent workflow</title>
          <description>Users report a useful automation pattern.</description>
          <link>https://example.com/story</link></item></channel></rss>"""
        entries = customer_sources._feed_entries(raw)
        self.assertEqual(entries[0]["url"], "https://example.com/story")
        self.assertIn("Agent workflow", entries[0]["text"])

    def test_customer_corpus_includes_operator_added_rss(self):
        row = {"id": "community-feed", "name": "Community Feed",
               "content_type": "customer_stories", "connector": "rss",
               "url": "https://example.com/feed", "enabled": True,
               "limit_mode": "fixed", "limit": 2}
        item = {"source": "Community Feed", "text": "A real user workflow report",
                "url": "https://example.com/story", "score": 0}
        with mock.patch.object(customer_sources, "fetch_all",
                               return_value={"community-feed": [item]}), \
             mock.patch.object(content_settings, "sources", return_value=[row]):
            corpus, active, urls, refmap = customer_pipeline.build_multi_corpus("")
        self.assertIn("Community Feed", corpus)
        self.assertEqual(active, ["Community Feed"])
        self.assertEqual(urls, ["https://example.com/story"])
        self.assertEqual(refmap["S1-1"]["url"], "https://example.com/story")


if __name__ == "__main__":
    unittest.main()
