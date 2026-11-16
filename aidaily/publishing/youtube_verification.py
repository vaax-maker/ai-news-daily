"""Verify this run's YouTube reports through the public dated lists and images.

This is a delivery check, not a replacement for content-quality review. Expected
slugs, video IDs and hashes come only from the current private staging receipt.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import urllib.parse
import urllib.request

from aidaily import config


class _Page(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.images = []
        self.embeds = []
        self.text = []
        self.schemas = []
        self.heading_numbering = []
        self.card_headings = []
        self.card_texts = []
        self._card_text = None
        self._sections = []
        self._heading = None
        self._in_seq = False
        self._anchor = None
        self._hidden = 0
        self.feed(content)
        self.close()

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        if tag in ('script', 'style'):
            self._hidden += 1
        if self._hidden:
            return
        if tag == 'meta' and values.get('name') == 'youtube-report-schema':
            self.schemas.append(values.get('content', ''))
        if tag == 'meta' and values.get('name') == 'youtube-heading-numbering':
            self.heading_numbering.append(values.get('content', ''))
        if tag == 'section':
            self._sections.append('card' in values.get('class', '').split())
            if self._sections[-1]:
                self._card_text = []
        elif tag == 'h2' and self._sections and self._sections[-1]:
            self._heading = {'number': '', 'title': ''}
        elif tag == 'span' and self._heading is not None and 'seq' in values.get('class', '').split():
            self._in_seq = True
        if tag == 'a':
            self._anchor = {'href': values.get('href', ''), 'images': []}
            self.links.append(self._anchor)
        elif tag == 'img':
            src = values.get('src', '')
            self.images.append(src)
            if self._anchor is not None:
                self._anchor['images'].append(src)
        elif tag == 'iframe':
            self.embeds.append(values.get('src', ''))

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self._hidden = max(0, self._hidden - 1)
        if self._hidden:
            return
        if tag == 'span' and self._in_seq:
            self._in_seq = False
        elif tag == 'h2' and self._heading is not None:
            self.card_headings.append((self._heading['number'].strip(), self._heading['title'].strip()))
            self._heading = None
        elif tag == 'section' and self._sections:
            if self._sections[-1] and self._card_text is not None:
                self.card_texts.append(' '.join(' '.join(self._card_text).split()))
                self._card_text = None
            self._sections.pop()
        if tag == 'a':
            self._anchor = None

    def handle_data(self, data):
        if not self._hidden:
            self.text.append(data)
            if self._card_text is not None:
                self._card_text.append(data)
            if self._heading is not None:
                self._heading['number' if self._in_seq else 'title'] += data


def _story_headings(page):
    """Validate the selected heading convention and return titles for comparison."""
    headings = page.card_headings
    if page.heading_numbering not in ([], ['none']):
        raise RuntimeError('Invalid YouTube heading numbering metadata')
    unnumbered = page.heading_numbering == ['none']
    if (len(headings) < 2 or headings[-1][1] != '용어 사전' or
            any((number != '' if unnumbered else number != f'{index:02d}') or not title or
                (unnumbered and re.match(r'^\d{1,2}(?:[.)．]\s*|\s+)', title)) or
                (index < len(headings) and title == '용어 사전')
                for index, (number, title) in enumerate(headings, 1))):
        raise RuntimeError('Invalid YouTube story-topic headings')
    return headings


def _key(url):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme.lower(), parsed.netloc.lower(),
            posixpath.normpath(urllib.parse.unquote(parsed.path)))


def _same_resource(page_url, reference, expected):
    return bool(reference) and _key(urllib.parse.urljoin(page_url, reference)) == _key(expected)


def _video_ids(page):
    result = set()
    for url in page.embeds:
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname not in {'www.youtube.com', 'youtube.com',
                                    'www.youtube-nocookie.com', 'youtube-nocookie.com'}:
            continue
        match = re.fullmatch(r'/embed/([A-Za-z0-9_-]{11})/?', parsed.path)
        if match:
            result.add(match[1])
    return result


def _has_publication_date(page, date):
    """Check rendered document text, not URLs, comments, or script payloads."""
    year, month, day = date.split('-')
    visible = ' '.join(page.text)
    iso = r'(?<!\d)' + re.escape(date) + r'(?!\d)'
    dotted = (r'(?<!\d)' + year + r'\s*\.\s*0?' + str(int(month)) +
              r'\s*\.\s*0?' + str(int(day)) + r'(?!\d)')
    return bool(re.search(iso, visible) or re.search(dotted, visible))


def _jpeg_dimensions(data):
    """Read JPEG framing/dimensions, rejecting HTML and truncated marker data."""
    if not isinstance(data, bytes) or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise RuntimeError('YouTube image is not a complete JPEG')
    cursor = 2
    dimensions = None
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                   0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while cursor < len(data) - 2:
        if data[cursor] != 0xFF:
            raise RuntimeError('Invalid JPEG marker')
        while cursor < len(data) and data[cursor] == 0xFF:
            cursor += 1
        if cursor >= len(data):
            raise RuntimeError('Truncated JPEG marker')
        marker = data[cursor]
        cursor += 1
        if marker in {0xD8, 0xD9, 0x01} or 0xD0 <= marker <= 0xD7:
            continue
        if cursor + 2 > len(data):
            raise RuntimeError('Truncated JPEG segment')
        length = int.from_bytes(data[cursor:cursor + 2], 'big')
        if length < 2 or cursor + length > len(data) - 2:
            raise RuntimeError('Invalid JPEG segment length')
        if marker in sof_markers:
            if length < 8:
                raise RuntimeError('Missing JPEG dimensions')
            height = int.from_bytes(data[cursor + 3:cursor + 5], 'big')
            width = int.from_bytes(data[cursor + 5:cursor + 7], 'big')
            components = data[cursor + 7]
            if width <= 0 or height <= 0 or components <= 0 or length != 8 + 3 * components:
                raise RuntimeError('Invalid JPEG dimensions')
            dimensions = (width, height)
        if marker == 0xDA:
            break  # Entropy-coded data uses marker escaping; the terminal EOI was checked above.
        cursor += length
    if dimensions is None:
        raise RuntimeError('JPEG dimensions were not found')
    return dimensions


def _get(url, opener, *, image=False):
    try:
        with opener(url, timeout=30) as response:
            if response.status != 200:
                raise RuntimeError('YouTube publication HTTP status is not 200: ' + url)
            final_url = response.geturl() if hasattr(response, 'geturl') else url
            if final_url and _key(final_url) != _key(url):
                raise RuntimeError('YouTube publication redirected to a different resource: ' + url)
            content = response.read()
            content_type = str(response.headers.get('Content-Type', '')).split(';', 1)[0].strip().lower()
    except (OSError, ValueError) as error:
        raise RuntimeError('Cannot read YouTube publication: ' + url) from error
    if image:
        if content_type not in {'image/jpeg', 'image/jpg'}:
            raise RuntimeError('YouTube image has wrong Content-Type: ' + url)
        return _jpeg_dimensions(content)
    if content_type and content_type not in {'text/html', 'application/xhtml+xml'}:
        raise RuntimeError('YouTube page has wrong Content-Type: ' + url)
    try:
        return _Page(content.decode('utf-8'))
    except (UnicodeError, ValueError) as error:
        raise RuntimeError('Cannot parse YouTube publication: ' + url) from error


def _expected(date):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise RuntimeError('Invalid YouTube publication date')
    staging = config.DATA_ROOT / 'youtube_summaries/staging' / date
    try:
        state = json.loads((staging / 'run-status.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise RuntimeError('Current YouTube run receipt is missing or invalid') from error
    if not isinstance(state, dict) or state.get('date') != date:
        raise RuntimeError('YouTube run receipt date differs')
    if (state.get('quality_gate') or {}).get('status') == 'failed':
        # The generator withheld this run from publication; nothing is expected.
        return None
    queue, done, hashes, target_count = (state.get('queue'), state.get('done_ids'),
                                        state.get('report_hashes'), state.get('target_count'))
    if (not isinstance(queue, dict) or not isinstance(done, list) or
            type(target_count) is not int or target_count < 0 or
            any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', x) for x in done)
            or len(set(done)) != len(done)):
        raise RuntimeError('Invalid YouTube run receipt fields')
    if target_count == 0 and not queue and not done:
        return []
    if not queue or not done or not isinstance(hashes, dict) or len(queue) != len(done) or target_count < len(queue):
        raise RuntimeError('YouTube run has incomplete expected reports')
    expected = []
    for slug in queue:
        if not isinstance(slug, str) or not re.fullmatch(re.escape(date) + r'-[A-Za-z0-9_-]+', slug):
            raise RuntimeError('YouTube report slug does not match the publication date')
        expected_hash = hashes.get(slug)
        if not isinstance(expected_hash, str) or not re.fullmatch(r'[a-f0-9]{64}', expected_hash):
            raise RuntimeError('YouTube staged report hash is missing')
        try:
            content = (staging / (slug + '.html')).read_bytes()
        except OSError as error:
            raise RuntimeError('Expected YouTube staged report is missing: ' + slug) from error
        if hashlib.sha256(content).hexdigest() != expected_hash:
            raise RuntimeError('YouTube staged report differs from this run receipt: ' + slug)
        try:
            page = _Page(content.decode('utf-8'))
            ids = _video_ids(page)
        except UnicodeError as error:
            raise RuntimeError('Invalid YouTube staged report encoding') from error
        if len(ids) != 1:
            raise RuntimeError('YouTube staged report has no unique source video: ' + slug)
        story_content = (page.heading_numbering, _story_headings(page), page.card_texts) if 'story_topics_v2' in page.schemas else None
        if story_content is not None and len(page.card_texts) != len(page.card_headings):
            raise RuntimeError('Invalid YouTube story-topic cards')
        expected.append((slug, next(iter(ids)), story_content))
    if {video for _, video, _ in expected} != set(done) or len({video for _, video, _ in expected}) != len(expected):
        raise RuntimeError('YouTube staged source videos differ from this run done_ids')
    return expected


def verify_youtube_publication(date, *, opener=None):
    """Fail unless every output from this exact run is reachable from today's list."""
    expected = _expected(date)
    if not expected:
        result = {'youtube_reports': 0, 'youtube_images': 0, 'youtube_thumbnails': 0,
                  'youtube_briefs': 0, 'youtube_evidence': []}
        if expected is None:
            result['youtube_status'] = 'withheld_quality_gate'
        return result
    opener = opener or urllib.request.urlopen
    base = urllib.parse.urljoin(config.TECH_DAILY_URL, './')
    listing_urls = [urllib.parse.urljoin(base, urllib.parse.quote(name) + '?date=' + date)
                    for name in ('기술.html', '경제.html')]
    listings = {url: _get(url, opener) for url in listing_urls}
    brief_urls = [urllib.parse.urljoin(base, f'{date}-daily-brief-{kind}.html')
                  for kind in ('ai', 'econ')]
    linked_briefs = {url for url in brief_urls if any(
        _same_resource(list_url, link['href'], url)
        for list_url, page in listings.items() for link in page.links)}
    briefs = {url: _get(url, opener) for url in linked_briefs}
    evidence = []
    used_briefs = set()
    for slug, video_id, story_content in expected:
        report_url = urllib.parse.urljoin(base, slug + '.html')
        image_url = urllib.parse.urljoin(base, f'assets/ig/{slug}.jpg')
        thumb_url = urllib.parse.urljoin(base, f'assets/ig/thumb/{slug}.jpg')
        listed = [url for url, page in listings.items() if _has_publication_date(page, date) and any(
            _same_resource(url, link['href'], report_url) and any(
                _same_resource(url, image, image_url) for image in link['images'])
            for link in page.links)]
        if not listed:
            raise RuntimeError('Current YouTube report/image is missing from the daily list: ' + slug)
        report = _get(report_url, opener)
        if story_content is not None:
            if ('story_topics_v2' not in report.schemas or
                    (report.heading_numbering, _story_headings(report), report.card_texts) != story_content):
                raise RuntimeError('Published YouTube story-topic content differs from staged report: ' + slug)
        if _video_ids(report) != {video_id}:
            raise RuntimeError('Published YouTube report has a different source video: ' + slug)
        if not _has_publication_date(report, date):
            raise RuntimeError('Published YouTube report has a different publication date: ' + slug)
        if not any(_same_resource(report_url, image, image_url) for image in report.images):
            raise RuntimeError('Published YouTube report is missing its required image: ' + slug)
        width, height = _get(image_url, opener, image=True)
        matching_briefs = [url for url, page in briefs.items() if _has_publication_date(page, date) and any(
            _same_resource(url, link['href'], report_url) and any(
                _same_resource(url, image, thumb_url) for image in link['images'])
            for link in page.links)]
        if not matching_briefs:
            raise RuntimeError('Current YouTube report/thumbnail is missing from the linked daily brief: ' + slug)
        thumb_width, thumb_height = _get(thumb_url, opener, image=True)
        used_briefs.update(matching_briefs)
        evidence.append({'slug': slug, 'video_id': video_id, 'report_url': report_url,
                         'image_url': image_url, 'image_dimensions': [width, height],
                         'thumbnail_url': thumb_url, 'thumbnail_dimensions': [thumb_width, thumb_height],
                         'listing_urls': listed, 'brief_urls': matching_briefs})
    return {'youtube_reports': len(expected), 'youtube_images': len(evidence),
            'youtube_thumbnails': len(evidence), 'youtube_briefs': len(used_briefs),
            'youtube_evidence': evidence}
