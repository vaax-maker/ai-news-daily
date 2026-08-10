"""Firestore fetch + deterministic parsing for aiofmodu.com daily-news docs.

Ported from validated prototypes:
  - build_proto.py: val() (incl. doubleValue), fetch_today(), parse_stories() (incl. emoji field)
  - backfill.py: clean() (incl. U+FFFD strip), fetch_all() (paginated, newest-first)
"""
import html
import json
import re
import urllib.request

PROJECT = "modu-ai-portal"
KEY = "AIzaSyDBacvlgCpiECpnNzft58rpIRgQ4-B8SC8"
RUNQ = (f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
        f"/databases/(default)/documents:runQuery?key={KEY}")

LABELS = ("주요내용", "핵심 포인트", "원문 기사")


def val(v):
    if not isinstance(v, dict):
        return v
    for t in ("stringValue", "integerValue", "booleanValue", "timestampValue", "doubleValue"):
        if t in v:
            return v[t]
    if "arrayValue" in v:
        return [val(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v:
        return {k: val(x) for k, x in v["mapValue"].get("fields", {}).items()}
    if "nullValue" in v:
        return None
    return next(iter(v.values()), None)


def clean(s):
    # 소스(모두의AI)에 저장된 깨진 문자 U+FFFD 제거(복구 불가·아티팩트 배포 거부 대응)
    s = (s or "").replace("�", "")
    return html.unescape(re.sub(r"\s+", " ", s)).strip()


def _query(body):
    req = urllib.request.Request(RUNQ, data=json.dumps(body).encode(),
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def fetch_today():
    body = {"structuredQuery": {"from": [{"collectionId": "contents"}],
            "orderBy": [{"field": {"fieldPath": "date"}, "direction": "DESCENDING"}], "limit": 5}}
    rows = _query(body)
    for r in rows:
        d = r.get("document")
        if d and val(d["fields"].get("type")) == "daily-news":
            return {k: val(v) for k, v in d["fields"].items()}
    raise SystemExit("daily-news 없음")


def parse_stories(content):
    """Parse a daily-news `content` HTML blob into per-story dicts.

    Each story: n, emoji, headline, body, takeaway, url.
    """
    hrefs = re.findall(r'<a[^>]+href="([^"]+)"', content or "")
    txt = re.sub(r"<style.*?</style>", "", content or "", flags=re.S)
    txt = re.sub(r"<[^>]+>", "\n", txt)
    lines = [clean(l) for l in txt.split("\n") if clean(l)]
    stories, cur, mode = [], None, None
    for l in lines:
        if re.fullmatch(r"\d{2}", l):
            if cur:
                stories.append(cur)
            cur = {"n": l, "emoji": "", "headline": "", "body": "", "takeaway": "", "url": ""}
            mode = "headline"
            continue
        if cur is None:
            continue
        if mode == "headline":
            cur["headline"] = l
            mode = "emoji"
            continue
        if mode == "emoji":
            if any(l.startswith(x) for x in LABELS):
                pass
            elif len(l) <= 3:
                cur["emoji"] = l
                continue
        if l.startswith("주요내용"):
            mode = "body"; continue
        if l.startswith("핵심 포인트"):
            mode = "take"; continue
        if l.startswith("원문 기사"):
            mode = "src"; continue
        if mode == "body":
            cur["body"] = (cur["body"] + " " + l).strip()
        elif mode == "take":
            cur["takeaway"] = (cur["takeaway"] + " " + l).strip()
    if cur:
        stories.append(cur)
    for i, s in enumerate(stories):
        s["url"] = hrefs[i] if i < len(hrefs) else ""
    return stories


def fetch_all():
    """Paginate ALL daily-news docs from Firestore, newest first."""
    out, cur = [], None
    while True:
        sq = {"from": [{"collectionId": "contents"}],
              "orderBy": [{"field": {"fieldPath": "date"}, "direction": "ASCENDING"},
                          {"field": {"fieldPath": "__name__"}, "direction": "ASCENDING"}],
              "limit": 300}
        if cur:
            sq["startAt"] = {"values": cur, "before": False}
        rs = _query({"structuredQuery": sq})
        got = [r["document"] for r in rs if r.get("document")]
        if not got:
            break
        for d in got:
            f = {k: val(v) for k, v in d["fields"].items()}
            if f.get("type") != "daily-news":
                continue
            out.append({
                "date": clean(f.get("date")), "newsTime": clean(f.get("newsTime")),
                "title": clean(f.get("title")), "summary": clean(f.get("summary")),
                "stories": [{"n": s["n"], "emoji": s["emoji"], "headline": s["headline"],
                             "body": s["body"], "takeaway": s["takeaway"], "url": s["url"]}
                            for s in parse_stories(f.get("content", ""))],
            })
        last = got[-1]
        cur = [{"stringValue": val(last["fields"].get("date"))}, {"referenceValue": last["name"]}]
        if len(got) < 300:
            break
    out.sort(key=lambda x: x["date"], reverse=True)  # 최신순
    return out
