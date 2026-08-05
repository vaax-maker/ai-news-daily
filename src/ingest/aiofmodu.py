"""모두의 AI(aiofmodu.com) 인제스트 — 오늘 키워드·트렌드·앵글 참조 신호 (04 §4.5).

데이터 소스: 모두의 AI 는 Firestore(project=modu-ai-portal, 컬렉션 'contents')를
공개(로그인 없이) 서빙한다. 여기서 type='daily-news' 최근 문서를 Firestore REST로
읽어 헤드라인·태그(키워드)를 뽑는다. HTML 스크랩보다 안정적(JS 렌더 불필요).

원칙(04 §4.5): 이 신호는 **키워드·앵글 힌트로만** 사용한다. 사실(fact)은 우리 후보
뉴스에서만 취하고, 모두의 AI 문장을 verbatim 복사하지 않는다(저작권). 접근 실패 시
보조 신호이므로 조용히 스킵(ok=False)하고 발행은 계속한다.
"""
from __future__ import annotations
import json
import urllib.request

_PROJECT = "modu-ai-portal"
_KEY = "AIzaSyDBacvlgCpiECpnNzft58rpIRgQ4-B8SC8"  # 공개 웹 클라이언트 키(모두의 AI가 클라이언트에 노출)
_RUNQ = (f"https://firestore.googleapis.com/v1/projects/{_PROJECT}"
         f"/databases/(default)/documents:runQuery?key={_KEY}")
_FIELDS = ("type", "title", "summary", "tags", "highlights", "date", "newsTime")


def _val(v):
    if not isinstance(v, dict):
        return v
    if "stringValue" in v:
        return v["stringValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "booleanValue" in v:
        return v["booleanValue"]
    if "arrayValue" in v:
        return [_val(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v:
        return {k: _val(x) for k, x in v["mapValue"].get("fields", {}).items()}
    return next(iter(v.values()), None)


def fetch_daily(limit: int = 6, scan: int = 30, timeout: int = 15) -> list[dict]:
    """type=daily-news 최근 문서. date 단일필드 정렬(복합 인덱스 불필요) 후 클라 필터."""
    body = {"structuredQuery": {
        "from": [{"collectionId": "contents"}],
        "orderBy": [{"field": {"fieldPath": "date"}, "direction": "DESCENDING"}],
        "select": {"fields": [{"fieldPath": f} for f in _FIELDS]},
        "limit": scan,
    }}
    req = urllib.request.Request(_RUNQ, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rows = json.loads(r.read().decode("utf-8"))
    out = []
    for row in rows:
        doc = row.get("document")
        if not doc:
            continue
        f = {k: _val(v) for k, v in doc.get("fields", {}).items()}
        if f.get("type") != "daily-news":
            continue
        out.append({
            "title": f.get("title", "") or "",
            "summary": f.get("summary", "") or "",
            "tags": [t for t in (f.get("tags") or []) if t],
            "highlights": [h for h in (f.get("highlights") or []) if h],
            "date": f.get("date", "") or "",
        })
        if len(out) >= limit:
            break
    return out


def build_signal(limit: int = 6) -> dict:
    """대표 선정/함의 생성에 넣을 참조 신호. 실패해도 예외 없이 ok=False."""
    try:
        items = fetch_daily(limit=limit)
    except Exception as e:  # noqa
        return {"ok": False, "error": str(e)[:200], "headlines": [], "keywords": []}
    headlines = [it["title"] for it in items if it["title"]]
    kws = []
    for it in items:
        kws += it.get("tags", [])
    kws = list(dict.fromkeys(kws))[:20]
    return {"ok": True, "headlines": headlines, "keywords": kws, "items": items}


if __name__ == "__main__":
    sig = build_signal()
    print(f"ok={sig['ok']} headlines={len(sig['headlines'])} keywords={len(sig['keywords'])}")
    for h in sig["headlines"]:
        print(" •", h)
    print(" 키워드:", ", ".join(sig["keywords"]))
