#!/usr/bin/env python3
"""
infographic_generator.py
주제별 인포그래픽 1페이지를 한국어로 생성합니다. (HTML → PNG)
중복 주제 카드를 먼저, 개별 주제 카드를 나중에 생성합니다.
"""

import json
import os
import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"

with open(CONFIG_DIR / "settings.json", "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)


# ─── HTML 템플릿 (인라인 CSS, 한국어 폰트) ──────────────────────────────────

HTML_TEMPLATE_COMMON = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1080">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700;900&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1080px; min-height: 1080px;
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    font-family: 'Noto Sans KR', sans-serif;
    color: #ffffff;
    padding: 60px 50px;
  }}
  .header {{
    text-align: center; margin-bottom: 48px;
  }}
  .header .badge {{
    display: inline-block;
    background: linear-gradient(90deg, #f7971e, #ffd200);
    color: #1a1a2e; font-size: 14px; font-weight: 900;
    padding: 6px 20px; border-radius: 20px; letter-spacing: 2px;
    margin-bottom: 16px;
  }}
  .header h1 {{
    font-size: 38px; font-weight: 900; line-height: 1.3;
    background: linear-gradient(90deg, #f7971e, #ffd200);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }}
  .header .date {{
    font-size: 14px; color: rgba(255,255,255,0.5); margin-top: 8px;
    letter-spacing: 1px;
  }}
  .topic-card {{
    background: rgba(255,255,255,0.07); border-radius: 20px;
    border: 1px solid rgba(255,180,0,0.3);
    padding: 32px; margin-bottom: 24px;
    transition: all 0.3s;
  }}
  .topic-card .rank {{
    font-size: 13px; font-weight: 700;
    color: #ffd200; letter-spacing: 2px; margin-bottom: 10px;
  }}
  .topic-card h2 {{
    font-size: 24px; font-weight: 700; margin-bottom: 16px;
    line-height: 1.4;
  }}
  .topic-card p {{
    font-size: 15px; line-height: 1.8; color: rgba(255,255,255,0.8);
    margin-bottom: 16px;
  }}
  .channel-badges {{
    display: flex; flex-wrap: wrap; gap: 8px;
  }}
  .channel-badge {{
    background: rgba(247,151,30,0.2); border: 1px solid rgba(247,151,30,0.4);
    border-radius: 12px; padding: 4px 14px;
    font-size: 12px; color: #ffd200; font-weight: 600;
  }}
  .stat-bar {{
    display: flex; align-items: center; gap: 12px; margin-top: 14px;
  }}
  .stat-bar .label {{
    font-size: 12px; color: rgba(255,255,255,0.5); min-width: 80px;
  }}
  .stat-bar .bar-bg {{
    flex: 1; height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px;
  }}
  .stat-bar .bar-fill {{
    height: 100%; border-radius: 3px;
    background: linear-gradient(90deg, #f7971e, #ffd200);
  }}
  .footer {{
    text-align: center; margin-top: 40px;
    font-size: 12px; color: rgba(255,255,255,0.3);
    letter-spacing: 1px;
  }}
  .summary-box {{
    background: rgba(247,151,30,0.1);
    border: 1px solid rgba(247,151,30,0.25);
    border-radius: 14px; padding: 20px 28px;
    margin-bottom: 36px; font-size: 15px;
    line-height: 1.8; color: rgba(255,255,255,0.85);
  }}
</style>
</head>
<body>
  <div class="header">
    <div class="badge">🔥 공통 AI 이슈</div>
    <h1>{title}</h1>
    <div class="date">📅 {date} · {video_count}개 영상 분석 · {channel_count}개 채널</div>
  </div>
  <div class="summary-box">
    💡 <strong>오늘의 요약:</strong> {daily_summary}
  </div>
  {topic_cards}
  <div class="footer">AI 이슈 모니터링 에이전트 · 자동 생성</div>
</body>
</html>"""

HTML_TEMPLATE_UNIQUE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=1080">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700;900&display=swap');
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: 1080px; min-height: 1080px;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    font-family: 'Noto Sans KR', sans-serif;
    color: #ffffff;
    padding: 60px 50px;
  }}
  .header {{
    text-align: center; margin-bottom: 44px;
  }}
  .header .badge {{
    display: inline-block;
    background: linear-gradient(90deg, #4facfe, #00f2fe);
    color: #1a1a2e; font-size: 14px; font-weight: 900;
    padding: 6px 20px; border-radius: 20px; letter-spacing: 2px;
    margin-bottom: 16px;
  }}
  .header h1 {{
    font-size: 36px; font-weight: 900;
    background: linear-gradient(90deg, #4facfe, #00f2fe);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  }}
  .header .date {{
    font-size: 14px; color: rgba(255,255,255,0.4); margin-top: 8px; letter-spacing: 1px;
  }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .video-card {{
    background: rgba(255,255,255,0.06); border-radius: 16px;
    border: 1px solid rgba(79,172,254,0.2);
    padding: 24px;
  }}
  .video-card .channel {{
    font-size: 12px; color: #4facfe; font-weight: 700;
    letter-spacing: 1px; margin-bottom: 10px;
  }}
  .video-card h3 {{
    font-size: 16px; font-weight: 700; line-height: 1.5;
    margin-bottom: 12px; color: #ffffff;
  }}
  .video-card p {{
    font-size: 13px; color: rgba(255,255,255,0.65); line-height: 1.7;
  }}
  .video-card .cat-badge {{
    display: inline-block; margin-top: 12px;
    background: rgba(79,172,254,0.15); border: 1px solid rgba(79,172,254,0.3);
    border-radius: 8px; padding: 3px 10px;
    font-size: 11px; color: #4facfe;
  }}
  .footer {{
    text-align: center; margin-top: 40px;
    font-size: 12px; color: rgba(255,255,255,0.3); letter-spacing: 1px;
  }}
</style>
</head>
<body>
  <div class="header">
    <div class="badge">📌 개별 AI 이슈</div>
    <h1>{title}</h1>
    <div class="date">📅 {date} · 채널별 단독 이슈</div>
  </div>
  <div class="grid">
    {video_cards}
  </div>
  <div class="footer">AI 이슈 모니터링 에이전트 · 자동 생성</div>
</body>
</html>"""


def parse_common_topics(raw_text: str) -> list[dict]:
    """NotebookLM 출력에서 공통 주제 파싱"""
    topics = []
    # 섹션으로 분할 시도 (**, ##, 번호 등)
    sections = re.split(r'\n(?=(?:\*\*|\#{1,3}|\d+\.))', raw_text.strip())
    for sec in sections[:6]:  # 최대 6개
        title_match = re.search(r'[\*#]+\s*(.+?)[\*#\n]', sec)
        title = title_match.group(1).strip() if title_match else sec[:50].strip()
        # 채널 이름 추출
        channels = re.findall(r'@[\w\-.]+', sec) or re.findall(r'채널[:\s]+([^\n,]+)', sec)
        content = re.sub(r'[\*#]+', '', sec)[:200].strip()
        if title and len(title) > 2:
            topics.append({
                "title": title,
                "content": content,
                "channels": channels[:5],
                "strength": min(len(channels) / 5, 1.0) if channels else 0.3,
            })
    return topics or [{"title": raw_text[:60], "content": raw_text[:200], "channels": [], "strength": 0.5}]


def build_common_card(topic: dict, rank: int) -> str:
    ch_badges = "".join(f'<span class="channel-badge">{ch}</span>' for ch in (topic["channels"] or ["다수 채널"]))
    fill = int(topic["strength"] * 100)
    return f"""
<div class="topic-card">
  <div class="rank">🔥 공통 주제 #{rank}</div>
  <h2>{topic['title']}</h2>
  <p>{topic['content']}</p>
  <div class="channel-badges">{ch_badges}</div>
  <div class="stat-bar">
    <span class="label">연관도</span>
    <div class="bar-bg"><div class="bar-fill" style="width:{fill}%"></div></div>
  </div>
</div>"""


def build_video_card(video: dict) -> str:
    title = video["title"][:55] + ("..." if len(video["title"]) > 55 else "")
    category = video.get("channel_category", "AI")
    transcript_note = "📝 자막 수집됨" if video.get("has_transcript") else "📌 제목 기반"
    return f"""
<div class="video-card">
  <div class="channel">{video['channel_handle']}</div>
  <h3>{title}</h3>
  <p>{transcript_note}</p>
  <span class="cat-badge">{category}</span>
</div>"""


def generate_common_infographic(analysis: dict, videos: list[dict], output_path: str) -> bool:
    """공통 주제 인포그래픽 HTML 생성"""
    today = datetime.now().strftime("%Y년 %m월 %d일")
    topics = parse_common_topics(analysis.get("common_topics_raw", ""))
    cards_html = "".join(build_common_card(t, i+1) for i, t in enumerate(topics))
    channel_count = len(set(v["channel_handle"] for v in videos))
    
    html = HTML_TEMPLATE_COMMON.format(
        title=f"오늘의 AI 핵심 이슈",
        date=today,
        video_count=len(videos),
        channel_count=channel_count,
        daily_summary=analysis.get("daily_summary", "")[:150],
        topic_cards=cards_html,
    )
    html_path = output_path.replace(".png", ".html")
    Path(html_path).write_text(html, encoding="utf-8")
    logger.info(f"✅ 공통 주제 HTML 저장: {html_path}")
    return html_to_png(html_path, output_path)


def generate_unique_infographic(videos: list[dict], output_path: str) -> bool:
    """개별 주제 인포그래픽 HTML 생성"""
    today = datetime.now().strftime("%Y년 %m월 %d일")
    cards_html = "".join(build_video_card(v) for v in videos[:12])  # 최대 12개
    
    html = HTML_TEMPLATE_UNIQUE.format(
        title="채널별 단독 AI 이슈",
        date=today,
        video_cards=cards_html,
    )
    html_path = output_path.replace(".png", ".html")
    Path(html_path).write_text(html, encoding="utf-8")
    logger.info(f"✅ 개별 주제 HTML 저장: {html_path}")
    return html_to_png(html_path, output_path)


def html_to_png(html_path: str, png_path: str) -> bool:
    """HTML → PNG 변환 (Playwright 사용)"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1080, "height": 1080})
            page.goto(f"file://{Path(html_path).absolute()}", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(2000)  # 폰트 로드 대기
            # 전체 페이지 높이로 스크린샷
            height = page.evaluate("document.documentElement.scrollHeight")
            page.set_viewport_size({"width": 1080, "height": max(height, 1080)})
            page.screenshot(path=png_path, full_page=True)
            browser.close()
        logger.info(f"🖼️ PNG 생성 완료: {png_path}")
        return True
    except Exception as e:
        logger.error(f"PNG 변환 실패: {e}")
        return False


def generate_all(analysis: dict, videos: list[dict], output_dir: str) -> list[str]:
    """공통 + 개별 인포그래픽 생성 후 경로 목록 반환"""
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = Path(output_dir) / today
    out_dir.mkdir(parents=True, exist_ok=True)
    
    generated = []
    
    # 1. 공통 주제 인포그래픽 (먼저)
    common_path = str(out_dir / "01_common_topics.png")
    if generate_common_infographic(analysis, videos, common_path):
        generated.append(common_path)
    
    # 2. 개별 주제 인포그래픽 (나중에)
    unique_path = str(out_dir / "02_unique_topics.png")
    if generate_unique_infographic(videos, unique_path):
        generated.append(unique_path)
    
    return generated


if __name__ == "__main__":
    # 테스트 실행
    test_analysis = {
        "common_topics_raw": "**GPT-5 출시** — @nateherk, @jocoding 채널에서 언급\n**AI 에이전트** — @Chase-H-AI, @ai_tusol 채널에서 언급",
        "unique_topics_raw": "개별 주제 목록",
        "daily_summary": "오늘 AI 분야 최대 이슈는 GPT-5 출시와 AI 에이전트 도구들의 급속한 발전입니다.",
    }
    test_videos = [
        {"channel_handle": "@nateherk", "title": "GPT-5: Everything You Need to Know", "has_transcript": True, "channel_category": "AI"},
        {"channel_handle": "@jocoding", "title": "GPT-5로 코딩하기 완벽 가이드", "has_transcript": True, "channel_category": "AI/Coding"},
    ]
    paths = generate_all(test_analysis, test_videos, "./output")
    print(f"생성된 파일: {paths}")
