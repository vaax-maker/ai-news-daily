"""대표기사 원문 fetch + terra 종합 — 정보 밀도 높은 인포그래픽 content.

top-N 스토리의 원문(source url) 본문을 읽어와 핵심 수치·사실을 LLM(OpenRouter)으로
종합한다. 원문 fetch/종합 실패 시 None을 반환 → 호출부가 뉴스 요약으로 폴백한다.
키: 환경변수 OPENROUTER_API_KEY (없으면 None).
"""
import gzip
import json
import os
import re
import sys
import urllib.request

MODEL = os.environ.get("OUTLINE_MODEL", "openai/gpt-5.6-terra")
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_BODY_PATTERNS = (
    r'<article[^>]*id="dic_area"[^>]*>(.*?)</article>',        # 네이버
    r'id="newsct_article"[^>]*>(.*?)</div>\s*</div>',
    r'id="article-view-content-div"[^>]*>(.*?)</div>',         # AI타임스 등
    r'<article[^>]*>(.*?)</article>',                          # 일반 폴백
)


def fetch_body(url):
    """기사 원문 본문 텍스트(최대 3500자). 실패 시 빈 문자열."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept-Language": "ko"})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            html = raw.decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"[article] fetch 실패 {type(e).__name__}: {str(e)[:80]} · {url[:60]}", file=sys.stderr)
        return ""
    for pat in _BODY_PATTERNS:
        m = re.search(pat, html, re.S)
        if m:
            t = re.sub(r"<script.*?</script>|<style.*?</style>", "", m.group(1), flags=re.S)
            t = re.sub(r"<[^>]+>", " ", t)
            t = re.sub(r"&[a-z]+;", " ", t)
            t = re.sub(r"\s+", " ", t).strip()
            if len(t) > 200:
                return t[:3500]
    return ""


_SYS = (
 "너는 데이터 저널리스트다. 아래 대표기사들의 '원문 본문'을 읽고, 하루 AI 뉴스의 정보 밀도 "
 "높은 인포그래픽에 넣을 핵심을 종합한다. 규칙: 원문에 실제로 나온 수치·고유명사·인용만 사용"
 "(창작·추정 금지). 다음 형식의 JSON만 출력:\n"
 '{"theme":"오늘의 테마 한 줄(사실 기반)",'
 '"facts":[{"stat":"큰 수치/키워드","label":"짧은 설명(원문 근거)"}, ...4개],'
 '"insight":"종합 시사점 한 줄"}\n'
 "facts는 4개, stat은 숫자·비율·핵심어 위주, label은 30자 내외."
)


def synthesize_rich(stories, top_n=3):
    """top_n 스토리 원문 fetch + 종합 → {theme, facts, insight} 또는 None(실패)."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key:
        print("[article] OPENROUTER_API_KEY 없음 → rich 종합 생략", file=sys.stderr)
        return None
    items, got = [], 0
    for s in stories[:top_n]:
        body = fetch_body(s.get("url", ""))
        if body:
            got += 1
        items.append({"headline": s.get("headline", ""),
                      "source_body": body or s.get("body", "")})
    if got == 0:
        print("[article] 원문 0건 fetch → rich 종합 생략(요약 폴백)", file=sys.stderr)
        return None
    body = {"model": MODEL, "temperature": 0.2,
            "messages": [{"role": "system", "content": _SYS},
                         {"role": "user", "content": json.dumps(items, ensure_ascii=False)}]}
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(body).encode(),
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://ai-news-daily.local", "X-Title": "aidaily"})
        with urllib.request.urlopen(req, timeout=120) as r:
            txt = json.loads(r.read().decode())["choices"][0]["message"]["content"]
        txt = re.sub(r"```(json)?", "", txt).replace("```", "").strip()
        rich = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
        if rich.get("facts"):
            print(f"[article] 원문 {got}건 종합 ok (facts={len(rich['facts'])})", file=sys.stderr)
            return rich
    except Exception as e:  # noqa: BLE001
        print(f"[article] 종합 실패 {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
    return None


def rich_content_and_instruction(rich, date):
    """rich 종합 → nlm API용 (content, instruction)."""
    facts = "\n".join(f"{i+1}) {f.get('stat','')} — {f.get('label','')}"
                      for i, f in enumerate(rich.get("facts", [])))
    content = (f"오늘의 AI 뉴스\n{date}\n\n테마: {rich.get('theme','')}\n\n"
               f"핵심 수치:\n{facts}\n\n시사점: {rich.get('insight','')}")
    instruction = (
        f"하루 AI 뉴스의 '내용 요약' 인포그래픽(기사 제목 나열 아님). 제목 '오늘의 AI 뉴스', "
        f"날짜 뱃지 '{date}'. 4개 핵심 수치를 큰 숫자와 간결한 차트(막대·라인·도넛)로 제시. "
        "★디자인=모노톤: 전체를 무채색(검정·짙은회색·연회색·흰색)으로만 구성하고, 색상은 오직 "
        "'에메랄드 그린 #059669' 하나만 포인트로 아주 절제해서 사용한다(핵심 수치·강조 요소에만). "
        "그 외 모든 텍스트·차트·아이콘·선·배경은 무채색. 일러스트·이모지·다색 그래프·그라디언트·"
        "장식 금지. 미니멀하고 여백 넉넉한 에디토리얼. 세로 포맷. 출처·로고·워터마크 없음."
    )
    return content, instruction
