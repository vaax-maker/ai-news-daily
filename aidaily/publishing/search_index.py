#!/usr/bin/env python3
"""Build the unified search index for all published AI Daily content.

원칙3(P4): 여러 발행 채널을 넘나드는 통합 검색. 각 발행물은 서로 다른 저장 포맷을
쓰므로(AI News=날짜별 JSON 배열, Customer Stories=manifest.json,
YouTube Summaries/시황=index.html 카드)
소스별로 읽어 공통 스키마로 합친다.

카테고리:
  - AI 뉴스     : docs/archive/index.json (날짜별 스토리 묶음)
  - 고객 사용기 : public compatibility path의 날짜별 manifest
  - 브리프      : ~/Sites/ai-infographic의 **AI·기술 일단위 편성페이지**
                  ({date}-daily-brief-ai.html)만. **날짜당 1엔트리.**
  - 시황        : ~/Sites/ai-infographic의 **시황·경제 일단위 편성페이지**
                  ({date}-daily-brief-econ.html)만(브리프와 완전 분리된 별도 카테고리).
                  **날짜당 1엔트리.**
  - 개별리포트  : ~/Sites/ai-infographic index.html의 **개별 유튜브 영상 리포트** 카드
                  (data-cat="AI 뉴스", `-daily-brief-`/gpters/market-briefing 슬러그는 제외 —
                   이들은 개별 영상이 아니므로 뺀다). channel(출처 채널) 포함.

출력: docs/search-index.json — [{date, pub, title, summary, url, channel?}, ...]
  pub: "뉴스" | "고객사용기" | "브리프" | "시황" | "개별리포트"

★비파괴: 이 스크립트는 새 파일(search-index.json)만 만든다. 기존 발행 페이지는 건드리지 않는다.

사용:
  python3 build_search_index.py [--webroot ~/Sites/ai-infographic] [--out search-index.json]
"""
import argparse
import html
import json
import os
import re
import sys

from aidaily import config
from aidaily.customer_stories.pipeline import public_source_label, public_story_text
from aidaily.publishing.highlights import select_highlights
from aidaily.publishing.engagement import stable_uid

# 공개 URL 베이스
NEWS_ARCHIVE_URL = f"{config.PUBLIC_SITE_URL}archive.html"
CUSTOMER_STORIES_BASE_URL = (
    f"{config.PUBLIC_SITE_URL}v2/{config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR}/"
)
BRIEF_BASE_URL = "https://wootom.github.io/news/"

DEFAULT_WEBROOT = str(config.PUBLISHING_REPOSITORY)

# --- index.html 카드 추출 정규식 — backfill_calendar_briefs.py의 read_cards와 동일 ---
CARD_OPEN_RE = re.compile(
    r'<a class="card" href="\./(?P<slug>[^"]+)\.html" data-cat="(?P<dcat>[^"]*)"')
BADGE_RE = re.compile(r'<span class="badge"[^>]*>(.*?)</span>', re.S)
TITLE_RE = re.compile(r'<div class="card-title">(.*?)</div>', re.S)
SUMMARY_RE = re.compile(r'<div class="card-summary">(.*?)</div>', re.S)
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-")
# 일단위 편성페이지(daily-brief) 슬러그: {date}-daily-brief-{cat}
DAILY_BRIEF_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-daily-brief-(ai|econ)$")

# 개별 영상 리포트가 아닌 슬러그(개별리포트 대상 아님) — backfill_calendar_briefs.py와 동일 기준
SKIP_PREFIX = ("gpters", "market-briefing")
# 개별리포트/편성페이지 카테고리로 취급할 data-cat. '커뮤니티'는 영상 리포트가 아니라 제외.
CAT_OF_DATACAT = {"AI 뉴스": "ai", "시황브리핑": "econ"}
# 일단위 편성페이지의 cat(ai/econ)별 pub 라벨·제목 — 브리프(AI·기술)와 시황(경제)은 완전 분리된 카테고리.
DAILY_BRIEF_PUB = {"ai": "브리프", "econ": "시황"}
DAILY_BRIEF_TITLE = {"ai": "AI·기술 브리프", "econ": "시황 브리프"}


def _unescape(s):
    return (s or "").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
                    .replace("&quot;", '"').replace("&#x27;", "'").replace("&#39;", "'").strip()


def _summary_bullets(text, limit=3):
    """Turn legacy paragraph summaries into compact display bullets.

    New AI News records already carry editor-produced ``body_bullets``.  This
    fallback keeps historical news and Customer Stories readable without an
    additional LLM/API call.
    """
    clean = _unescape(text)
    if not clean:
        return []
    parts = re.split(r"(?:\r?\n+|(?<=[.!?])\s+)", clean)
    bullets = []
    for part in parts:
        part = re.sub(r"^\s*[-•·▪]\s*", "", part).strip()
        if part:
            bullets.append(part)
        if len(bullets) >= limit:
            break
    return bullets or [clean]


def _domain(url):
    m = re.search(r"https?://([^/]+)", url or "")
    return m.group(1).replace("www.", "") if m else ""


# 출처 도메인 → 알아보기 쉬운 소스 이름(기사 출처 명시용). 신규 4개 소스 + 네이버.
# 매핑에 없으면 도메인 그대로. (2026-08-26 우장훈: "기사는 출처를 명시해야" — MIT/CB 등이
# technologyreview.com 도메인으로만 보여 인식 안 됨 → 소스명으로 표기)
_SOURCE_NAME = {
    "technologyreview.com": "MIT Tech Review",
    "cbinsights.com": "CB Insights",
    "aibase.com": "aibase",
    "aitimes.com": "AI타임스",
    "n.news.naver.com": "네이버뉴스",
    "news.naver.com": "네이버뉴스",
}


def _source_name(url):
    """기사 url → 출처 표기명(신규 소스는 브랜드명, 그 외는 도메인)."""
    return _SOURCE_NAME.get(_domain(url), _domain(url))


def _story_channel(story):
    """Show source domains while retaining aiofmodu's curator attribution."""
    curator = str(story.get("source") or "").strip()
    publisher_domain = _domain(story.get("url", ""))
    if curator.casefold() == "aiofmodu":
        if publisher_domain and publisher_domain != "aiofmodu.com":
            return f"aiofmodu.com · {publisher_domain}"
        return "aiofmodu.com"
    return publisher_domain or curator


def load_news(docs_root):
    """AI 뉴스: docs/archive/index.json → 그날의 개별 기사(stories[]) 각각 1건.

    2026-08-24: 종합 1건 → **개별 기사 N건화**. 페이지가 'AI뉴스 5건(+신규 소스)'을 개별 카드로
    노출하도록. url은 기사 원문, channel은 출처 도메인. stories가 없으면 종합 1건으로 폴백."""
    path = os.path.join(docs_root, "archive", "index.json")
    if not os.path.exists(path):
        print(f"  [경고] AI 뉴스 인덱스 없음: {path}", file=sys.stderr)
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = []
    for d in data:
        date = d.get("date", "")
        stories = d.get("stories") or []
        if not stories:                       # 스토리 없으면 종합 1건(폴백)
            summary = d.get("summary", "")
            items.append({"date": date, "pub": "뉴스", "title": d.get("title", ""),
                          "summary": summary, "summary_bullets": _summary_bullets(summary),
                          "url": NEWS_ARCHIVE_URL})
            continue
        for s in stories:
            summary = s.get("body", "") or ""
            bullets = [str(x).strip() for x in (s.get("body_bullets") or []) if str(x).strip()]
            items.append({
                "date": date, "pub": "뉴스", "n": s.get("n", ""),
                "title": s.get("headline", "") or d.get("title", ""),
                "summary": summary,
                "summary_bullets": bullets[:3] or _summary_bullets(summary),
                "why": s.get("takeaway", "") or "",
                "url": s.get("url") or NEWS_ARCHIVE_URL,
                "channel": _story_channel(s),
            })
    return items


def _customer_story_v2_rows(gen, date, url):
    """Index complete public newsroom articles without private verification evidence.

    Publication identity is assigned by the runtime. Story ID is a stable
    fallback for fixtures/migrations; display order must never become identity.
    """
    from aidaily.customer_stories.story_render import safe_url
    from urllib.parse import urlencode
    stories = gen.get("items")
    if not isinstance(stories, list) or len(stories) > 2:
        raise ValueError("Customer story v2 must contain zero to two articles")
    rows, identities, indexes = [], set(), set()
    for story in stories:
        if not isinstance(story, dict):
            raise ValueError("Invalid customer story article")
        identity = story.get("story_id")
        if not isinstance(identity, str) or not identity.strip() or identity in identities:
            raise ValueError("Customer story v2 needs unique stable story IDs")
        identities.add(identity)
        index = story.get("publication_index", identity)
        if "publication_index" in story and (type(index) is not int or index < 0):
            raise ValueError("Customer story publication_index must be a nonnegative integer")
        if index in indexes:
            raise ValueError("Duplicate customer story publication index")
        indexes.add(index)
        title = public_story_text(story.get("issue") or "").strip()
        if not title:
            raise ValueError("Customer story v2 needs an article title")
        summary = public_story_text(story.get("dek") or "").strip()
        voices = story.get("voices") or []
        if not summary:
            # Keep the complete supplied observation: sentence slicing can drop
            # a qualification or negation in the following sentence.
            summary = next((public_story_text(voice.get("text") or "").strip()
                            for voice in voices if voice.get("text")), "")
        labels = list(dict.fromkeys(public_source_label(voice.get("source") or "")
                                    for voice in voices if voice.get("source")))
        row = {"date": date, "pub": "고객사용기", "customer_story_index": index,
               "story_id": identity, "title": title, "summary": summary,
               "summary_bullets": [summary] if summary else [],
               "why": public_story_text(story.get("commentary") or ""),
               "url": config.TECH_DAILY_URL + "?" + urlencode({"date": date, "item": f"customer_story:{date}:{index}"}),
               "channel": " · ".join(labels)}
        # Whitelist published prose; source excerpts, evidence IDs and internal
        # review metadata never enter the public store.
        content = {"commentary": public_story_text(story.get("commentary") or "")}
        for field in ("background", "voices", "timeline", "related_links"):
            content[field] = []
            for source_row in story.get(field) or []:
                clean = {key: public_story_text(str(source_row[key]))
                         for key in ("text", "label", "date", "stage") if source_row.get(key)}
                if source_row.get("source"):
                    clean["source"] = public_source_label(str(source_row["source"]))
                if safe_url(source_row.get("url")):
                    clean["url"] = source_row["url"]
                content[field].append(clean)
        row["story_content"] = content
        if story.get("article_kind") in ("experience", "explainer"):
            row["article_kind"] = story["article_kind"]
        rows.append(row)
    return rows


def load_customer_stories(docs_root):
    """고객 사용기 manifest와 날짜별 원본에서 개별 항목을 방출한다.

    2026-08-24: 종합 1건 → **개별 N건화**. manifest.json은 날짜·제목·정서·건수만 담으므로,
    각 날짜의 원본 데이터(data/customer_stories/{date}.json → gen.items[])를 읽어 피드백 항목
    (issue/category/sentiment/content/commentary/sources/refs)을 하나씩 카드로 만든다.
    개별 파일이 없거나 items가 비면 그 날짜는 manifest 종합 1건으로 **폴백**한다.
    """
    path = os.path.join(docs_root, "v2", config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR,
                        "manifest.json")
    if not os.path.exists(path):
        print(f"  [경고] 고객 사용기 매니페스트 없음: {path}", file=sys.stderr)
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data_dir = str(config.DATA_ROOT / "customer_stories")
    items = []
    for d in data:
        date = d.get("date", "")
        gen_items = []
        gen = {}
        day_path = os.path.join(data_dir, f"{date}.json")
        if os.path.exists(day_path):
            try:
                with open(day_path, encoding="utf-8") as gf:
                    gen = json.load(gf).get("gen") or {}
                    gen_items = gen.get("items") or []
            except Exception as e:
                print(f"  [경고] 고객 사용기 원본 파싱 실패({date}): {e}", file=sys.stderr)
                gen_items = []
        url = f"{CUSTOMER_STORIES_BASE_URL}{date}.html"
        if gen.get("schema_version") == 2:
            items.extend(_customer_story_v2_rows(gen, date, url))
            continue
        if gen_items:                              # 개별 항목 N건
            for i, it in enumerate(gen_items):
                sources = it.get("sources") or []
                summary = public_story_text(it.get("content", "") or "")
                items.append({
                    "date": date,
                    "pub": "고객사용기",
                    "customer_story_index": it.get("publication_index", i),  # 필터 후에도 기존 항목 ID 보존
                    "title": public_story_text(it.get("issue", "") or ""),
                    "summary": summary,
                    "summary_bullets": _summary_bullets(summary),
                    "why": public_story_text(it.get("commentary", "") or ""),
                    # 원문(Reddit/HN/긱뉴스) 직링크; 없으면(오픈채팅 등) 그날 아카이브 폴백.
                    "url": it.get("primary_url") or url,
                    "channel": " · ".join(public_source_label(s) for s in sources if s),
                })
        else:                                      # 폴백: manifest 종합 1건
            mood = public_story_text(d.get("mood", ""))
            n = d.get("n", "")
            summary = f"피드백 {n}건 · 정서 {mood}" if (n or mood) else ""
            items.append({
                "date": date,
                "pub": "고객사용기",
                "title": public_story_text(d.get("title", "")),
                "summary": public_story_text(summary),
                "summary_bullets": _summary_bullets(summary),
                "url": url,
            })
    return items


def _read_cards(webroot):
    """index.html에서 카드 블록을 모두 회수한다(경계 처리는 backfill_calendar_briefs.py와 동일).

    반환: [(slug, dcat, block), ...] — 뒤에서 daily-brief/개별영상으로 분기한다.
    """
    idx_path = os.path.join(webroot, "index.html")
    if not os.path.exists(idx_path):
        print(f"  [경고] index.html 없음: {idx_path}", file=sys.stderr)
        return []
    idx = open(idx_path, encoding="utf-8").read()
    opens = list(CARD_OPEN_RE.finditer(idx))
    cards = []
    for i, m in enumerate(opens):
        # 카드 블록 = 이 앵커부터 다음 앵커(또는 </a>) 앞까지. 경계를 넘지 않는다.
        stop = opens[i + 1].start() if i + 1 < len(opens) else len(idx)
        end = idx.find("</a>", m.end())
        block = idx[m.end():min(stop, end if end != -1 else stop)]
        cards.append((m.group("slug"), m.group("dcat"), block))
    return cards


def load_daily_briefs(webroot):
    """브리프/시황: 일단위 편성페이지({date}-daily-brief-{ai,econ}.html) → 날짜·카테고리당 1건.

    ai→"브리프"(AI·기술), econ→"시황"(경제·증시)으로 **완전히 분리된 카테고리**다(사용자 확정사항:
    시황을 브리프에서 분리). 제목은 카드 원제목("N편 — 하루 리포트 모아보기") 대신
    "AI·기술 브리프"/"시황 브리프" + 날짜로 명확히 라벨링한다.
    """
    items, seen = [], set()
    for slug, dcat, block in _read_cards(webroot):
        m = DAILY_BRIEF_RE.match(slug)
        if not m or CAT_OF_DATACAT.get(dcat) is None:
            continue
        date, cat = m.group(1), m.group(2)
        key = (date, cat)
        if key in seen:  # 날짜·카테고리당 1개만 — 중복 카드가 있어도 유일화
            continue
        seen.add(key)
        s = SUMMARY_RE.search(block)
        items.append({
            "date": date,
            "pub": DAILY_BRIEF_PUB[cat],
            "title": f"{DAILY_BRIEF_TITLE[cat]} · {date}",
            "summary": _unescape(s.group(1)) if s else "",
            "url": f"{BRIEF_BASE_URL}{slug}.html",
        })
    return items


# New reports use the canonical marker; old published reports remain readable.
_MD_RE = re.compile(r"(?:YOUTUBE SUMMARIES|MORNING DIGEST) · \d{4}-\d{2}-\d{2} · ([^<]+)")
_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.S)
_REPORT_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-.+\.html$")
_CAT_RE = re.compile(r'class="cat-(econ|tech)"')   # 리포트 body 카테고리(경제/기술)


def _scan_report_files(webroot):
    """webroot의 개별 영상 리포트 파일을 직접 스캔 → (slug, date, title, channel, cat).
    YouTube summary marker로 리포트만 선별(비리포트/슬라이드/index 등 제외).
    카테고리는 body의 class="cat-econ"/"cat-tech"에서 뽑는다(기본=tech)."""
    if not os.path.isdir(webroot):
        return
    for fn in sorted(os.listdir(webroot)):
        m = _REPORT_FILE_RE.match(fn)
        if not m:
            continue
        slug = fn[:-5]
        if slug.startswith(SKIP_PREFIX) or DAILY_BRIEF_RE.match(slug):
            continue
        try:
            h = open(os.path.join(webroot, fn), encoding="utf-8").read()
        except Exception:
            continue
        md = _MD_RE.search(h)
        if not md:                 # YouTube summary marker가 없으면 개별 영상 리포트 아님
            continue
        tt = _TITLE_TAG_RE.search(h)
        title = _unescape(tt.group(1).strip()) if tt else slug
        cm = _CAT_RE.search(h)
        cat = cm.group(1) if cm else "tech"
        yield slug, m.group(1), title, _unescape(md.group(1).strip()), cat


def load_individual_reports(webroot):
    """개별리포트: 개별 유튜브 영상 리포트 → slug당 1건.

    2026-08-21: 소스를 index.html 카드 + 실제 리포트 파일 스캔의 **union**으로 확장.
    개별 YouTube 리포트 카드가 index.html에
    안 들어가므로, 카드만 읽으면 07-25 이후 리포트가 전부 누락된다. 파일을 직접 스캔해 갭을 메운다.
    카드가 있는 슬러그는 카드 버전(요약 포함)을 우선하고, 카드에 없는 슬러그만 파일에서 채운다.
    """
    items, seen = [], set()
    # 1) index.html 카드(옛 리포트 — 파일이 정리돼도 유지, 요약 포함)
    for slug, dcat, block in _read_cards(webroot):
        d = DATE_RE.match(slug)
        if (CAT_OF_DATACAT.get(dcat) is None or not d
                or slug.startswith(SKIP_PREFIX) or DAILY_BRIEF_RE.match(slug)):
            continue
        if slug in seen:  # slug 기준 유일화
            continue
        seen.add(slug)
        b, t, s = BADGE_RE.search(block), TITLE_RE.search(block), SUMMARY_RE.search(block)
        items.append({
            "date": d.group(1),
            "pub": "개별리포트",
            "cat": "econ" if CAT_OF_DATACAT.get(dcat) == "econ" else "tech",
            "title": _unescape(t.group(1)) if t else slug,
            "summary": _unescape(s.group(1)) if s else "",
            "url": f"{BRIEF_BASE_URL}{slug}.html",
            "channel": _unescape(b.group(1)) if b else "",
        })
    # 2) 실제 리포트 파일 스캔(카드에 없는 슬러그만) — 07-25 전환 이후 갭 보완
    for slug, date, title, channel, cat in _scan_report_files(webroot):
        if slug in seen:
            continue
        seen.add(slug)
        # Current report pages carry the source-grounded overview in section 1,
        # rather than legacy index cards. Preserve its literal evidence lines.
        try:
            with open(os.path.join(webroot, slug + '.html'), encoding='utf-8') as report:
                page = report.read()
            section = re.search(r'<section\b[^>]*\bid="s1"[^>]*>(.*?)</section>', page, re.S)
            clean = lambda text: re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', text))).strip()
            bullets = [clean(text) for text in re.findall(r'<li\b[^>]*>(.*?)</li>', section.group(1), re.S)] if section else []
            # The first section is now a real subtopic, not the whole-video
            # overview. Reuse the validated cross-topic compatibility facts.
            if 'name="youtube-report-schema" content="story_topics_v2"' in page:
                stored = re.search(r'<meta\s+name="youtube-summary-bullets"\s+content="([^"]*)"', page)
                if stored:
                    try:
                        supplied = json.loads(html.unescape(stored.group(1)))
                        if isinstance(supplied, list) and all(isinstance(value, str) for value in supplied):
                            bullets = supplied[:4]
                    except ValueError:
                        pass
            lead = re.search(r'<p\b[^>]*class="lead"[^>]*>(.*?)</p>', page, re.S)
            summary = ' '.join(bullets[:5]) or (clean(lead.group(1)) if lead else '')
        except OSError:
            bullets, summary = [], ''
        items.append({
            "date": date,
            "pub": "개별리포트",
            "cat": cat,
            "title": title,
            "summary": summary,
            "summary_bullets": bullets[:5],
            "url": f"{BRIEF_BASE_URL}{slug}.html",
            "channel": channel,
        })
    # Keep the original public title across translation/headline rewriting.
    # Legacy index cards can coexist with current report files.
    for item in items:
        slug = item['url'].rsplit('/', 1)[-1]
        try:
            with open(os.path.join(webroot, slug), encoding='utf-8') as report:
                page = report.read()
        except OSError:
            continue
        source = re.search(r'<meta\s+name="youtube-source-title"\s+content="([^"]*)"', page)
        if source:
            item['source_title'] = html.unescape(source.group(1))
    return items


_BRIEF_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-daily-brief-(ai|econ)\.html$")
_BTITLE_RE = re.compile(r'class="b-title"[^>]*>(.*?)</', re.S)


def load_briefs_from_files(webroot):
    """브리프(기술)/시황(경제) 집계 = 실제 편성페이지 파일을 진실원천으로 스캔.
    2026-08-21: 리포트 그룹핑 재구성 방식은 (a)실제 브리프 파일이 없는 날에도 URL을 만들어 404를
    냈고 (b)실제 존재하는 브리프 일부를 누락했다. 이제 origin의 {date}-daily-brief-{ai|econ}.html
    파일만 항목으로 만든다 → 죽은 링크·누락 없음. summary는 그 브리프의 b-title(영상 제목)들을
    이어 개별 영상 제목으로도 검색되게 한다. 리다이렉트 페이지는 제외."""
    out = []
    if not os.path.isdir(webroot):
        return out
    for fn in sorted(os.listdir(webroot), reverse=True):
        m = _BRIEF_FILE_RE.match(fn)
        if not m:
            continue
        try:
            h = open(os.path.join(webroot, fn), encoding="utf-8").read()
        except Exception:
            continue
        if "이전되었습니다" in h:            # 리다이렉트 페이지면 제외(실브리프만)
            continue
        econ = (m.group(2) == "econ")
        titles = [_unescape(re.sub(r"<[^>]+>", "", t)) for t in _BTITLE_RE.findall(h)]
        titles = [t for t in titles if t]
        out.append({
            "date": m.group(1),
            "pub": "시황" if econ else "브리프",
            "cat": "econ" if econ else "tech",
            "title": f"{'시황 브리프' if econ else 'AI·기술 브리프'} · {m.group(1)}",
            "summary": (" · ".join(titles))[:500],
            "url": f"{BRIEF_BASE_URL}{fn}",
        })
    return out


# --- 통합 스키마 보강(additive·비파괴) — 2026-08-24 "오늘의 AI 소식" 통합 ---
# 기존 필드(date, pub, title, summary, url, cat?, channel?)는 그대로 두고, 목표 통합 스키마
# 필드(id, kind, cat, source, edition)를 추가만 한다. search.html은 pub/cat을 계속 읽으므로 무해.
#   kind: ai_news | customer_story | youtube_summary | market_summary
#   cat : tech | econ                (없으면 pub 기준 채움)
#   source: 신 용어 피드 라벨(AI뉴스/고객사용기/오늘 유튜브/시황)  ← 제품 갈래 표기
#   edition: 아침/저녁 (시황 분리 전이라 현재 None)
_PUB_TO_KIND = {"뉴스": "ai_news", "고객사용기": "customer_story",
                "브리프": "youtube_summary", "시황": "market_summary",
                "개별리포트": "youtube_summary"}
_PUB_TO_CAT = {"뉴스": "tech", "고객사용기": "tech", "브리프": "tech", "시황": "econ"}
_PUB_TO_SOURCE = {"뉴스": "AI뉴스", "고객사용기": "고객사용기", "브리프": "오늘 유튜브",
                  "시황": "시황", "개별리포트": "오늘 유튜브"}


def _slug_from_url(url):
    base = (url or "").rstrip("/").split("/")[-1]
    return base[:-5] if base.endswith(".html") else base


def enrich_unified(items):
    """각 레코드에 통합 스키마 필드(id·kind·cat·source·edition)를 additive로 채운다.
    기존 필드는 절대 덮지 않는다(cat은 없을 때만 채움)."""
    for it in items:
        pub = it.get("pub", "")
        if not it.get("cat"):
            it["cat"] = _PUB_TO_CAT.get(pub, "tech")
        it["kind"] = _PUB_TO_KIND.get(pub, "youtube_summary")
        it["source"] = _PUB_TO_SOURCE.get(pub, pub)
        it.setdefault("edition", None)              # 아침/저녁 분리 전 → None
        it["highlights"] = select_highlights(it.get("summary", ""), it.get("title", ""))
        slug = _slug_from_url(it.get("url", ""))
        if pub == "뉴스":                            # 개별 기사 → date:n 으로 유일
            n = it.get("n")
            it["id"] = f"ai_news:{it.get('date', '')}" + (f":{n}" if n else "")
        elif pub == "고객사용기":                    # 날짜당 개별 항목 N건 → date:index 로 유일
            story_index = it.get("customer_story_index")
            it["id"] = f"customer_story:{it.get('date', '')}" + (
                f":{story_index}" if story_index is not None else ""
            )
        else:
            it["id"] = f"{_PUB_TO_KIND.get(pub, 'youtube_summary')}:{slug or it.get('date', '')}"
    # id 유일성 보장 — 같은 날 중복 뉴스 등 충돌 시 -2, -3 접미(결정적).
    seen = {}
    for it in items:
        base = it["id"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            it["id"] = f"{base}-{seen[base]}"
        it['uid'] = stable_uid(it)
    return items


def build(docs_root: str, webroot: str, output: str) -> list[dict]:
    news = load_news(docs_root)
    customer_stories = load_customer_stories(docs_root)
    reports = load_individual_reports(webroot)
    daily_briefs_all = load_briefs_from_files(webroot)

    def dedupe(items):
        result, seen = [], set()
        for item in items:
            key = (item["pub"], item["url"])
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    daily_briefs_all = dedupe(daily_briefs_all)
    reports = dedupe(reports)
    combined = news + customer_stories + daily_briefs_all + reports
    combined.sort(key=lambda item: item.get("date", ""), reverse=True)
    enrich_unified(combined)
    with open(output, "w", encoding="utf-8") as target:
        json.dump(combined, target, ensure_ascii=False, indent=2)
    return combined


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--webroot", default=DEFAULT_WEBROOT,
                     help="브리프 index.html이 있는 웹루트 (기본: ~/Sites/ai-infographic)")
    ap.add_argument("--docs-root", default=str(config.DOCS_ROOT))
    ap.add_argument("--out", default=str(config.DOCS_ROOT / "search-index.json"),
                     help="출력 경로 (기본: docs/search-index.json)")
    a = ap.parse_args()

    combined = build(
        docs_root=os.path.expanduser(a.docs_root),
        webroot=os.path.expanduser(a.webroot),
        output=os.path.expanduser(a.out),
    )
    briefs = [x for x in combined if x["pub"] == "브리프"]
    econ = [x for x in combined if x["pub"] == "시황"]
    news = [x for x in combined if x["pub"] == "뉴스"]
    customer_stories = [x for x in combined if x["pub"] == "고객사용기"]
    reports = [x for x in combined if x["pub"] == "개별리포트"]

    with_id = sum(1 for x in combined if x.get("id"))
    with_cat = sum(1 for x in combined if x.get("cat"))
    print(f"[완료] {a.out}")
    print(f"  뉴스     : {len(news)}건")
    print(f"  고객사용기: {len(customer_stories)}건")
    print(f"  브리프   : {len(briefs)}건")
    print(f"  시황     : {len(econ)}건")
    print(f"  개별리포트: {len(reports)}건")
    print(f"  합계     : {len(combined)}건  (통합필드: id {with_id}/{len(combined)} · cat {with_cat}/{len(combined)})")


if __name__ == "__main__":
    main()
