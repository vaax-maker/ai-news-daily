"""Horizontal AI News hero prompt assembly."""
import copy
import datetime
import struct
import sys
import urllib.error

from aidaily import config
from aidaily.ai_news import visual_brief
from aidaily.integrations.infographic import InfographicClient
from aidaily.integrations import content_settings

CLIENT = InfographicClient()

THREE_VIGNETTES = "THREE_VIGNETTES"


def _display_headline(value: str, limit: int = 18) -> str:
    """Return a compact image title; full wording remains in the HTML article."""
    text = str(value or "").strip()
    first = text.split(",", 1)[0].strip()
    candidate = first if 5 <= len(first) <= limit else text
    return candidate[:limit].rstrip(" ,·-")
def _today_youtube_story(date: str) -> dict | None:
    """당일 검증 리포트만 사용한다."""
    try:
        from aidaily.publishing import search_index
        reports = search_index.load_individual_reports(str(config.PUBLISHING_REPOSITORY))
    except Exception as exc:
        print(f"[hero] 오늘 유튜브 조회 실패: {type(exc).__name__}", file=sys.stderr)
        return None
    tech_reports = [item for item in reports if item.get("cat", "tech") == "tech"]
    report = next((item for item in tech_reports if item.get("date") == date), None)
    if not report:
        return None
    channel = str(report.get("channel") or "오늘 유튜브").strip()
    title = str(report.get("title") or "오늘의 YouTube 리포트").strip()
    report_date = str(report.get("date") or date)
    source = "오늘 유튜브"
    return {
        "source": source, "headline": title,
        "body": str(report.get("summary") or "").strip(),
        "takeaway": f"{channel}의 {report_date} 영상에서 읽은 핵심 신호",
        "url": str(report.get("url") or ""), "channel": channel,
        "report_date": report_date,
    }


def _today_customer_story(date: str) -> dict | None:
    """당일 고객사용기에서 인포그래픽의 출발점이 될 한 주제를 읽는다."""
    try:
        from aidaily.publishing import search_index
        stories = search_index.load_customer_stories(str(config.DOCS_ROOT))
    except Exception as exc:
        print(f"[hero] 오늘 고객사용기 조회 실패: {type(exc).__name__}", file=sys.stderr)
        return None
    story = next((item for item in stories if item.get("date") == date), None)
    if not story:
        return None
    channel = str(story.get("channel") or "고객사용기").strip()
    title = str(story.get("title") or "오늘의 고객 목소리").strip()
    return {
        "source": "고객사용기", "headline": title,
        "body": str(story.get("summary") or "").strip(),
        "takeaway": str(story.get("why") or "").strip() or "사용자가 실제 현장에서 겪은 문제와 기대",
        "url": str(story.get("url") or ""), "channel": channel, "report_date": date,
    }


def _selected_stories(brief, policy=None):
    """커버를 고객사용기 → 오늘 유튜브 → AI뉴스의 세 장면으로 구성한다."""
    policy = policy or {}
    story_mix = policy.get("story_mix") or ["customer_story", "today_youtube", "ai_news"]
    if story_mix != ["customer_story", "today_youtube", "ai_news"]:
        raise RuntimeError("지원하지 않는 인포그래픽 편성: " + " · ".join(story_mix))
    prepared = brief.get("cover_stories")
    if isinstance(prepared, list):
        from .hero_validation import validate_sources
        if [item.get("hero_role") for item in prepared if isinstance(item, dict)] != ["customer_story", "today_youtube", "ai_news"]:
            raise ValueError("Prepared hero sources need explicit roles")
        validate_sources(prepared, str(brief.get("date") or ""))
        return copy.deepcopy(prepared)
    stories = list(brief.get("stories") or [])
    news = copy.deepcopy(stories[0]) if stories else None
    if news:
        news.setdefault("report_date", str(brief.get("date") or ""))
    customer = brief.get("customer_story") or _today_customer_story(str(brief.get("date") or ""))
    youtube = brief.get("youtube_story") or _today_youtube_story(str(brief.get("date") or ""))
    missing = [label for item, label in (
        (customer, "고객사용기 1건"), (youtube, "오늘 유튜브 1건"), (news, "AI뉴스 1건"),
    ) if not item]
    if missing:
        raise RuntimeError("인포그래픽 편성 부족: " + " · ".join(missing))
    selected = [copy.deepcopy(customer), copy.deepcopy(youtube), copy.deepcopy(news)]
    for story, role in zip(selected, ("customer_story", "today_youtube", "ai_news")):
        if story.get("hero_role", role) != role:
            raise ValueError("Hero source role mismatch")
        story["hero_role"] = role
    from .hero_validation import validate_sources
    validate_sources(selected, str(brief.get("date") or ""))
    for index, story in enumerate(selected, 1):
        story["n"] = f"{index:02d}"
    return selected


def _hero_content_and_instruction(brief, policy=None):
    """Build a fact-safe editorial anthology from three independent daily signals."""
    policy = policy or {}
    date = brief.get("date", "")
    stories = _selected_stories(brief, policy)
    mode = THREE_VIGNETTES
    roles = ("고객사용기의 한 장면", "YouTube의 한 장면", "AI뉴스의 한 장면")
    secs = []
    for i, (story, role) in enumerate(zip(stories, roles), 1):
        visual = story.get("visual_brief") or visual_brief._fallback(story)
        elements = " / ".join(visual.get("nodes") or []) or "없음"
        metrics = " / ".join(visual.get("metrics") or []) or "없음"
        constraints = " / ".join(visual.get("constraints") or []) or "없음"
        impact = " ".join(filter(None, [str(story.get("takeaway") or "").strip(),
                                         " ".join(str(v).strip() for v in
                                                  (story.get("why_bullets") or [])[:1])]))
        source_label = str(story.get("channel") or story.get("source") or "").strip()
        secs.append(f"[{i:02d}] {role} · 출처 {source_label}\n"
                    f"  제목: {story.get('headline', '')}\n"
                    f"  핵심 메시지: {visual.get('message', '')}\n"
                    f"  시각화 형식: {visual.get('layout', 'flow')}\n"
                    f"  시각화 요소: {elements}\n"
                    f"  강조 수치: {metrics}\n"
                    f"  독자 영향: {(impact or visual.get('message', ''))[:110]}\n"
                    f"  과제·위험: {constraints}")
    # 서로 무관한 세 콘텐츠를 하나의 주장으로 합성하지 않는다. 상·하단은
    # 사실을 단정하는 요약 대신 독자가 각 단편을 병렬로 읽게 하는 편집 질문이다.
    common_question = "오늘 AI의 서로 다른 현장에서는 무엇이 포착됐나?"
    remaining_question = "편리함과 통제 사이에서 무엇을 먼저 확인해야 하나?"
    source_parts = []
    for label, story in zip(("고객사용기", "YouTube", "AI뉴스"), stories):
        source_name = str(story.get("channel") or story.get("source") or "").strip()
        report_date = str(story.get("report_date") or "").strip()
        if label == "YouTube" and str(story.get("source") or "") == "최근 유튜브":
            label = "최근 YouTube"
        date_suffix = f" ({report_date})" if report_date else ""
        source_parts.append(f"{label}: {source_name}{date_suffix}")
    source_footer = " · ".join(source_parts)
    content = (f"MODE: {mode}\nTODAY_COMMON_QUESTION: {common_question}\n"
               + "".join(f"SCENE_{i}: {roles[i-1]} · {_display_headline(story.get('headline', ''))}\n"
                         for i, story in enumerate(stories, 1))
               + f"TODAY_REMAINING_QUESTION: {remaining_question}\nSOURCE_FOOTER: {source_footer}\n\n"
               + "\n\n".join(secs))
    max_text_blocks = max(4, int(policy.get("max_text_blocks") or 8))
    instruction = (
        f"'오늘의 AI 소식' 가로 16:6 표지. MODE={mode}. "
        f"상단에서 TODAY_COMMON_QUESTION을 가장 크고 먼저 읽히게 하고 전체 텍스트 블록은 {max_text_blocks}개 이하로 제한한다. "
        "고객사용기, YouTube, AI뉴스를 서로 독립된 세 단편으로 보여주는 에디토리얼 앤솔로지다. "
        "각 단편은 서로 다른 주인공과 공간을 사용해도 되며, 동일한 팔레트·선 스타일·편집 리듬으로 한 호의 잡지처럼 통일한다. "
        "단편은 여백과 장면 전환으로 구분하되 카드 UI나 동일 인물의 시간 흐름으로 만들지 않는다. "
        "절제된 현대 시사 주간지 삽화로, 세 단편 모두 동일한 얇은 잉크선과 평평한 단색 면, 같은 인체 단순화 수준을 사용한다. "
        "각 단편은 주인공 또는 대상 1개, 구체적 행동 1개, 보조 소품 최대 2개만 그린다. 제품도 사진처럼 렌더링하지 말고 같은 선화와 단색 면으로 단순화한다. "
        "도식이나 연표가 필요한 장면도 카드형 아이콘 대신 같은 스타일의 공간 삽화 하나와 상징 1~2개로 표현한다. "
        "원형 프레임, 카드 UI, 굵은 인과 화살표, 3D, 수채화, 질감, 네온, 그라디언트, 로고, 워터마크는 금지한다. "
        "지정 팔레트만 사용한다: 종이색 #F7F5EF, 본문 남색 #17233C, 기술 블루 #2E5FE0, 절제된 금색 #C9923E, 보조 회청색 #E7ECF5. "
        "본문과 출처는 #17233C로 충분한 대비를 확보하고 #2E5FE0은 핵심 주장과 중요한 소품에만 사용한다. "
        f"화면에 쓰는 문자는 공통 질문 1개, SCENE에 지정된 짧은 단편 제목 3개, 남은 질문 1개, 출처 스트립만 허용한다. 원래의 긴 기사 제목, 부제·불릿·수치 설명·내부 라벨은 이미지에 쓰지 않는다. "
        "단편 제목은 크고 굵게 최대 2줄로 쓰고, 각 단편 아래에 작은 출처를 반복하지 않는다. "
        f"하단 SOURCE_FOOTER는 전용 2줄 영역에 생략 없이 진한 본문색으로 크게 표기한다: '{source_footer}'. 출처 글자 높이는 단편 제목의 절반 이상이어야 하며 390px 폭 축소에서도 확대 없이 읽혀야 한다. "
        "그 위에 TODAY_REMAINING_QUESTION을 짧고 또렷하게 둔다. "
        "세 단편 사이에 인과관계를 만들지 않는다. 단편을 원인·해법·결과로 이름 붙이거나 화살표로 연결하지 않는다. "
        "상단의 공통 질문은 세 출처를 과장 없이 함께 바라보게 할 뿐 하나의 서사를 주장하지 않는다. "
        f"상단 워드마크 '오늘의 AI 소식', 날짜 '{date}'. 모바일 축소 가독성, 한국어, 안전 여백.")
    return content, instruction


def generate_hero(out_path, brief):
    """그날 주요 소식을 도식화한 가로 16:6 Hero 커버 PNG 생성(nlm API, method 1)."""
    from .hero_validation import invalidate_hero, write_manifest
    invalidate_hero(out_path, str(brief.get("date") or ""), "generation_started")
    enriched = copy.deepcopy(brief)
    policy = content_settings.load().get("infographics", {}).get("ai_news", {})
    selected = _selected_stories(enriched, policy)
    source_stories = copy.deepcopy(selected)
    visual_brief.enrich_stories(
        selected,
        read_originals=bool(policy.get("read_original_articles", True)),
        max_article_chars=max(1000, int(policy.get("max_article_chars") or 6000)),
    )
    enriched["cover_stories"] = selected
    content, instruction = _hero_content_and_instruction(enriched, policy)
    body = {"method": 1, "content": content, "instruction": instruction,
            "orientation": "가로", "allow_fallback": True, "format": "png"}
    print("[hero] 도식화 커버 생성 시작(가로 16:6, 브라우저 자동화, 수십 초~수 분)...", file=sys.stderr)
    try:
        data, hdr = CLIENT.generate(body, timeout=1200)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"hero HTTPError {e.code}: {e.read().decode()[:400]}")
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        raise RuntimeError("hero PNG 형식 검증 실패")
    with open(out_path, "wb") as output:
        output.write(data)
    w = h = 0
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
    print(f"[hero] OK → {out_path} ({len(data)//1024}KB) {w}x{h} "
          f"method={hdr.get('X-Infographic-Method')} "
          f"fellback={hdr.get('X-Infographic-Fellback')} "
          f"elapsed={hdr.get('X-Elapsed-Sec')}s", file=sys.stderr)
    write_manifest(out_path, brief["date"], source_stories)
    return out_path
