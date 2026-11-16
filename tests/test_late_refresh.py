import json
import tempfile
import unittest
from pathlib import Path

from aidaily.ai_news import late_refresh


DATE = "2026-09-11"
STORY = {
    "headline": "Today story", "body": "Initial source body",
    "takeaway": "Why it matters", "url": "https://example.com/today",
    "source": "aiofmodu",
}


class LateRefreshTests(unittest.TestCase):
    def _archive(self, root: str, stories: list[dict]) -> Path:
        path = Path(root) / "index.json"
        path.write_text(json.dumps([{"date": DATE, "stories": stories}]), encoding="utf-8")
        return path

    def test_waits_when_weekday_source_is_not_available(self):
        with tempfile.TemporaryDirectory() as root:
            result = late_refresh.evaluate(DATE, self._archive(root, []), source_items=[])
        self.assertEqual(result["state"], "waiting")

    def test_refreshes_when_source_arrives_after_initial_publication(self):
        items = [{"date": DATE, "stories": [STORY]}]
        with tempfile.TemporaryDirectory() as root:
            result = late_refresh.evaluate(DATE, self._archive(root, []), source_items=items)
        self.assertEqual(result["state"], "refresh")
        self.assertEqual((result["source_count"], result["published_count"]), (1, 0))

    def test_does_not_republish_unchanged_source(self):
        items = [{"date": DATE, "stories": [STORY]}]
        published = [{**STORY, "body_bullets": ["Generated display metadata"]}]
        with tempfile.TemporaryDirectory() as root:
            result = late_refresh.evaluate(DATE, self._archive(root, published), source_items=items)
        self.assertEqual(result["state"], "current")

    def test_refreshes_again_when_source_is_edited_later(self):
        items = [{"date": DATE, "stories": [{**STORY, "body": "Updated source body"}]}]
        with tempfile.TemporaryDirectory() as root:
            result = late_refresh.evaluate(DATE, self._archive(root, [STORY]), source_items=items)
        self.assertEqual(result["state"], "refresh")
        self.assertNotEqual(result["source_fingerprint"], result["published_fingerprint"])


if __name__ == "__main__":
    unittest.main()
