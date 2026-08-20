#!/usr/bin/env python3
"""build_search_index.py — 5개 카테고리(뉴스·보이스·브리프·시황·개별리포트)를 단일 검색 인덱스로 통합.

원칙3(P4): 여러 발행 채널을 넘나드는 통합 검색. 각 발행물은 서로 다른 저장 포맷을
쓰므로(뉴스=날짜별 JSON 배열, 보이스=manifest.json, 브리프/시황/개별리포트=index.html 카드)
소스별로 읽어 공통 스키마로 합친다.

카테고리:
  - AI 뉴스     : docs/archive/index.json (날짜별 스토리 묶음)
  - AI 보이스   : docs/v2/uservoice/manifest.json (날짜별 요약)
  - 브리프      : ~/Sites/ai-infographic의 **AI·기술 일단위 편성페이지**
                  ({date}-daily-brief-ai.html)만. **날짜당 1엔트리.**
  - 시황        : ~/Sites/ai-infographic의 **시황·경제 일단위 편성페이지**
                  ({date}-daily-brief-econ.html)만(브리프와 완전 분리된 별도 카테고리).
                  **날짜당 1엔트리.**
  - 개별리포트  : ~/Sites/ai-infographic index.html의 **개별 유튜브 영상 리포트** 카드
                  (data-cat="AI 뉴스", `-daily-brief-`/gpters/market-briefing 슬러그는 제외 —
                   이들은 개별 영상이 아니므로 뺀다). channel(출처 채널) 포함.

출력: docs/search-index.json — [{date, pub, title, summary, url, channel?}, ...]
  pub: "뉴스" | "보이스" | "브리프" | "시황" | "개별리포트"

★비파괴: 이 스크립트는 새 파일(search-index.json)만 만든다. 기존 발행 페이지는 건드리지 않는다.

사용:
  python3 build_search_index.py [--webroot ~/Sites/ai-infographic] [--out search-index.json]
"""
import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# 공개 URL 베이스
NEWS_ARCHIVE_URL = "https://vaax-maker.github.io/ai-news-daily/archive.html"
UVOICE_BASE_URL = "https://vaax-maker.github.io/ai-news-daily/v2/uservoice/"
BRIEF_BASE_URL = "https://wootom.github.io/news/"

DEFAULT_WEBROOT = os.path.expanduser("~/Sites/ai-infographic")

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


def load_news(beacon_docs):
    """AI 뉴스: docs/archive/index.json → 날짜별 1건(그날의 종합 타이틀+요약)."""
    path = os.path.join(beacon_docs, "archive", "index.json")
    if not os.path.exists(path):
        print(f"  [경고] AI 뉴스 인덱스 없음: {path}", file=sys.stderr)
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = []
    for d in data:
        items.append({
            "date": d.get("date", ""),
            "pub": "뉴스",
            "title": d.get("title", ""),
            "summary": d.get("summary", ""),
            "url": NEWS_ARCHIVE_URL,
        })
    return items


def load_uservoice(beacon_docs):
    """AI 보이스: docs/v2/uservoice/manifest.json → 날짜별 1건."""
    path = os.path.join(beacon_docs, "v2", "uservoice", "manifest.json")
    if not os.path.exists(path):
        print(f"  [경고] AI 보이스 매니페스트 없음: {path}", file=sys.stderr)
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = []
    for d in data:
        date = d.get("date", "")
        mood = d.get("mood", "")
        n = d.get("n", "")
        summary = f"피드백 {n}건 · 정서 {mood}" if (n or mood) else ""
        items.append({
            "date": date,
            "pub": "보이스",
            "title": d.get("title", ""),
            "summary": summary,
            "url": f"{UVOICE_BASE_URL}{date}.html",
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


# 개별 영상 리포트 파일 판별/추출 — 'MORNING DIGEST · 날짜 · 채널' 마커를 가진 리포트만.
_MD_RE = re.compile(r"MORNING DIGEST · \d{4}-\d{2}-\d{2} · ([^<]+)")
_TITLE_TAG_RE = re.compile(r"<title>(.*?)</title>", re.S)
_REPORT_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-.+\.html$")
_CAT_RE = re.compile(r'class="cat-(econ|tech)"')   # 리포트 body 카테고리(경제/기술)


def _scan_report_files(webroot):
    """webroot의 개별 영상 리포트 파일을 직접 스캔 → (slug, date, title, channel, cat).
    'MORNING DIGEST · 날짜 · 채널' 마커로 리포트만 선별(비리포트/슬라이드/index 등 제외).
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
        if not md:                 # MORNING DIGEST 마커 없으면 개별 영상 리포트 아님
            continue
        tt = _TITLE_TAG_RE.search(h)
        title = _unescape(tt.group(1).strip()) if tt else slug
        cm = _CAT_RE.search(h)
        cat = cm.group(1) if cm else "tech"
        yield slug, m.group(1), title, _unescape(md.group(1).strip()), cat


def load_individual_reports(webroot):
    """개별리포트: 개별 유튜브 영상 리포트 → slug당 1건.

    2026-08-21: 소스를 index.html 카드 + 실제 리포트 파일 스캔의 **union**으로 확장.
    07-25 'Daily Youtube Brief 전환'(daybreak_finish.py:8) 이후 개별 카드가 index.html에
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
        items.append({
            "date": date,
            "pub": "개별리포트",
            "cat": cat,
            "title": title,
            "summary": "",
            "url": f"{BRIEF_BASE_URL}{slug}.html",
            "channel": channel,
        })
    return items


def reconstruct_briefs(reports):
    """개별 리포트를 (날짜, 카테고리)로 묶어 일일 브리프(기술)/시황(경제) 집계 항목을 재구성한다.
    2026-08-21: origin index.html이 AI 데일리 리다이렉트로 바뀌어 카드 소스가 사라짐 → 집계 항목
    소실. 개별 리포트(파일 스캔)에서 되살린다. summary에 그날 영상 제목을 담아 집계 항목으로도
    개별 영상이 검색된다. url은 편성페이지(오늘=라이브, 과거=AI 데일리 리다이렉트)."""
    from collections import defaultdict
    groups = defaultdict(list)
    for r in reports:
        groups[(r["date"], r.get("cat", "tech"))].append(r)
    out = []
    for (date, cat), rs in sorted(groups.items(), reverse=True):
        econ = (cat == "econ")
        # 편성페이지(과거)는 AI 데일리로 리다이렉트돼 클릭 시 뉴스로 새므로, 브리프 항목은
        # 검색 자체를 그날·카테고리로 드릴다운(개별 리포트 노출)하게 자기참조 링크로 건다.
        out.append({
            "date": date,
            "pub": "시황" if econ else "브리프",
            "cat": cat,
            "title": f"{'시황 브리프' if econ else 'AI·기술 브리프'} · {date}",
            "summary": (" · ".join(r["title"] for r in rs))[:500],
            "url": f"search.html?date={date}&cat={cat}",
        })
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--webroot", default=DEFAULT_WEBROOT,
                     help="브리프 index.html이 있는 웹루트 (기본: ~/Sites/ai-infographic)")
    ap.add_argument("--out", default=os.path.join(_HERE, "search-index.json"),
                     help="출력 경로 (기본: docs/search-index.json)")
    a = ap.parse_args()

    webroot = os.path.expanduser(a.webroot)
    beacon_docs = _HERE

    news = load_news(beacon_docs)
    uvoice = load_uservoice(beacon_docs)
    reports = load_individual_reports(webroot)
    # 브리프(기술)/시황(경제) 집계는 index.html 카드가 리다이렉트로 사라져(2026-08-21),
    # 개별 리포트를 (날짜, 카테고리)로 묶어 재구성한다(load_daily_briefs는 리다이렉트라 0건).
    daily_briefs_all = reconstruct_briefs(reports)

    # url 기준 최종 유일화(안전망) — 편성페이지·개별리포트는 카드가 중복 등록될 수 있어
    # (pub, url) 기준으로 한 번 더 거른다. 뉴스는 날짜별 1건이 모두 같은 archive.html을
    # 가리키므로(설계상 정상) 제외한다.
    def dedupe(items):
        out, seen = [], set()
        for item in items:
            key = (item["pub"], item["url"])
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    daily_briefs_all = dedupe(daily_briefs_all)
    reports = dedupe(reports)

    briefs = [x for x in daily_briefs_all if x["pub"] == "브리프"]
    econ = [x for x in daily_briefs_all if x["pub"] == "시황"]

    combined = news + uvoice + daily_briefs_all + reports

    combined.sort(key=lambda x: x.get("date", ""), reverse=True)

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    print(f"[완료] {a.out}")
    print(f"  뉴스     : {len(news)}건")
    print(f"  보이스   : {len(uvoice)}건")
    print(f"  브리프   : {len(briefs)}건")
    print(f"  시황     : {len(econ)}건")
    print(f"  개별리포트: {len(reports)}건")
    print(f"  합계     : {len(combined)}건")


if __name__ == "__main__":
    main()
