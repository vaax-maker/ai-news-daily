#!/usr/bin/env python3
"""
topic_analyzer.py
NotebookLM 스킬을 활용하여 수집된 영상들의 주제를 분석합니다.
중복 주제(여러 채널 언급)와 개별 주제를 분류합니다.
"""

import json
import os
import subprocess
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
SKILLS_DIR = Path.home() / ".agents" / "skills" / "notebooklm"

with open(CONFIG_DIR / "settings.json", "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)

QUERIES = SETTINGS["notebooklm"]["queries"]


def run_notebooklm_script(script_name: str, args: list[str]) -> str:
    """NotebookLM 스킬 스크립트 실행"""
    run_py = SKILLS_DIR / "scripts" / "run.py"
    if not run_py.exists():
        raise FileNotFoundError(f"NotebookLM 스킬을 찾을 수 없습니다: {run_py}")
    cmd = ["python", str(run_py), script_name] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILLS_DIR))
    if result.returncode != 0:
        logger.warning(f"스크립트 오류: {result.stderr[:300]}")
    return result.stdout.strip()


def ensure_notebook_exists(notebook_name: str) -> str:
    """오늘 날짜용 노트북이 없으면 생성 (존재하면 재사용)"""
    today = datetime.now().strftime("%Y-%m-%d")
    nb_name = f"{notebook_name}_{today}"
    
    # 기존 노트북 목록 확인
    output = run_notebooklm_script("notebook_manager.py", ["list"])
    
    # 노트북 ID 파싱 시도
    for line in output.splitlines():
        if nb_name in line:
            # ID 추출
            import re
            match = re.search(r'id[:\s]+([a-zA-Z0-9_-]+)', line)
            if match:
                logger.info(f"기존 노트북 사용: {nb_name}")
                return match.group(1)
    
    logger.info(f"새 노트북 생성: {nb_name}")
    return nb_name  # URL 기반으로 추가할 노트북 이름 반환


def add_videos_to_notebooklm(videos: list[dict]) -> str:
    """수집된 영상 내용을 NotebookLM에 추가"""
    today = datetime.now().strftime("%Y-%m-%d")
    nb_name = f"{SETTINGS['notebooklm']['notebook_name']}_{today}"
    
    # 트랜스크립트를 임시 텍스트로 합쳐 질의용으로 준비
    combined_text = f"# AI 이슈 수집 ({today})\n\n"
    for v in videos:
        combined_text += f"## [{v['channel_handle']}] {v['title']}\n"
        combined_text += f"URL: {v['url']}\n"
        if v.get("has_transcript"):
            text = v.get("summary_for_notebooklm", "")
            combined_text += f"{text[:3000]}\n\n"
        else:
            combined_text += "(자막 없음)\n\n"
    
    # 임시 파일로 저장
    tmp_file = Path(f"/tmp/ai-issue-agent-{today}.txt")
    tmp_file.write_text(combined_text, encoding="utf-8")
    logger.info(f"📝 통합 콘텐츠 파일 생성: {tmp_file} ({len(combined_text):,}자)")
    return str(tmp_file), nb_name, combined_text


def ask_notebooklm(question: str, notebook_url: str = None) -> str:
    """NotebookLM에 질문하고 답변 반환"""
    args = ["--question", question]
    if notebook_url:
        args += ["--notebook-url", notebook_url]
    
    logger.info(f"🔍 NotebookLM 질의: {question[:80]}...")
    output = run_notebooklm_script("ask_question.py", args)
    logger.info(f"✅ 답변 수신 ({len(output)}자)")
    return output


def analyze_topics_with_ai(videos: list[dict]) -> dict:
    """
    AI 기반 주제 분석 (NotebookLM 사용)
    NotebookLM 없을 시 로컬 키워드 분석으로 폴백
    """
    try:
        tmp_file, nb_name, combined_text = add_videos_to_notebooklm(videos)
        
        # NotebookLM 스킬 존재 확인
        if not (SKILLS_DIR / "scripts" / "run.py").exists():
            raise FileNotFoundError("NotebookLM 스킬 없음")
        
        # 중복 주제 질의
        common_answer = ask_notebooklm(QUERIES["common_topics"])
        # 개별 주제 질의
        unique_answer = ask_notebooklm(QUERIES["unique_topics"])
        # 전체 요약 질의
        summary_answer = ask_notebooklm(QUERIES["daily_summary"])
        
        return {
            "method": "notebooklm",
            "common_topics_raw": common_answer,
            "unique_topics_raw": unique_answer,
            "daily_summary": summary_answer,
            "video_count": len(videos),
            "has_transcript_count": sum(1 for v in videos if v.get("has_transcript")),
        }
        
    except Exception as e:
        logger.warning(f"NotebookLM 오류 ({e}), 로컬 분석으로 폴백")
        return analyze_topics_local(videos)


def analyze_topics_local(videos: list[dict]) -> dict:
    """
    로컬 키워드 기반 주제 분석 (NotebookLM 폴백)
    채널별 제목에서 공통 키워드를 추출하여 중복/개별 주제 분류
    """
    import re
    from collections import Counter
    
    ai_keywords = [
        "GPT", "Claude", "Gemini", "LLM", "AI", "에이전트", "agent", "모델", "model",
        "ChatGPT", "OpenAI", "Anthropic", "Google", "Sora", "Grok", "DeepSeek",
        "프롬프트", "prompt", "RAG", "자동화", "automation", "코딩", "coding"
    ]
    
    # 채널별 키워드 수집
    channel_keywords = {}
    for v in videos:
        ch = v["channel_handle"]
        title = v["title"].upper()
        found = [kw for kw in ai_keywords if kw.upper() in title]
        if ch not in channel_keywords:
            channel_keywords[ch] = set()
        channel_keywords[ch].update(found)
    
    # 2개+ 채널に서 언급된 키워드 = 중복 주제
    all_kw = []
    for kws in channel_keywords.values():
        all_kw.extend(kws)
    kw_count = Counter(all_kw)
    common = {kw: cnt for kw, cnt in kw_count.items() if cnt >= 2}
    
    # 중복 주제 텍스트 구성
    common_text = "### 🔥 공통 주제 (여러 채널 언급)\n\n"
    if common:
        for kw, cnt in sorted(common.items(), key=lambda x: -x[1]):
            channels_with_kw = [ch for ch, kws in channel_keywords.items() if kw in kws]
            common_text += f"**{kw}** — {cnt}개 채널 ({', '.join(channels_with_kw)})\n"
    else:
        common_text += "오늘 공통으로 다룬 주제 없음\n"
    
    # 개별 주제 텍스트 구성
    unique_text = "### 📌 개별 주제\n\n"
    for v in videos:
        unique_text += f"- **[{v['channel_handle']}]** {v['title']}\n"
    
    return {
        "method": "local_keyword",
        "common_topics_raw": common_text,
        "unique_topics_raw": unique_text,
        "daily_summary": f"총 {len(videos)}개 영상 분석 완료 (로컬 키워드 분석)",
        "video_count": len(videos),
        "has_transcript_count": sum(1 for v in videos if v.get("has_transcript")),
    }


if __name__ == "__main__":
    # 테스트 실행
    test_videos = [
        {"channel_handle": "@nateherk", "title": "GPT-5 Released!", "url": "https://youtu.be/test1", "has_transcript": True, "summary_for_notebooklm": "GPT-5 출시 영상"},
        {"channel_handle": "@jocoding", "title": "GPT-5로 코딩하기", "url": "https://youtu.be/test2", "has_transcript": True, "summary_for_notebooklm": "GPT-5 코딩 활용"},
        {"channel_handle": "@ai_tusol", "title": "Claude 3.7 리뷰", "url": "https://youtu.be/test3", "has_transcript": False, "summary_for_notebooklm": ""},
    ]
    result = analyze_topics_with_ai(test_videos)
    print(json.dumps(result, ensure_ascii=False, indent=2))
