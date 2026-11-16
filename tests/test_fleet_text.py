"""Exercise the real common receipt client with isolated, mocked transports."""
import io
import json
import os
import ssl
import tempfile
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from aidaily.integrations import openrouter as llm
from aidaily.ai_news import summarizer, visual_brief, extra_sources
from aidaily.customer_stories import pipeline as customer
from aidaily.youtube_summaries import pipeline as youtube


def response(text='{"ok": true, "summary": "근거를 유지한 요약"}', model="qwen3.8-27b"):
    return {"id": "completion-test", "model": model,
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 18, "total_tokens": 30}}


def http_error(code):
    return urllib.error.HTTPError("https://fixture.invalid", code, "fixture", {}, None)


class FleetTextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = self.root / "registry.json"
        self.registry.write_text(json.dumps({"tailnet": "fixture.ts.net", "hosts": {
            "pro": {"tailscale": "pro"}}, "services": {"abot-inference": {
            "host": "pro", "endpoints": {"api_tailnet": "https://pro.fixture.ts.net:9444"}}}}))
        self.auth = self.root / "auth"
        self.auth.write_text("unit-test:dummy")
        self.fleet = llm._fleet_module()
        self.client_class = self.fleet.InferenceClient
        self.patch(mock.patch.dict(os.environ, {"AIDAILY_LLM_STATE_DIR": str(self.root / "state")}))
        self.patch(mock.patch.object(llm, "KEY", "fixture-key"))
        self.patch(mock.patch.object(self.fleet, "InferenceClient", side_effect=self.client))
        self.health = self.patch(mock.patch.object(self.client_class, "health", return_value={
            "capabilities": {"chat": {"ready": True}}}))
        self.network = self.patch(mock.patch.object(self.client_class, "json_request", side_effect=self.transport))
        self.content = self.patch(mock.patch.object(self.client_class, "request", side_effect=lambda *a, **k:
                                                   io.BytesIO(json.dumps(response()).encode())))
        self.external = self.patch(mock.patch.object(llm, "request_json", return_value=response(model="external-fixture")))
        self.posts = []

    def patch(self, p):
        value = p.start()
        self.addCleanup(p.stop)
        return value

    def client(self, project, state_dir):
        return self.client_class(project, registry=self.registry, auth_file=self.auth, state_dir=state_dir)

    def transport(self, method, path, data=None, **kw):
        if method == "POST":
            self.posts.append(data)
            return {"id": "job-test"}
        return {"id": "job-test", "status": "succeeded"}

    def complete(self, **kwargs):
        return llm.complete("한국어로 근거만 요약한다", "GPU 작업은 한 번에 한 건 실행한다.", **kwargs)

    def receipt(self):
        paths = list((self.root / "state").glob("*.json"))
        self.assertEqual(len(paths), 1)
        return json.loads(paths[0].read_text())

    def test_same_call_local_success_mapping_keyless_and_project_tags(self):
        llm.KEY = ""
        self.assertEqual(json.loads(self.complete())["ok"], True)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.posts[0]["project"], "AI-Daily")
        client = llm._new_client(self.root / "state")
        self.assertEqual(client.headers["X-Title"], "AI-Daily")
        self.assertEqual(client.headers["HTTP-Referer"], "https://ai-daily.local")
        self.assertEqual(llm.last_usage()["cost_usd"], 0.0)
        self.assertEqual(llm.last_usage()["usage"]["total_tokens"], 30)
        self.assertEqual(llm.last_usage()["model"], "qwen3.8-27b")
        self.external.assert_not_called()

    def test_cached_resume_preserves_id_no_second_submission(self):
        first = self.complete()
        first_id = llm.last_usage()["request_id"]
        self.assertEqual(self.complete(), first)
        self.assertEqual(llm.last_usage()["request_id"], first_id)
        self.assertEqual(len(self.posts), 1)
        self.assertEqual(self.receipt()["state"], "succeeded")

    def test_explicit_id_cannot_be_rebound(self):
        self.complete(request_id="daily:2026-10-01:news")
        with self.assertRaises(ValueError):
            llm.complete("changed", "input", request_id="daily:2026-10-01:news")
        self.assertEqual(len(self.posts), 1)

    def test_offline_fallback_has_original_contract_headers_and_receipt(self):
        self.health.side_effect = urllib.error.URLError(ConnectionRefusedError())
        self.assertIn("summary", json.loads(self.complete()))
        self.external.assert_called_once()
        args, kw = self.external.call_args
        self.assertEqual(args[0], llm.URL)
        self.assertEqual(kw["headers"]["X-Title"], "AI-Daily")
        self.assertEqual(kw["headers"]["HTTP-Referer"], "https://ai-daily.local")
        body = json.loads(kw["data"])
        self.assertEqual(body["messages"][1]["content"], "GPU 작업은 한 번에 한 건 실행한다.")
        self.assertEqual(self.receipt()["provider_job_id"], "completion-test")
        self.assertIsNone(llm.last_usage()["cost_usd"])
        self.assertEqual(llm.last_usage()["provider"], "openrouter")
        self.complete()
        self.external.assert_called_once()

    def test_long_transcript_and_token_capability_fallback_without_truncation(self):
        long = "자막" * 9000
        llm.complete("system", long, max_tokens=15000)
        self.health.assert_not_called()
        self.network.assert_not_called()
        body = json.loads(self.external.call_args.kwargs["data"])
        self.assertEqual(body["messages"][1]["content"], long)
        self.assertEqual(body["max_tokens"], 15000)

    def test_busy_resumes_same_request_and_never_pays(self):
        self.network.side_effect = http_error(429)
        with self.assertRaises(llm.CompletionPending) as first:
            self.complete()
        self.network.side_effect = self.transport
        self.complete()
        self.assertEqual(self.posts[0]["request_id"], first.exception.request_id)
        self.external.assert_not_called()

    def test_uncertain_submit_found_in_same_call(self):
        def transport(method, path, data=None, **kw):
            if method == "POST":
                self.posts.append(data)
                raise urllib.error.URLError(TimeoutError())
            if "/requests?" in path:
                return {"id": "job-test"}
            return {"status": "succeeded"}
        self.network.side_effect = transport
        self.complete()
        self.assertEqual(len(self.posts), 1)
        self.external.assert_not_called()

    def test_uncertain_submit_then_503_does_not_pay(self):
        self.network.side_effect = urllib.error.URLError(TimeoutError())
        with self.assertRaises(llm.CompletionPending): self.complete()
        self.network.side_effect = http_error(503)
        with self.assertRaises(llm.CompletionPending): self.complete()
        self.external.assert_not_called()

    def test_accepted_poll_error_resumes_without_post(self):
        def transport(method, path, data=None, **kw):
            if method == "POST":
                self.posts.append(data)
                return {"id": "job-test"}
            raise urllib.error.URLError(TimeoutError())
        self.network.side_effect = transport
        with self.assertRaises(llm.CompletionPending): self.complete()
        self.network.side_effect = self.transport
        self.complete()
        self.assertEqual(len(self.posts), 1)
        self.external.assert_not_called()

    def test_auth_and_tls_health_never_fallback(self):
        for exc in [http_error(401), http_error(403), ssl.SSLError("TLS failure"),
                    urllib.error.URLError(ssl.SSLError("TLS failure")),
                    urllib.error.URLError(ssl.SSLCertVerificationError("certificate"))]:
            with self.subTest(type=type(exc).__name__):
                self.health.side_effect = exc
                with self.assertRaises(llm.RoutingBlocked): self.complete(request_id=str(id(exc)))
        self.external.assert_not_called()

    def test_post_auth_never_fallback(self):
        self.network.side_effect = http_error(401)
        with self.assertRaises(llm.RoutingBlocked): self.complete()
        self.external.assert_not_called()

    def test_engine_failure_only_confirmed_failure_can_fallback(self):
        self.network.side_effect = lambda method, path, data=None, **kw: (
            {"id": "job-test"} if method == "POST" else
            {"status": "failed", "error_code": "engine_failed"})
        self.complete()
        self.external.assert_called_once()

    def test_interrupted_engine_never_fallback(self):
        self.network.side_effect = lambda method, path, data=None, **kw: (
            {"id": "job-test"} if method == "POST" else
            {"status": "failed", "error_code": "worker_interrupted"})
        with self.assertRaises(llm.CompletionPending): self.complete()
        self.external.assert_not_called()

    def test_external_timeout_never_retried_even_by_new_call(self):
        self.health.side_effect = urllib.error.URLError(ConnectionRefusedError())
        self.external.side_effect = TimeoutError()
        for _ in range(2):
            with self.assertRaises(llm.CompletionPending): self.complete(retries=10)
        self.external.assert_called_once()
        self.assertEqual(self.receipt()["state"], "external_pending")

    def test_external_missing_content_records_id_before_review(self):
        self.health.side_effect = http_error(503)
        self.external.return_value = {"id": "accepted-paid-fixture"}
        with self.assertRaises(llm.RoutingBlocked): self.complete()
        self.assertEqual(self.receipt()["provider_job_id"], "accepted-paid-fixture")
        with self.assertRaises(llm.CompletionPending): self.complete()
        self.external.assert_called_once()

    def test_malformed_local_quality_never_paid(self):
        self.content.side_effect = lambda *a, **k: io.BytesIO(json.dumps(response(text="")).encode())
        with self.assertRaises(llm.RoutingBlocked): self.complete()
        self.external.assert_not_called()

    def test_known_not_ready_can_fallback_before_submission(self):
        self.health.return_value = {"capabilities": {"chat": {"ready": False}}}
        self.complete()
        self.network.assert_not_called()
        self.external.assert_called_once()

    def test_explicit_model_404_rejection_can_use_next_model(self):
        self.health.side_effect = http_error(503)
        self.external.side_effect = [http_error(404), response(model="second")]
        self.complete(models=["first", "second"], retries=9)
        self.assertEqual(self.external.call_count, 2)
        models = [json.loads(call.kwargs["data"])["model"] for call in self.external.call_args_list]
        self.assertEqual(models, ["first", "second"])

    def test_paid_auth_error_does_not_try_chain(self):
        self.health.side_effect = http_error(503)
        self.external.side_effect = http_error(401)
        with self.assertRaises(llm.CompletionPending): self.complete(models=["first", "second"])
        self.external.assert_called_once()

    def test_accepted_job_wait_deadline_never_fallback(self):
        with self.assertRaises(llm.CompletionPending): self.complete(timeout=0)
        self.assertEqual(len(self.posts), 1)
        self.external.assert_not_called()
        self.complete()
        self.assertEqual(len(self.posts), 1)

    def test_failed_content_download_stays_pending(self):
        self.content.side_effect = urllib.error.URLError(TimeoutError())
        with self.assertRaises(llm.CompletionPending): self.complete()
        self.external.assert_not_called()

    def test_concurrent_identical_requests_submit_once(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.complete(), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.posts), 1)


class JsonQualityTests(unittest.TestCase):
    def test_local_final_array_close_repair_preserves_escaped_text(self):
        broken = '[{"n":"01","why":["literal } ] and \\"quoted\\""}]'
        self.assertEqual(llm._repair_local_delimiters(broken),
                         [{"n":"01", "why":['literal } ] and "quoted"']}])

    def test_delimiter_repair_rejects_truncation_or_missing_values(self):
        for candidate in ['[{"why":["truncated"', '{"why":}', '{"why" ["a"]}',
                          '[{"a":[1}, {"b":[2}, {"c":[3}]']:
            with self.subTest(candidate=candidate):
                self.assertIsNone(llm._repair_local_delimiters(candidate))

    def test_external_invalid_json_still_returns_none(self):
        with mock.patch.object(llm,"complete",return_value='[{"why":["a"}]'), \
             mock.patch.object(llm,"last_usage",return_value={"provider":"openrouter"}):
            self.assertIsNone(llm.complete_json("system","user"))

    def test_local_json_repair_requires_no_model_or_paid_request(self):
        with mock.patch.object(llm,"complete",return_value='[{"why":["a"}]') as call, \
             mock.patch.object(llm,"last_usage",return_value={"provider":"local:qwen3.8"}):
            self.assertEqual(llm.complete_json("system","user"),[{"why":["a"]}])
        call.assert_called_once()


class GeneratorBoundaryTests(unittest.TestCase):
    def test_pending_stops_news_and_visual_generation_even_without_paid_key(self):
        for module, function in [(summarizer, summarizer.summarize_stories),
                                 (visual_brief, lambda rows: visual_brief.enrich_stories(rows, read_originals=False))]:
            with mock.patch.object(llm, "KEY", ""), mock.patch.object(module, "_call", side_effect=llm.CompletionPending("stable")):
                with self.assertRaises(llm.CompletionPending): function([{"n": "01"}])

    def test_customer_pending_does_not_try_next_model_or_pass_judge(self):
        with mock.patch.object(llm, "complete", side_effect=llm.CompletionPending("stable")) as call:
            with self.assertRaises(llm.CompletionPending): customer.generate("fixture", models=["a", "b"])
            self.assertEqual(call.call_count, 1)
            with self.assertRaises(llm.CompletionPending): customer.judge({}, "fixture")

    def test_news_uses_local_without_provider_key(self):
        generated = [{"n": "01", "body": ["핵심"], "why": ["영향"]}]
        rows = [{"n": "01", "headline": "제목", "body": "본문", "takeaway": "이유"}]
        with mock.patch.object(llm, "KEY", ""), mock.patch.object(summarizer, "_call", return_value=generated) as call:
            summarizer.summarize_stories(rows)
        call.assert_called_once()
        self.assertEqual(rows[0]["body_bullets"], ["핵심"])

    def test_extra_news_pending_is_not_silently_skipped(self):
        with mock.patch.object(llm, "KEY", ""), mock.patch.object(llm, "complete_json", side_effect=llm.CompletionPending("stable")):
            with self.assertRaises(llm.CompletionPending):
                extra_sources._summarize_ko({"lang":"ko", "source":"fixture", "title":"title", "body":"body"})

    def test_customer_quality_failure_does_not_submit_next_model(self):
        with mock.patch.object(llm, "complete", return_value='{"items": []}') as call:
            with self.assertRaises(ValueError): customer.generate("fixture", models=["first", "second"])
        call.assert_called_once()

    def test_youtube_pending_stops_before_queue_or_publication(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(youtube, "load_processed_ids", return_value=set()), \
             mock.patch.object(youtube, "load_config", return_value={"channels": []}), \
             mock.patch.object(youtube, "video_metadata", return_value={}), \
             mock.patch.object(youtube, "process_video", side_effect=llm.CompletionPending("stable")), \
             mock.patch.object(youtube, "publish") as publish:
            result = youtube.run(["https://youtu.be/abcdefghijk"],tmp,10)
            self.assertEqual(result["queue"], {})
            self.assertEqual(result["failures"][0]["state"], "review_or_pending")
            publish.assert_not_called()

    def test_existing_publication_history_dedup_is_unchanged(self):
        # User-request flow must skip an already-published ID before fetching,
        # analyzing, writing new queue entries or calling publication.
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(youtube, "load_processed_ids", return_value={"abcdefghijk"}), \
             mock.patch.object(youtube, "load_config", return_value={"channels": []}), \
             mock.patch.object(youtube, "video_metadata") as metadata, \
             mock.patch.object(youtube, "process_video") as process:
            result = youtube.run(["https://youtu.be/abcdefghijk"], tmp, 10)
        self.assertEqual(result["queue"], {})
        metadata.assert_not_called()
        process.assert_not_called()


if __name__ == "__main__": unittest.main()
