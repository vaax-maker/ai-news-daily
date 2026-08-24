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


def _top3_content_and_instruction(brief):
    """상위 3개 기사를 '기사별 카드'로 채우는 content/instruction (2026-08-14 확정 스타일).

    각 기사 = 헤드라인 + 개조식 본문(body_bullets) + '왜 중요한가'(why_bullets).
    큰 수치 하나 강조가 아니라 각 기사 공간을 디테일하게 채운다. 세리프 마스트헤드 제목,
    얼굴 아이콘 없음, 단일 녹색 #0E9E7E 포인트.
    """
    date = brief.get("date", "")
    stories = (brief.get("stories") or [])[:3]
    secs = []
    for i, s in enumerate(stories, 1):
        bb = "\n".join(f"  · {x}" for x in (s.get("body_bullets") or []))
        wb = "\n".join(f"  → {x}" for x in (s.get("why_bullets") or []))
        secs.append(f"[{i}] {s.get('headline', '')}\n본문:\n{bb}\n왜 중요:\n{wb}")
    content = (f"오늘의 AI 뉴스 · {date}\n상위 3개 기사 (위 → 아래로 각 기사 카드)\n\n"
               + "\n\n".join(secs))
    instruction = (
        "'오늘의 AI 뉴스' 상위 3개 기사를 위에서 아래로 3개 섹션(카드)으로 배치. 이 인포그래픽은 웹 "
        "'AI 데일리' 페이지(따뜻한 종이색 배경 + 흰 카드 + 인디고 포인트)의 표지 이미지이므로, 카드 자체를 "
        "웹의 스토리 카드처럼 '독립된 흰색(또는 아주 옅은 종이색) 카드 3장'으로 명확히 구획하고, 카드마다 "
        "은은한 라운드 코너와 얇은 테두리로 web 카드와 같은 톤을 낸다. "
        "유튜브 브리프 인포그래픽 수준으로 각 기사 공간을 '디테일하게' 채운다 — 큰 수치 하나만 강조하지 말고, "
        "각 기사를 개조식 명사형 요점 여러 개 + 관련 수치는 미니 표/카드/작은 차트 + 아이콘·간단 다이어그램으로 "
        "고르게 채운다. 각 카드 = 번호(웹의 '01·02·03' 인디고 라벨과 동일한 스타일) + 헤드라인(크게, 진한 잉크색) "
        "+ 본문 개조식 3~4개(불릿 대신 짧은 인디고 틱 마커) + 수치 표/카드 + '왜 중요한가' 박스(옅은 인디고 틴트 "
        "배경의 별도 서브카드, 웹의 하이라이트 박스와 동일 구조). "
        "표가 어울리는 기사는 순위/모델/점수 표로 정리. 정보량 충분히 담되 과밀하지 않게(여백, 약 80% 밀도). "
        "★상단 제목은 '오늘의 AI 뉴스' 워드마크 — 정제된 굵은 커스텀 레터링, 고급 잡지 마스트헤드 같은 "
        "미니멀·프리미엄 감성(웹 페이지의 절제된 헤드라인 타이포와 같은 무게감). 절제된 기하학 포인트 1~2개, "
        "인디고 액센트도 필요한 곳에만 절제해서. 스우시·장식선·점패턴 남발 금지 — 균형 잡히고 정돈된 타이포그래피 "
        "중심. "
        "★사람 얼굴·인물 실루엣·캐릭터 아이콘은 어디에도 넣지 말 것(도넛 차트 중앙 등 포함). 아이콘은 추상·개념형만. "
        "★색: 배경은 웹과 같은 따뜻한 종이색 계열(크림·아이보리, 순백 아님)에 카드는 흰색, 본문 텍스트는 짙은 잉크색"
        "(거의 검정), 보조 텍스트는 중간 회갈색. 포인트 컬러는 오직 '인디고 #3450E0' 단일 톤 하나만 일관되게 사용"
        "(번호·강조 수치·틱 마커·'왜 중요한가' 라벨·박스 테두리에만, 여러 색조·명암 편차 금지, 보라·청록 금지). "
        "그 외 아이콘·선·차트는 무채색 위주로 절제. 카드 배경에서 인디고 텍스트가 고대비로 또렷하게. "
        "개조식 명사형, 표·다이어그램·카드 우선. 이모지·다색 그래프·그라디언트·과한 장식·로고·워터마크 금지. "
        f"세로 포맷, 미니멀 에디토리얼(웹 'AI 데일리' 페이지와 같은 톤앤매너). 날짜 뱃지 '{date}'.")
    return content, instruction


def _hero_content_and_instruction(brief):
    """Hero(표지) 커버 — 그날의 주요 소식을 '도식화'한 가로 16:6 콘텐츠/지시.

    단순 제목 나열이 아니라 대표 소식의 사실·수치·관계를 도식(흐름도/관계도/비교/타임라인)으로
    시각화하도록 유도. 통합 '기술 데일리' 표지에 들어가므로 포인트색=accent.tech(#2E5FE0)."""
    date = brief.get("date", "")
    title = brief.get("title", "")
    summary = brief.get("summary", "")
    stories = (brief.get("stories") or [])[:3]
    secs = []
    for i, s in enumerate(stories, 1):
        fact = s.get("body", "")
        why = s.get("takeaway") or (s.get("why_bullets") or [""])[0]
        secs.append(f"[{i}] {s.get('headline', '')}\n  사실: {fact}\n  함의: {why}")
    content = (f"오늘의 AI 소식 · {date} — 그날의 주요 소식(도식화 대상)\n"
               f"오늘의 테마: {title}\n{('요약: ' + summary) if summary else ''}\n\n"
               + "\n\n".join(secs))
    instruction = (
        "'오늘의 AI 소식' 통합 표지 히어로 이미지. **가로 와이드 16:6**. "
        "★그날의 주요 소식을 '도식화'한다 — 기사 제목 단순 나열 절대 금지. "
        "대표 소식 1건을 화면 중심의 큰 도식(흐름도·관계도·비교·타임라인 중 적합한 형태)으로 시각화하고, "
        "핵심 수치는 큰 숫자로, 주체·원인·결과의 관계를 화살표/구조로 드러낸다. 나머지 소식은 주변 보조 요소로 작게. "
        "★디자인=모노톤: 무채색(검정·짙은회색·연회색·흰색) 기반, 포인트 컬러는 오직 '인디고 #2E5FE0' 하나만 "
        "핵심 수치·강조·화살표에 절제해서. 배경은 따뜻한 종이색 계열(크림·아이보리). "
        "★사람 얼굴·인물·캐릭터·이모지·일러스트·다색 그래프·그라디언트·로고·워터마크 금지. 아이콘은 추상·개념형만. "
        f"상단 워드마크 '오늘의 AI 소식', 부제 날짜 '{date}'. 미니멀·여백 넉넉한 프리미엄 에디토리얼. 한국어. "
        "**가로(16:6) 포맷.**")
    return content, instruction


def generate_hero(out_path, brief):
    """그날 주요 소식을 도식화한 가로 16:6 Hero 커버 PNG 생성(nlm API, method 1)."""
    token = open(TOKEN_PATH).read().strip()
    content, instruction = _hero_content_and_instruction(brief)
    body = {"method": 1, "content": content, "instruction": instruction,
            "orientation": "가로", "allow_fallback": True, "format": "png"}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-API-Token": token})
    print("[hero] 도식화 커버 생성 시작(가로 16:6, 브라우저 자동화, 수십 초~수 분)...", file=sys.stderr)
    try:
        with urllib.request.urlopen(req, timeout=420) as r:
            data = r.read()
            hdr = dict(r.headers)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"hero HTTPError {e.code}: {e.read().decode()[:400]}")
    open(out_path, "wb").write(data)
    w = h = 0
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
    print(f"[hero] OK → {out_path} ({len(data)//1024}KB) {w}x{h} "
          f"method={hdr.get('X-Infographic-Method')} "
          f"fellback={hdr.get('X-Infographic-Fellback')} "
          f"elapsed={hdr.get('X-Elapsed-Sec')}s", file=sys.stderr)
    return out_path


def generate(out_path, brief, rich=None):
    """Call the nlm-infographic API and write a portrait PNG to out_path.

    2026-08-14: 상위 3개 기사를 '기사별 카드'로 채우는 확정 스타일 사용(rich 무시).
    """
    token = open(TOKEN_PATH).read().strip()
    content, instruction = _top3_content_and_instruction(brief)
    print("[infographic] 상위 3기사 카드 스타일 content 사용", file=sys.stderr)
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
