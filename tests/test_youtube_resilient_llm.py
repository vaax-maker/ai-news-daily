import unittest
from unittest.mock import patch

from aidaily.integrations import openrouter
from aidaily.youtube_summaries import resilient_llm


class ResilientYouTubeLLMTests(unittest.TestCase):
    def test_pending_request_is_resumed_with_same_id(self):
        with patch.object(resilient_llm.openrouter, "complete_json",
                          side_effect=[openrouter.CompletionPending("stable"), {"ok": True}]) as call, \
             patch.object(resilient_llm.time, "sleep"):
            result = resilient_llm.complete_json("system", "user", request_id="stable",
                                                 resume_timeout=30, poll_interval=1)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(call.call_count, 2)
        self.assertTrue(all(c.kwargs["request_id"] == "stable" for c in call.call_args_list))
        self.assertTrue(all(c.kwargs["allow_external"] for c in call.call_args_list))

    def test_pending_request_stops_at_deadline(self):
        with patch.object(resilient_llm.openrouter, "complete_json",
                          side_effect=openrouter.CompletionPending("stable")), \
             patch.object(resilient_llm.time, "monotonic", side_effect=[0, 2]):
            with self.assertRaises(openrouter.CompletionPending):
                resilient_llm.complete_json("system", "user", request_id="stable",
                                             resume_timeout=1, poll_interval=1)


if __name__ == "__main__":
    unittest.main()
