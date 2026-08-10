"""맥미니 nlm-infographic /generate 호출 — 세로·연두·내용요약 인포그래픽 생성.

Ported from nlm_call.py. SLOW (~수십초~수 분, 브라우저 자동화) — dry-run should
pass --skip-infographic to briefer.build instead of calling this.
"""
import json
import struct
import sys
import urllib.error
import urllib.request

TOKEN_PATH = "/Users/woojanghoon/nlm-infographic/.api_token"
URL = "http://127.0.0.1:8791/generate"


def _content_and_instruction(brief):
    """Build the API `content`/`instruction` text from today's brief doc."""
    date = brief.get("date", "")
    title = brief.get("title", "")
    summary = brief.get("summary", "")
    stories = brief.get("stories") or []

    lines = [f"오늘의 AI 뉴스 핵심 요약 ({date}).", "", f"오늘의 테마: {title}", ""]
    if summary:
        lines.append(f"요약: {summary}")
        lines.append("")
    lines.append("핵심 뉴스:")
    for s in stories:
        headline = s.get("headline", "")
        takeaway = s.get("takeaway") or (s.get("why_bullets") or [""])[0]
        n = s.get("n", "")
        lines.append(f"{n}) {headline}" + (f" — {takeaway}" if takeaway else ""))
    content = "\n".join(lines)

    instruction = (
        f"제목은 '오늘의 AI 뉴스', 부제로 날짜 '{date}'. "
        "이것은 하루 뉴스의 '내용 요약' 인포그래픽이다(기사 제목 나열이 아님). "
        "핵심 수치·사실을 큰 숫자와 간결한 차트로 제시. "
        "★디자인=모노톤: 전체를 무채색(검정·짙은회색·연회색·흰색)으로만 구성하고, 색상은 오직 "
        "'에메랄드 그린 #059669' 하나만 포인트로 아주 절제해서 사용(핵심 수치·강조에만). "
        "그 외 텍스트·차트·아이콘·선·배경은 무채색. 일러스트·이모지·다색 그래프·그라디언트·장식 금지. "
        "미니멀·여백 넉넉한 에디토리얼. 세로 포맷. 출처/로고/워터마크 없음."
    )
    return content, instruction


def generate(out_path, brief, rich=None):
    """Call the nlm-infographic API and write a portrait PNG to out_path.

    rich: 대표기사 원문 종합 dict(article.synthesize_rich). 있으면 원문 기반 content,
    없으면 뉴스 요약 기반으로 폴백.
    """
    token = open(TOKEN_PATH).read().strip()
    if rich:
        from briefer import article
        content, instruction = article.rich_content_and_instruction(rich, brief.get("date", ""))
        print("[infographic] 원문 종합(rich) content 사용", file=sys.stderr)
    else:
        content, instruction = _content_and_instruction(brief)
    body = {"method": 1, "content": content, "instruction": instruction,
            "orientation": "세로", "allow_fallback": True, "format": "png"}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-API-Token": token})
    print("[infographic] 호출 시작(브라우저 자동화, 수십 초~수 분)...", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=420) as r:
            data = r.read()
            hdr = dict(r.headers)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"infographic HTTPError {e.code}: {e.read().decode()[:400]}")
    open(out_path, "wb").write(data)
    w = h = 0
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
    print(f"[infographic] OK → {out_path} ({len(data)//1024}KB) {w}x{h} "
          f"method={hdr.get('X-Infographic-Method')} "
          f"fellback={hdr.get('X-Infographic-Fellback')} "
          f"elapsed={hdr.get('X-Elapsed-Sec')}s", file=sys.stderr)
    return out_path
