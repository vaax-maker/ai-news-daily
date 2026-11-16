import datetime
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aidaily import config
from aidaily.ai_news import extra_sources, pipeline, renderer, source, summarizer, visual_brief, visuals
from aidaily.customer_stories import pipeline as customer_pipeline
from aidaily.integrations import article_reader, openrouter
from aidaily.notifications import daily_digest
from aidaily.publishing import search_index
from aidaily.publishing.highlights import select_highlights
from aidaily.publishing import youtube_summaries as youtube_publishing
from aidaily.youtube_summaries import analyzer as youtube_analyzer
from aidaily.youtube_summaries import pipeline as youtube_pipeline


class KeyLoadingTests(unittest.TestCase):
    def test_key_from_file_accepts_env_syntax(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text('OPENROUTER_API_KEY="secret-value"\n', encoding="utf-8")
            self.assertEqual(openrouter._key_from_file(path), "secret-value")

    def test_key_from_file_ignores_similar_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("OPENROUTER_API_KEY_OLD=not-the-key\n", encoding="utf-8")
            self.assertEqual(openrouter._key_from_file(path), "")


class RuntimePathTests(unittest.TestCase):
    def test_ai_news_seen_store_lives_under_shared_data_root(self):
        self.assertEqual(
            Path(extra_sources._DEFAULT_SEEN_PATH),
            config.DATA_ROOT / "ai_news" / "extra_seen.json",
        )

    def test_external_media_limits_accept_explicit_override(self):
        with mock.patch.object(extra_sources, "_fetch_rss_source", return_value=[]) as rss, \
             mock.patch.object(extra_sources, "_fetch_aibase", return_value=[]):
            extra_sources.fetch_extra(limit_per_source=99)
        self.assertEqual([call.args[3] for call in rss.call_args_list], [99, 99, 99])

    def test_late_refresh_counts_restored_external_cards_against_limit(self):
        today = {"date": "2026-09-11", "stories": [
            {"n": "01", "source": "aiofmodu", "headline": "source", "url": "a"},
            {"n": "02", "source": "MIT Tech Review", "headline": "old 1", "url": "m1"},
            {"n": "03", "source": "MIT Tech Review", "headline": "old 2", "url": "m2"},
        ]}
        with mock.patch.object(extra_sources, "fetch_extra", return_value=[]) as fetch, \
             mock.patch.object(extra_sources, "load_seen",
                               return_value={"urls": set(), "heads": set(), "entries": []}):
            extra_sources.merge_into(today)
        requested = fetch.call_args.kwargs["limit_per_source"]
        self.assertEqual(requested["MIT Tech Review"], 0)
        self.assertEqual(len([story for story in today["stories"]
                              if story.get("source") == "MIT Tech Review"]), 2)

    def test_same_publication_date_is_removed_from_seen_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "seen.json"
            path.write_text(json.dumps({"entries": [
                {"url": "https://today", "headline_norm": "today", "date": "2026-09-08"},
                {"url": "https://older", "headline_norm": "older", "date": "2026-09-07"},
            ]}), encoding="utf-8")
            store = extra_sources.load_seen(str(path), ignore_date="2026-09-08")
        self.assertNotIn("https://today", store["urls"])
        self.assertIn("https://older", store["urls"])

    def test_aiofmodu_channel_keeps_curator_and_original_publisher(self):
        story = {
            "source": "aiofmodu",
            "url": "https://n.news.naver.com/mnews/article/001/1",
        }
        self.assertEqual(
            search_index._story_channel(story),
            "aiofmodu.com · n.news.naver.com",
        )

    def test_external_channel_is_not_repeated(self):
        story = {
            "source": "AI타임스",
            "url": "https://www.aitimes.com/news/articleView.html?idxno=1",
        }
        self.assertEqual(search_index._story_channel(story), "aitimes.com")

    def test_legacy_paragraph_is_split_into_display_bullets(self):
        text = "첫 사실이다. 둘째 사실이다. 셋째 사실이다. 넷째 사실이다."
        self.assertEqual(
            search_index._summary_bullets(text),
            ["첫 사실이다.", "둘째 사실이다.", "셋째 사실이다."],
        )

    def test_korean_word_ending_in_da_is_not_split_mid_sentence(self):
        text = "Astra가 Fable보다 5배 빠르다는 사용기가 나왔다. 한도 불만도 있었다."
        self.assertEqual(
            search_index._summary_bullets(text),
            ["Astra가 Fable보다 5배 빠르다는 사용기가 나왔다.", "한도 불만도 있었다."],
        )

    def test_news_keeps_editor_generated_bullets(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "archive"
            archive.mkdir()
            (archive / "index.json").write_text(json.dumps([{
                "date": "2026-09-10",
                "title": "오늘",
                "stories": [{
                    "n": "01", "headline": "기사", "body": "긴 본문이다.",
                    "body_bullets": ["핵심 사실", "두 번째 사실"],
                    "url": "https://example.com/article",
                }],
            }]), encoding="utf-8")
            rows = search_index.load_news(tmp)
        self.assertEqual(rows[0]["summary_bullets"], ["핵심 사실", "두 번째 사실"])


class JsonCompletionTests(unittest.TestCase):
    def test_complete_json_removes_code_fence(self):
        payload = {"ok": True, "items": [1, 2]}
        with mock.patch.object(openrouter, "complete", return_value=f"```json\n{json.dumps(payload)}\n```"):
            self.assertEqual(openrouter.complete_json("system", "user"), payload)


class OutlineTests(unittest.TestCase):
    def test_missing_generated_json_uses_sentence_fallback(self):
        stories = [{
            "n": "01",
            "headline": "제목",
            "body": "첫 문장이다. 둘째 문장이다.",
            "takeaway": "중요한 이유다.",
        }]
        with mock.patch.object(summarizer.openrouter, "KEY", ""), \
             mock.patch.object(summarizer, "_call", return_value=None):
            result = summarizer.summarize_stories(stories)
        self.assertEqual(result[0]["body_bullets"], ["첫 문장이다.", "둘째 문장이다."])
        self.assertEqual(result[0]["why_bullets"], ["중요한 이유다."])

    def test_sentence_fallback_does_not_split_korean_word_ending_in_da(self):
        stories = [{
            "n": "01", "headline": "제목",
            "body": "생성 지연 시간은 이전 모델보다 최대 50% 줄었습니다. 편집력도 좋아졌습니다.",
            "takeaway": "사용성이 개선됐습니다.",
        }]
        result = summarizer._fallback(stories)
        self.assertEqual(result[0]["body"][0], "생성 지연 시간은 이전 모델보다 최대 50% 줄었습니다.")

    def test_shared_llm_result_is_applied(self):
        stories = [{"n": "01", "headline": "제목", "body": "본문", "takeaway": "이유"}]
        generated = [{"n": "01", "body": ["핵심"], "why": ["영향"]}]
        with mock.patch.object(summarizer.openrouter, "KEY", "key"), \
             mock.patch.object(summarizer, "_call", return_value=generated):
            result = summarizer.summarize_stories(stories)
        self.assertEqual(result[0]["body_bullets"], ["핵심"])
        self.assertEqual(result[0]["why_bullets"], ["영향"])


class BuildTests(unittest.TestCase):
    def test_article_reader_extracts_naver_style_body(self):
        body = " ".join(["기사 원문에 포함된 핵심 문장입니다."] * 8)
        document = (f'<html><div class="ad">광고</div><div id="dic_area"><p>{body}<br>끝.</p></div>'
                    '<div class="footer">기사 밖의 매우 긴 추천 콘텐츠와 댓글</div></html>')
        self.assertEqual(article_reader.extract_article_text(document), f"{body} 끝.")

    def test_visual_brief_uses_original_article_and_structured_result(self):
        stories = [{
            "n": "01", "headline": "기사", "url": "https://example.com/news",
            "body": "짧은 요약", "takeaway": "의미",
        }]
        generated = [{
            "n": "01", "message": "생활 채널에서 공공업무까지 연결",
            "layout": "flow", "nodes": ["카카오톡", "모두의 AI", "신청·결제"],
            "metrics": ["2030년 3,000만 명"], "constraints": ["개인정보 기준"],
        }]
        original = "원문에서 수집한 충분히 긴 기사 본문 " * 20
        with mock.patch.object(article_reader, "fetch_article_text", return_value=original), \
             mock.patch.object(visual_brief.openrouter, "KEY", "key"), \
             mock.patch.object(visual_brief, "_call", return_value=generated) as call:
            visual_brief.enrich_stories(stories)
        self.assertEqual(stories[0]["article_text"], original)
        self.assertEqual(stories[0]["visual_brief"]["layout"], "flow")
        self.assertEqual(stories[0]["visual_brief"]["metrics"], ["2030년 3,000만 명"])
        self.assertEqual(call.call_args.args[0][0]["article_text"], original)

    def test_hero_prompt_requires_story_driven_three_source_layout(self):
        brief = {
            "date": "2026-09-08",
            "title": "오늘",
            "stories": [{"headline": "오늘 뉴스", "body": "a", "takeaway": "a", "source": "aiofmodu"}],
            "customer_story": {"headline": "사용자의 고민", "body": "고민", "source": "고객사용기", "channel": "Reddit"},
            "youtube_story": {"headline": "오늘 영상", "body": "영상 요약", "takeaway": "영상 의미", "source": "오늘 유튜브", "channel": "테크 채널"},
        }
        for item in brief["stories"] + [brief["customer_story"], brief["youtube_story"]]:
            item["report_date"] = brief["date"]
            item.setdefault("body", "검증된 당일 본문")
        content, instruction = visuals._hero_content_and_instruction(brief)
        self.assertIn("에디토리얼 앤솔로지", instruction)
        self.assertIn("TODAY_COMMON_QUESTION을 가장 크고 먼저", instruction)
        self.assertIn("모바일 축소 가독성", instruction)
        self.assertIn("#2E5FE0", instruction)
        self.assertIn("#F7F5EF", instruction)
        self.assertIn("원형 프레임", instruction)
        self.assertIn("고객사용기: Reddit", instruction)
        self.assertIn("MODE: THREE_VIGNETTES", content)
        self.assertIn("TODAY_COMMON_QUESTION: 오늘", content)
        self.assertIn("SCENE_1:", content)
        self.assertIn("TODAY_REMAINING_QUESTION:", content)
        self.assertIn("SOURCE_FOOTER:", content)
        self.assertNotIn("CAUSAL_EVIDENCE:", content)
        self.assertIn("고객사용기의 한 장면", content)
        self.assertIn("출처 Reddit", content)
        self.assertIn("출처 테크 채널", content)
        self.assertIn("출처 aiofmodu", content)

    def test_hero_prompt_uses_structured_visual_brief(self):
        visual = {
            "message": "생활 채널에서 공공업무까지 연결", "layout": "flow",
            "nodes": ["카카오톡", "모두의 AI", "신청·결제"],
            "metrics": ["2030년 3,000만 명"], "constraints": ["개인정보 기준"],
        }
        brief = {"date": "2026-09-18", "title": "오늘", "stories": [
            {"headline": "aiofmodu 기사", "source": "aiofmodu", "visual_brief": visual},
        ], "customer_story": {"headline": "고객 이야기", "source": "고객사용기", "visual_brief": visual},
        "youtube_story": {"headline": "오늘 영상", "source": "오늘 유튜브", "visual_brief": visual}}
        for item in brief["stories"] + [brief["customer_story"], brief["youtube_story"]]:
            item["report_date"] = brief["date"]
            item.setdefault("body", "검증된 당일 본문")
        content, _ = visuals._hero_content_and_instruction(brief)
        self.assertIn("시각화 형식: flow", content)
        self.assertIn("카카오톡 / 모두의 AI / 신청·결제", content)
        self.assertIn("강조 수치: 2030년 3,000만 명", content)

    def test_anthology_prompt_forbids_causal_story_between_vignettes(self):
        brief = {"date": "2026-10-10", "title": "오늘의 공통 질문", "stories": [
            {"headline": "독립 뉴스", "source": "aiofmodu"}],
            "customer_story": {"headline": "고객 단편", "source": "Reddit"},
            "youtube_story": {"headline": "영상 단편", "source": "테크 채널"}}
        for item in brief["stories"] + [brief["customer_story"], brief["youtube_story"]]:
            item["report_date"] = brief["date"]
            item.setdefault("body", "검증된 당일 본문")
        content, instruction = visuals._hero_content_and_instruction(brief)
        self.assertIn("MODE: THREE_VIGNETTES", content)
        self.assertIn("서로 다른 주인공과 공간", instruction)
        self.assertIn("단편 사이에 인과관계를 만들지 않는다", instruction)
        self.assertIn("원인·해법·결과", instruction)

    def test_hero_uses_customer_youtube_and_news_story_order(self):
        brief = {"date": "2026-09-10", "title": "오늘", "stories": [
            {"headline": "뉴스 1", "body": "첫째", "source": "aiofmodu"},
            {"headline": "뉴스 2", "body": "둘째", "source": "aiofmodu"},
        ], "customer_story": {"headline": "고객 이야기", "body": "고객", "source": "고객사용기"},
        "youtube_story": {"headline": "오늘 영상", "body": "영상", "source": "오늘 유튜브"}}
        for item in brief["stories"] + [brief["customer_story"], brief["youtube_story"]]:
            item["report_date"] = brief["date"]
            item.setdefault("body", "검증된 당일 본문")
        content, _ = visuals._hero_content_and_instruction(brief)
        self.assertIn("고객 이야기", content)
        self.assertIn("오늘 영상", content)
        self.assertIn("뉴스 1", content)
        self.assertNotIn("뉴스 2", content)
        self.assertLess(content.index("고객 이야기"), content.index("오늘 영상"))
        self.assertLess(content.index("오늘 영상"), content.index("뉴스 1"))

    def test_hero_fails_when_required_story_source_is_missing(self):
        brief = {"date": "2026-09-10", "title": "오늘", "stories": [
            {"headline": "뉴스 1", "body": "첫째", "source": "aiofmodu"},
        ], "youtube_story": {"headline": "오늘 영상", "source": "오늘 유튜브"}}
        with mock.patch.object(visuals, "_today_customer_story", return_value=None), \
             self.assertRaisesRegex(RuntimeError, "고객사용기 1건"):
            visuals._hero_content_and_instruction(brief)

    def test_customer_stories_are_grouped_by_source_with_four_topic_limit(self):
        items = ([{"issue": f"레딧 {n}", "sources": ["Reddit"]} for n in range(5)]
                 + [{"issue": f"HN {n}", "sources": ["Hacker News"]} for n in range(2)]
                 + [{"issue": "대화", "sources": ["오픈채팅 · 공개방"]}])
        grouped = customer_pipeline.group_items_by_source(items)
        self.assertEqual([(name, len(rows)) for name, rows in grouped], [("Reddit", 4), ("HN", 2), ("공개방", 1)])

    def test_customer_stories_replace_open_chat_ids_with_room_names(self):
        self.assertEqual(customer_pipeline._short_src("오픈채팅 · 18472466542857243 (비공개 대화)"),
                         "김효율의 AI개발단")

    def test_customer_stories_rejects_merged_or_over_four_source_items(self):
        base = {"title": "테스트", "overview": "테스트", "items": [
            {"issue": f"주제 {i}", "content": "근거", "sources": ["Reddit"]} for i in range(5)
        ]}
        with self.assertRaisesRegex(ValueError, "4개 초과"):
            customer_pipeline._validate(base)
        base["items"] = [{"issue": "주제", "content": "근거", "sources": ["Reddit", "Hacker News"]}] * 3
        with self.assertRaisesRegex(ValueError, "정확히 하나"):
            customer_pipeline._validate(base)

    def test_open_chat_community_topics_exclude_web_sources_and_group_by_room(self):
        payloads = [
            {"date": "2026-09-28", "gen": {"items": [
                {"issue": "생성 한도", "category": "사용성", "content": "요약 A", "commentary": "시사점 A",
                 "sources": ["오픈채팅 · 공개방 A", "Reddit"]},
                {"issue": "생성 한도", "category": "사용성", "content": "요약 B", "commentary": "시사점 B",
                 "sources": ["오픈채팅 · 공개방 A"]},
                {"issue": "에이전트 보안", "category": "신뢰", "content": "요약 C", "commentary": "시사점 C",
                 "sources": ["오픈채팅 · 공개방 B"]},
                {"issue": "표시 제외", "category": "신뢰", "content": "요약 D", "commentary": "시사점 D",
                 "sources": ["오픈채팅 · 18475047644735325"]},
            ]}},
        ]
        rooms = customer_pipeline.build_open_chat_community_topics(payloads)
        self.assertEqual([room["name"] for room in rooms], ["공개방 A", "공개방 B"])
        self.assertEqual(rooms[0]["activity"], 2)
        self.assertEqual(rooms[0]["topics"][0]["count"], 2)
        page = customer_pipeline.render_open_chat_community_page(rooms, "2026-09-28")
        self.assertIn("role=\"tablist\"", page)
        self.assertIn("공개방 A", page)
        self.assertNotIn("Reddit", page)
        self.assertNotIn("18475047644735325", page)

    def test_all_aiofmodu_editions_on_publication_date_are_combined(self):
        items = [
            {"date": "2026-09-08", "title": "첫 판", "stories": [
                {"n": "01", "headline": "A", "url": "https://a"},
            ]},
            {"date": "2026-09-08", "title": "둘째 판", "stories": [
                {"n": "01", "headline": "B", "url": "https://b"},
            ]},
            {"date": "2026-09-07", "title": "어제", "stories": []},
        ]
        today, archive = pipeline._combine_editions_for_date(items, "2026-09-08")
        self.assertEqual([story["headline"] for story in today["stories"]], ["A", "B"])
        self.assertEqual([story["n"] for story in today["stories"]], ["01", "02"])
        self.assertEqual([item["date"] for item in archive], ["2026-09-08", "2026-09-07"])

    def test_source_refresh_restores_external_stories_and_bullets(self):
        fetched = [{
            "date": "2026-09-10", "stories": [{
                "headline": "모두의AI 기사", "url": "https://news.example/a",
                "source": "aiofmodu", "body": "본문", "takeaway": "의미",
            }],
        }]
        published = [{
            "date": "2026-09-10", "stories": [
                {
                    "headline": "모두의AI 기사", "url": "https://news.example/a",
                    "source": "aiofmodu", "body_bullets": ["기존 불릿"],
                },
                {
                    "headline": "외부 기사", "url": "https://external.example/b",
                    "source": "MIT Tech Review", "body": "외부 본문",
                },
            ],
        }]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.json"
            path.write_text(json.dumps(published), encoding="utf-8")
            restored = pipeline._restore_published_archive(fetched, str(path))
        self.assertEqual(len(restored[0]["stories"]), 2)
        self.assertEqual(restored[0]["stories"][0]["body_bullets"], ["기존 불릿"])
        self.assertEqual(restored[0]["stories"][1]["source"], "MIT Tech Review")

    def test_web_only_bullets_do_not_replace_existing_editor_bullets(self):
        stories = [
            {"n": "01", "body": "본문이다.", "takeaway": "의미다.",
             "body_bullets": ["편집 불릿"], "why_bullets": ["편집 의미"]},
            {"n": "02", "body": "첫 문장이다. 둘째 문장이다.", "takeaway": "중요하다."},
        ]
        pipeline._ensure_bullets_without_api(stories)
        self.assertEqual(stories[0]["body_bullets"], ["편집 불릿"])
        self.assertEqual(stories[1]["body_bullets"], ["첫 문장이다.", "둘째 문장이다."])

    def test_web_only_can_refresh_aiofmodu_bullets_from_source_text(self):
        stories = [{
            "n": "01", "source": "aiofmodu",
            "body": "생성 지연 시간은 이전 모델보다 최대 50% 줄었습니다. 편집력도 개선됐습니다.",
            "takeaway": "사용성이 좋아졌습니다.",
            "body_bullets": ["생성 지연 시간은 이전 모델보다"],
        }]
        pipeline._ensure_bullets_without_api(stories, refresh_sources={"aiofmodu"})
        self.assertEqual(
            stories[0]["body_bullets"][0],
            "생성 지연 시간은 이전 모델보다 최대 50% 줄었습니다.",
        )

    def test_daily_page_uses_horizontal_hero_only(self):
        brief = {
            "date": "2026-09-09", "title": "오늘", "summary": "요약",
        }
        page = renderer.render_daily(brief, [], "hero.png")
        self.assertIn('src="hero.png?d=2026-09-09"', page)
        self.assertIn('/hero.png?d=2026-09-09', page)
        self.assertNotIn("infographic.png", page)

    def test_missing_hero_has_no_social_image_fallback(self):
        page = renderer.render_daily({'date': '2026-10-12', 'title': '오늘', 'summary': '요약'}, [], None)
        self.assertNotIn('property="og:image"', page)
        self.assertNotIn('name="twitter:image"', page)
        self.assertIn('name="twitter:card" content="summary"', page)

    def test_offline_build_writes_expected_outputs(self):
        today = datetime.date.today().isoformat()
        brief = {
            "date": today,
            "newsTime": today,
            "title": "테스트 제목",
            "summary": "테스트 요약",
            "stories": [{
                "n": "01", "headline": "기사", "body": "본문", "takeaway": "이유",
            }],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "input.png"
            image.write_bytes(b"png-placeholder")
            docs = root / "docs"
            with mock.patch.object(source, "fetch_all", return_value=[brief]), \
                 mock.patch.object(extra_sources, "merge_into"), \
                 mock.patch.object(summarizer, "summarize_stories", return_value=brief["stories"]), \
                 mock.patch.object(renderer, "render_daily", return_value="<html>daily</html>"), \
                 mock.patch.object(renderer, "render_archive", return_value="<html>archive</html>"), \
                 mock.patch.object(sys, "argv", [
                     "aidaily.ai_news.pipeline", "--docs-root", str(docs),
                     "--reuse-hero", str(image),
                 ]):
                pipeline.main()
            self.assertEqual((docs / "daily.html").read_text(), "<html>daily</html>")
            self.assertEqual((docs / "archive.html").read_text(), "<html>archive</html>")
            self.assertTrue((docs / "archive" / "index.json").is_file())
            self.assertFalse((docs / "hero.png").exists())
            self.assertEqual(image.read_bytes(), b"png-placeholder")
            self.assertFalse(json.loads((docs / "hero.manifest.json").read_text())["active"])
            self.assertFalse((docs / "infographic.png").exists())


class UnifiedSchemaTests(unittest.TestCase):
    def test_highlights_are_compact_exact_phrases(self):
        summary = (
            "정부는 2027년부터 해외의 한국인 최상위 AI 연구자와 개발자의 국내 복귀를 지원합니다. "
            "연간 250억원을 투입하며 연구 환경과 GPU 확보를 함께 지원합니다. "
            "글로벌 수준의 보상 체계를 마련하는 것이 사업 성패를 좌우합니다."
        )
        phrases = select_highlights(summary, "AI 인재 귀환 나선 정부")
        self.assertGreaterEqual(len(phrases), 1)
        self.assertLessEqual(len(phrases), 2)
        for phrase in phrases:
            self.assertIn(phrase, summary)
            self.assertGreaterEqual(len(phrase), 10)
            self.assertLessEqual(len(phrase), 36)
            self.assertRegex(phrase, r"[가-힣A-Za-z]{2}")
            self.assertIsNone(re.search(r"(?:은|는|이|가|을|를|의|와|과|하며|하고|등|및)$", phrase))

    def test_aggregate_title_list_has_no_highlight(self):
        self.assertEqual(select_highlights("첫 영상 · 둘째 영상 · 셋째 영상", "브리프"), [])

    def test_canonical_kinds_are_used(self):
        records = [
            {"date": "2026-09-07", "pub": "뉴스", "url": "https://example/a", "n": "01"},
            {"date": "2026-09-07", "pub": "고객사용기", "url": "https://example/b", "customer_story_index": 0},
            {"date": "2026-09-07", "pub": "개별리포트", "url": "https://example/c.html"},
        ]
        search_index.enrich_unified(records)
        self.assertEqual(
            [record["kind"] for record in records],
            ["ai_news", "customer_story", "youtube_summary"],
        )

    def test_notification_reads_canonical_kinds(self):
        store = [
            {"date": "2026-09-07", "kind": "ai_news", "title": "뉴스"},
            {"date": "2026-09-07", "kind": "youtube_summary", "pub": "개별리포트",
             "cat": "tech", "title": "기술 영상"},
            {"date": "2026-09-07", "kind": "youtube_summary", "pub": "개별리포트",
             "cat": "econ", "title": "경제 영상"},
            {"date": "2026-09-07", "kind": "youtube_summary", "pub": "브리프",
             "cat": "tech", "title": "종합 브리프"},
            {"date": "2026-09-07", "kind": "customer_story", "title": "사용기"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "search-index.json"
            path.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")
            text = daily_digest.build_caption({"date": "2026-09-07"}, path)
        self.assertIn("AI뉴스 1건", text)
        self.assertIn("YouTube 요약 2건 (AI·기술 1 · 경제 1)", text)
        self.assertNotIn("종합 브리프", text)
        self.assertIn("고객 사용기 1건", text)
        self.assertNotIn("경제 YouTube", text)
        self.assertNotIn("%EA%B2%BD%EC%A0%9C.html", text)
        self.assertIn(
            f"{daily_digest.TECH_URL}?date=2026-09-07",
            text,
        )
        self.assertEqual(text.count("https://"), 1)


class YouTubePublishingTests(unittest.TestCase):
    def test_queue_merge_preserves_sent_and_existing_messages(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            path.write_text(json.dumps({
                "date": "2026-09-06",
                "messages": {"old": {"text": "old"}},
                "sent": ["old"],
            }), encoding="utf-8")
            merged, new_slugs = youtube_publishing._merge_queue(
                path, {"new": {"text": "new"}}, "2026-09-07"
            )
        self.assertEqual(merged["sent"], ["old"])
        self.assertEqual(set(merged["messages"]), {"old", "new"})
        self.assertEqual(new_slugs, ["new"])


class YouTubeReportTests(unittest.TestCase):
    @staticmethod
    def _rich_analysis():
        return {
            "category": "tech",
            "headline": "긴 영상의 핵심을 여덟 섹션으로 정리한 완결형 제목입니다",
            "card_summary": "영상 전체 흐름과 적용 사례를 함께 짚는 심층 요약",
            "slug_hint": "rich-report",
            "overview": [f"핵심 개요 {index}" for index in range(1, 5)],
            "sections": [
                {"title": title, "bullets": [f"{title}의 구체 내용 {index}" for index in range(1, 4)]}
                for title in (
                    "클라우드 VM의 작업 환경", "브라우저 화면을 읽는 방식", "Slack에서 작업을 전달하는 과정",
                    "피드백 재사용의 전략적 의미", "코드 렌더링 검증", "재사용 스킬과 적용 범위",
                )
            ],
            "glossary": [
                {"term": f"용어 {index}", "definition": f"영상 맥락에 따른 정의 {index}"}
                for index in range(1, 4)
            ],
        }

    def test_markdown_has_exactly_eight_sections(self):
        markdown = youtube_pipeline.build_markdown(self._rich_analysis(), "리포트 제목")
        headings = re.findall(r"^## (.+)$", markdown, re.M)
        self.assertEqual(len(headings), 8)
        self.assertEqual(headings[0], "핵심 개요")
        self.assertEqual(headings[-1], "용어 사전")
        self.assertNotIn("핵심 내용", headings)
        self.assertNotIn("왜 중요한가", headings)
        self.assertIn("| 용어 1 | 영상 맥락에 따른 정의 1 |", markdown)

    def test_analyzer_rejects_two_section_drift(self):
        thin = {
            "category": "tech", "headline": "제목", "card_summary": "요약",
            "overview": ["1", "2", "3", "4"],
            "sections": [
                {"title": "핵심 내용", "bullets": ["1", "2", "3"]},
                {"title": "왜 중요한가", "bullets": ["1", "2", "3"]},
            ],
            "glossary": [
                {"term": "A", "definition": "a"},
                {"term": "B", "definition": "b"},
                {"term": "C", "definition": "c"},
            ],
        }
        with self.assertRaisesRegex(RuntimeError, "일반적이거나 중복"):
            youtube_analyzer._validate_report(thin)

    def test_report_validation_derives_queue_bullets_from_topics(self):
        result = youtube_analyzer._validate_report(self._rich_analysis())
        self.assertEqual(result["body_bullets"], [s["bullets"][0] for s in result["sections"][:4]])
        self.assertEqual(result["why_bullets"], result["sections"][3]["bullets"][:2])

    def test_extra_story_topic_is_preserved_with_dynamic_glossary_number(self):
        analysis = self._rich_analysis()
        analysis["sections"].append({
            "title": "추가 전망",
            "bullets": ["추가 사실 하나", "추가 사실 둘", "추가 사실 셋"],
        })
        result = youtube_analyzer._validate_report(analysis)
        self.assertEqual(len(result["sections"]), 7)
        self.assertIn("추가 사실 하나", result["sections"][-1]["bullets"])
        markdown = youtube_pipeline.build_markdown(result, "리포트 제목")
        self.assertEqual(len(re.findall(r"^## ", markdown, re.M)), 8)


if __name__ == "__main__":
    unittest.main()
