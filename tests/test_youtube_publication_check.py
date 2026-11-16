"""Exact-run public delivery checks using private staging and fake HTTPS only."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.parse

from aidaily import config
from aidaily.publishing import youtube_verification as verification

DATE = '2026-11-02'
BASE = 'https://example.invalid/news/'
VIDEO = 'abcdefghijk'
SLUG = DATE + '-current-video'


def jpeg(width=640, height=360):
    # Minimal frame/scan framing for this metadata validator; not a decoded-image fixture.
    frame = bytes([8]) + height.to_bytes(2, 'big') + width.to_bytes(2, 'big') + bytes([1, 1, 0x11, 0])
    return b'\xff\xd8\xff\xc0' + (len(frame) + 2).to_bytes(2, 'big') + frame + b'\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x01\xff\xd9'


class Response(io.BytesIO):
    def __init__(self, body, content_type='text/html', status=200):
        super().__init__(body.encode() if isinstance(body, str) else body)
        self.headers = {'Content-Type': content_type}
        self.status = status


class YoutubePublicationCheckTests(unittest.TestCase):
    @staticmethod
    def topic_report(headings, *, marker=True, numbering='ordered'):
        meta = '<meta name="youtube-report-schema" content="story_topics_v2">' if marker else ''
        if numbering == 'none': meta += '<meta name="youtube-heading-numbering" content="none">'
        cards = ''.join('<section class="card s1" id="s%s"><h2>%s%s</h2><p>본문</p></section>' % (i, '' if numbering == 'none' else '<span class="seq">%02d</span>' % i, name)
                        for i, name in enumerate(headings, 1))
        return ('<html><head>' + meta + '</head><body><p>' + DATE + '</p>'
                '<aside><h2>인포그래픽 설명</h2></aside>' + cards +
                '<iframe src="https://www.youtube.com/embed/' + VIDEO + '"></iframe></body></html>')

    def set_story_report(self, staged, public):
        (self.stage / (SLUG + '.html')).write_text(staged)
        self.receipt['report_hashes'][SLUG] = hashlib.sha256(staged.encode()).hexdigest()
        self.save()
        self.routes[self.report] = (public.replace('</body>', '<img src="assets/ig/' + SLUG + '.jpg"></body>'), 'text/html', 200)

    def test_story_topic_headings_match_exact_staged_report(self):
        heads = ['첫 주제', '둘째 주제', '셋째 주제', '용어 사전']
        report = self.topic_report(heads)
        self.set_story_report(report, report)
        self.assertEqual(self.verify()['youtube_reports'], 1)
        # The dated list and image checks remain mandatory in the new mode.
        self.routes[self.image] = (b'not jpeg', 'image/jpeg', 200)
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_stale_legacy_or_changed_headings_cannot_pass_new_report(self):
        staged = self.topic_report(['첫 주제', '둘째 주제', '셋째 주제', '용어 사전'])
        variants = [self.topic_report(['핵심 개요'] + [f'옛 주제 {i}' for i in range(1, 7)] + ['용어 사전'], marker=False),
                    self.topic_report(['첫 주제', '셋째 주제', '둘째 주제', '용어 사전']),
                    self.topic_report(['첫 주제', '둘째 주제', '용어 사전']),
                    self.topic_report(['첫 주제', '둘째 주제', '셋째 주제', '용어 사전'], marker=False)]
        for public in variants:
            with self.subTest(public=public):
                self.set_story_report(staged, public)
                with self.assertRaises(RuntimeError):
                    self.verify()

    def test_story_numbering_and_final_glossary_are_required(self):
        valid = self.topic_report(['첫 주제', '둘째 주제', '용어 사전'])
        for malformed in (valid.replace('>02</span>', '>03</span>'),
                          valid.replace('용어 사전</h2>', '마지막 내용</h2>')):
            with self.subTest(malformed=malformed):
                self.set_story_report(malformed, malformed)
                self.calls.clear()
                with self.assertRaises(RuntimeError):
                    self.verify()
                self.assertEqual(self.calls, [])

    def test_unnumbered_story_headings_and_legacy_ordered_both_pass(self):
        heads=['첫 주제','둘째 주제','셋째 주제','용어 사전']
        for numbering in ('none','ordered'):
            with self.subTest(numbering=numbering):
                report=self.topic_report(heads,numbering=numbering)
                self.set_story_report(report,report)
                self.assertEqual(self.verify()['youtube_reports'],1)

    def test_unnumbered_stage_rejects_numbered_public_or_bad_metadata(self):
        staged=self.topic_report(['첫 주제','둘째 주제','용어 사전'],numbering='none')
        variants=[staged.replace('<h2>첫 주제','<h2><span class="seq">01</span>첫 주제'),
                  staged.replace('<h2>첫 주제','<h2>1. 첫 주제'),
                  staged.replace('content="none"','content="ordered"'),
                  staged.replace('<meta name="youtube-heading-numbering" content="none">','')]
        for public in variants:
            with self.subTest(public=public):
                self.set_story_report(staged,public)
                with self.assertRaises(RuntimeError):self.verify()

    def test_unnumbered_stage_rejects_hidden_sequence_and_duplicate_metadata(self):
        valid=self.topic_report(['첫 주제','용어 사전'],numbering='none')
        variants=[valid.replace('<h2>첫 주제','<h2><span class="seq">01</span>첫 주제'),
                  valid.replace('content="none">','content="none"><meta name="youtube-heading-numbering" content="none">')]
        for staged in variants:
            with self.subTest(staged=staged):
                self.set_story_report(staged,staged);self.calls.clear()
                with self.assertRaises(RuntimeError):self.verify()
                self.assertEqual(self.calls,[])

    def test_same_titles_with_stale_story_body_cannot_pass(self):
        staged = self.topic_report(['첫 주제', '둘째 주제', '용어 사전'])
        public = staged.replace('<p>본문</p>', '<p>이전 본문</p>', 1)
        self.set_story_report(staged, public)
        with self.assertRaisesRegex(RuntimeError, 'story-topic content differs'):
            self.verify()

    def test_card_whitespace_normalized_but_table_cells_are_compared(self):
        staged = self.topic_report(['첫 주제', '용어 사전']).replace('<p>본문</p>', '<p>내용  하나</p>', 1).replace('<p>본문</p>', '<table><tr><td>용어</td><td>뜻</td></tr></table>', 1)
        self.set_story_report(staged, staged.replace('내용  하나', '내용\n 하나'))
        self.assertEqual(self.verify()['youtube_reports'], 1)
        self.set_story_report(staged, staged.replace('<td>뜻</td>', '<td>이전 뜻</td>'))
        with self.assertRaisesRegex(RuntimeError, 'story-topic content differs'):
            self.verify()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        p = patch.object(config, 'DATA_ROOT', self.root); p.start(); self.addCleanup(p.stop)
        p = patch.object(config, 'TECH_DAILY_URL', BASE + urllib.parse.quote('기술.html')); p.start(); self.addCleanup(p.stop)
        self.stage = self.root / 'youtube_summaries/staging' / DATE
        self.stage.mkdir(parents=True)
        self.tech = BASE + urllib.parse.quote('기술.html') + '?date=' + DATE
        self.econ = BASE + urllib.parse.quote('경제.html') + '?date=' + DATE
        self.report = BASE + SLUG + '.html'
        self.image = BASE + 'assets/ig/' + SLUG + '.jpg'
        self.thumb = BASE + 'assets/ig/thumb/' + SLUG + '.jpg'
        self.brief = BASE + DATE + '-daily-brief-ai.html'
        staged = '<html><p>' + DATE + '</p><iframe src="https://www.youtube.com/embed/' + VIDEO + '"></iframe></html>'
        (self.stage / (SLUG + '.html')).write_text(staged)
        self.receipt = {'date': DATE, 'target_count': 1, 'done_ids': [VIDEO], 'queue': {SLUG: {'category': 'tech'}},
                        'report_hashes': {SLUG: hashlib.sha256(staged.encode()).hexdigest()}}
        self.save()
        self.routes = {
            self.tech: ('<h1>' + DATE + '</h1><a href="./' + SLUG + '.html"><img src="assets/ig/' + SLUG + '.jpg"></a><a href="./' + DATE + '-daily-brief-ai.html">모아보기</a>', 'text/html', 200),
            self.econ: ('<h1>' + DATE + '</h1>', 'text/html', 200),
            self.report: (staged.replace('</html>', '<img src="assets/ig/' + SLUG + '.jpg"></html>'), 'text/html', 200),
            self.brief: ('<h1>2026. 11. 02. (월)</h1><a class="b-card" href="./' + SLUG + '.html"><img src="./assets/ig/thumb/' + SLUG + '.jpg"></a>', 'text/html', 200),
            self.image: (jpeg(), 'image/jpeg', 200), self.thumb: (jpeg(320, 180), 'image/jpeg', 200),
        }
        self.calls = []

    def save(self):
        (self.stage / 'run-status.json').write_text(json.dumps(self.receipt))

    def opener(self, url, **kwargs):
        self.calls.append(url)
        if url not in self.routes:
            raise OSError('fixture resource missing: ' + url)
        return Response(*self.routes[url])

    def verify(self):
        return verification.verify_youtube_publication(DATE, opener=self.opener)

    def test_current_run_list_report_image_and_linked_brief_all_verified(self):
        result = self.verify()
        self.assertEqual({key: result[key] for key in ('youtube_reports', 'youtube_images', 'youtube_thumbnails', 'youtube_briefs')},
                         {'youtube_reports': 1, 'youtube_images': 1, 'youtube_thumbnails': 1, 'youtube_briefs': 1})
        self.assertEqual(result['youtube_evidence'][0]['video_id'], VIDEO)
        self.assertEqual(result['youtube_evidence'][0]['image_dimensions'], [640, 360])
        self.assertEqual(set(self.calls), set(self.routes))

    def test_missing_run_receipt_cannot_use_standalone_queue_or_existing_public_pages(self):
        (self.stage / 'run-status.json').unlink()
        (self.stage / 'daybreak-telegram-queue.json').write_text(json.dumps({'messages': self.receipt['queue']}))
        with self.assertRaises(RuntimeError): self.verify()
        self.assertEqual(self.calls, [])

    def test_only_explicit_zero_target_run_can_return_zero_without_network(self):
        self.receipt.update(target_count=0, done_ids=[], queue={}); self.save()
        result = self.verify()
        self.assertEqual(result['youtube_reports'], 0)
        self.assertEqual(self.calls, [])
        self.receipt['target_count'] = 1; self.save()
        with self.assertRaises(RuntimeError): self.verify()

    def test_corrupt_incomplete_and_duplicate_receipts_fail_before_network(self):
        original = json.loads(json.dumps(self.receipt))
        for changes in ({'date': '2026-11-01'}, {'queue': {}}, {'done_ids': []}, {'done_ids': [VIDEO, VIDEO]}, {'report_hashes': {}}, {'target_count': -1}, {'target_count': True}, {'queue': {'messages': original['queue']}}):
            with self.subTest(changes=changes):
                self.receipt = dict(original); self.receipt.update(changes); self.save()
                with self.assertRaises(RuntimeError): self.verify()
        self.assertEqual(self.calls, [])

    def test_staged_hash_and_source_id_must_match_this_run(self):
        original = (self.stage / (SLUG + '.html')).read_text()
        (self.stage / (SLUG + '.html')).write_text(original + '<!--changed-->')
        with self.assertRaises(RuntimeError): self.verify()
        (self.stage / (SLUG + '.html')).write_text(original)
        self.receipt['done_ids'] = ['lmnopqrstuv']; self.save()
        with self.assertRaises(RuntimeError): self.verify()
        self.assertEqual(self.calls, [])

    def test_old_item_count_or_mention_is_not_current_list_membership(self):
        for body in ('<p>1편 ' + SLUG + '.html</p>', '<!--<a href="./' + SLUG + '.html"><img src="assets/ig/' + SLUG + '.jpg"></a>-->', '<script>var old="<a href=\'./' + SLUG + '.html\'><img src=\'assets/ig/' + SLUG + '.jpg\'></a>";</script>'):
            with self.subTest(body=body):
                self.routes[self.tech] = (body, 'text/html', 200)
                with self.assertRaises(RuntimeError): self.verify()

    def test_foreign_origin_and_wrong_directory_report_links_do_not_count(self):
        for href in ('https://foreign.invalid/news/' + SLUG + '.html', '/wrong/' + SLUG + '.html'):
            with self.subTest(href=href):
                self.routes[self.tech] = ('<a href="' + href + '"><img src="assets/ig/' + SLUG + '.jpg"></a>', 'text/html', 200)
                with self.assertRaises(RuntimeError): self.verify()

    def test_list_image_must_belong_to_this_exact_report_anchor(self):
        self.routes[self.tech] = ('<a href="./' + SLUG + '.html"><img src="assets/ig/old.jpg"></a><img src="assets/ig/' + SLUG + '.jpg"><a href="./' + DATE + '-daily-brief-ai.html">brief</a>', 'text/html', 200)
        with self.assertRaises(RuntimeError): self.verify()

    def test_list_date_must_match_even_when_current_report_and_image_are_linked(self):
        original = self.routes[self.tech]
        for replacement in ('2026-11-01', '<!--' + DATE + '-->', '<script>"' + DATE + '"</script>'):
            with self.subTest(replacement=replacement):
                self.routes[self.tech] = (original[0].replace('<h1>' + DATE + '</h1>', replacement),
                                          original[1], original[2])
                with self.assertRaisesRegex(RuntimeError, 'missing from the daily list'):
                    self.verify()
        self.routes[self.tech] = (original[0].replace(DATE + '</h1>', '2026. 11. 02.</h1>'),
                                  original[1], original[2])
        self.assertEqual(self.verify()['youtube_reports'], 1)

    def test_public_report_must_embed_same_source_video_and_its_image(self):
        original = self.routes[self.report]
        for body in (original[0].replace(VIDEO, 'lmnopqrstuv'), original[0].replace('<img', '<!--<img').replace('.jpg">', '.jpg">-->')):
            with self.subTest(body=body):
                self.routes[self.report] = (body, 'text/html', 200)
                with self.assertRaises(RuntimeError): self.verify()

    def test_images_must_be_real_reachable_jpeg_resources(self):
        for resource in (self.image, self.thumb):
            original = self.routes[resource]
            for response in ((jpeg(), 'image/jpeg', 404), ('<html>error</html>', 'text/html', 200), (b'\xff\xd8not-an-image\xff\xd9', 'image/jpeg', 200), (jpeg()[:-2], 'image/jpeg', 200)):
                with self.subTest(resource=resource, response=response[1:]):
                    self.routes[resource] = response
                    with self.assertRaises(RuntimeError): self.verify()
            self.routes[resource] = original

    def test_brief_must_be_linked_from_current_list(self):
        self.routes[self.tech] = (self.routes[self.tech][0].replace('<a href="./' + DATE + '-daily-brief-ai.html">모아보기</a>', ''), 'text/html', 200)
        with self.assertRaises(RuntimeError): self.verify()
        self.assertNotIn(self.brief, self.calls)

    def test_brief_thumbnail_must_belong_to_exact_report_card(self):
        self.routes[self.brief] = ('<a href="./' + SLUG + '.html"><img src="./assets/ig/thumb/old.jpg"></a><img src="./assets/ig/thumb/' + SLUG + '.jpg">', 'text/html', 200)
        with self.assertRaises(RuntimeError): self.verify()

    def test_report_date_must_be_in_document_text_not_just_slug_or_script(self):
        original = self.routes[self.report]
        for replacement in ('2026-11-01', '<!--' + DATE + '-->', '<script>"' + DATE + '"</script>'):
            with self.subTest(replacement=replacement):
                self.routes[self.report] = (original[0].replace('<p>' + DATE + '</p>', replacement), original[1], original[2])
                with self.assertRaises(RuntimeError): self.verify()

    def test_brief_date_must_match_even_when_report_link_and_thumbnail_exist(self):
        original = self.routes[self.brief]
        for replacement in ('2026. 11. 01. (일)', '<!--2026. 11. 02.-->', '<script>"2026. 11. 02."</script>'):
            with self.subTest(replacement=replacement):
                self.routes[self.brief] = (original[0].replace('2026. 11. 02. (월)', replacement), original[1], original[2])
                with self.assertRaises(RuntimeError): self.verify()
        self.routes[self.brief] = (original[0].replace('2026. 11. 02. (월)', DATE), original[1], original[2])
        self.assertEqual(self.verify()['youtube_briefs'], 1)

    def test_jpeg_framing_dimension_parser_rejects_zero_or_missing_frame(self):
        self.assertEqual(verification._jpeg_dimensions(jpeg(321, 123)), (321, 123))
        for data in (jpeg(0, 123), b'\xff\xd8\xff\xd9', b'notJPEG', jpeg()[:-1]):
            with self.subTest(data=data):
                with self.assertRaises(RuntimeError): verification._jpeg_dimensions(data)

    def test_date_in_slug_cannot_be_replaced_by_upload_date(self):
        self.receipt['queue'] = {'2026-11-01-uploaded-yesterday': {}}; self.save()
        with self.assertRaises(RuntimeError): self.verify()
        self.assertEqual(self.calls, [])


if __name__ == '__main__': unittest.main()
