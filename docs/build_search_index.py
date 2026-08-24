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


def _domain(url):
    m = re.search(r"https?://([^/]+)", url or "")
    return m.group(1).replace("www.", "") if m else ""


def load_news(beacon_docs):
    """AI 뉴스: docs/archive/index.json → 그날의 개별 기사(stories[]) 각각 1건.

    2026-08-24: 종합 1건 → **개별 기사 N건화**. 페이지가 'AI뉴스 5건(+신규 소스)'을 개별 카드로
    노출하도록. url은 기사 원문, channel은 출처 도메인. stories가 없으면 종합 1건으로 폴백."""
    path = os.path.join(beacon_docs, "archive", "index.json")
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
            items.append({"date": date, "pub": "뉴스", "title": d.get("title", ""),
                          "summary": d.get("summary", ""), "url": NEWS_ARCHIVE_URL})
            continue
        for s in stories:
            items.append({
                "date": date, "pub": "뉴스", "n": s.get("n", ""),
                "title": s.get("headline", "") or d.get("title", ""),
                "summary": s.get("body", "") or "",
                "why": s.get("takeaway", "") or "",
                "url": s.get("url") or NEWS_ARCHIVE_URL,
                "channel": _domain(s.get("url", "")),
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
#   kind: news | usecase | report   (pub → kind 매핑)
#   cat : tech | econ                (없으면 pub 기준 채움 — 뉴스/보이스=tech, 시황=econ)
#   source: 신 용어 피드 라벨(AI뉴스/고객사용기/오늘 유튜브/시황)  ← 제품 갈래 표기
#   edition: 아침/저녁 (시황 분리 전이라 현재 None)
_PUB_TO_KIND = {"뉴스": "news", "보이스": "usecase", "브리프": "report",
                "시황": "report", "개별리포트": "report"}
_PUB_TO_CAT = {"뉴스": "tech", "보이스": "tech", "브리프": "tech", "시황": "econ"}
_PUB_TO_SOURCE = {"뉴스": "AI뉴스", "보이스": "고객사용기", "브리프": "오늘 유튜브",
                  "시황": "시황", "개별리포트": "오늘 유튜브"}


def _slug_from_url(url):
    base = (url or "").rstrip("/").split("/")[-1]
    return base[:-5] if base.endswith(".html") else base


def enrich_unified(items):
    """각 레코드에 통합 스키마 필드(id·kind·cat·source·edition)를 additive로 채운다.
    기존 필드는 절대 덮지 않는다(cat은 없을 때만 채움)."""
    for it in items:
        pub = it.get("pub", "")
        if not it.get("cat"):                       # 뉴스/보이스는 cat이 없어 채움
            it["cat"] = _PUB_TO_CAT.get(pub, "tech")
        it["kind"] = _PUB_TO_KIND.get(pub, "report")
        it["source"] = _PUB_TO_SOURCE.get(pub, pub)
        it.setdefault("edition", None)              # 아침/저녁 분리 전 → None
        slug = _slug_from_url(it.get("url", ""))
        if pub == "뉴스":                            # 개별 기사 → date:n 으로 유일
            n = it.get("n")
            it["id"] = f"news:{it.get('date', '')}" + (f":{n}" if n else "")
        elif pub == "보이스":                        # 날짜당 1건
            it["id"] = f"usecase:{it.get('date', '')}"
        else:
            it["id"] = f"{_PUB_TO_KIND.get(pub, 'report')}:{slug or it.get('date', '')}"
    # id 유일성 보장 — 같은 날 중복 뉴스 등 충돌 시 -2, -3 접미(결정적).
    seen = {}
    for it in items:
        base = it["id"]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            it["id"] = f"{base}-{seen[base]}"
    return items


def _news_docs(default_docs):
    """AI 뉴스 archive의 최신 소스 docs를 고른다.
    워크트리 분기 대비: 뉴스 생산자는 v3(feat/v3-rebuild)라 beacon(main) 사본이 며칠 뒤처질 수
    있다. 후보 archive/index.json 중 최신 date가 가장 큰 docs를 쓴다. NEWS_DOCS로 강제 가능."""
    env = os.environ.get("NEWS_DOCS")
    if env:
        return os.path.expanduser(env)
    best, best_date = default_docs, ""
    for c in (os.path.expanduser("~/ai-news-daily-v3/docs"), default_docs):
        try:
            dd = json.load(open(os.path.join(c, "archive", "index.json"), encoding="utf-8"))
            mx = max((x.get("date", "") for x in dd), default="")
            if mx > best_date:
                best_date, best = mx, c
        except Exception:
            continue
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--webroot", default=DEFAULT_WEBROOT,
                     help="브리프 index.html이 있는 웹루트 (기본: ~/Sites/ai-infographic)")
    ap.add_argument("--out", default=os.path.join(_HERE, "search-index.json"),
                     help="출력 경로 (기본: docs/search-index.json)")
    a = ap.parse_args()

    webroot = os.path.expanduser(a.webroot)
    beacon_docs = _HERE

    news_docs = _news_docs(beacon_docs)
    if news_docs != beacon_docs:
        print(f"  [뉴스 소스] 최신 archive = {news_docs} (beacon 사본보다 최신)", file=sys.stderr)
    news = load_news(news_docs)
    uvoice = load_uservoice(beacon_docs)
    reports = load_individual_reports(webroot)
    # 브리프(기술)/시황(경제) 집계 = 실제 편성페이지 파일 스캔(진실원천). 리포트 그룹핑 재구성은
    # 404·누락을 냈다(2026-08-21 감사) → 실제 존재하는 브리프 파일만 항목화.
    daily_briefs_all = load_briefs_from_files(webroot)

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

    # 통합 스키마 필드(id·kind·cat·source·edition) additive 보강 — 비파괴.
    enrich_unified(combined)

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    with_id = sum(1 for x in combined if x.get("id"))
    with_cat = sum(1 for x in combined if x.get("cat"))
    print(f"[완료] {a.out}")
    print(f"  뉴스     : {len(news)}건")
    print(f"  보이스   : {len(uvoice)}건")
    print(f"  브리프   : {len(briefs)}건")
    print(f"  시황     : {len(econ)}건")
    print(f"  개별리포트: {len(reports)}건")
    print(f"  합계     : {len(combined)}건  (통합필드: id {with_id}/{len(combined)} · cat {with_cat}/{len(combined)})")


if __name__ == "__main__":
    main()
