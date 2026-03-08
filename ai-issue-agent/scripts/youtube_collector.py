#!/usr/bin/env python3
"""
youtube_collector.py
YouTube 채널 RSS 피드에서 48시간 이내 영상을 수집하고 트랜스크립트를 추출합니다.
"""

import json
import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import feedparser
import requests
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 설정 로드
BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
with open(CONFIG_DIR / "channels.json", "r", encoding="utf-8") as f:
    CHANNELS_CONFIG = json.load(f)
with open(CONFIG_DIR / "settings.json", "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)


def resolve_channel_id(handle: str) -> Optional[str]:
    """YouTube 채널 핸들 → channel_id 변환 (RSS 피드 접근용)"""
    try:
        handle_clean = handle.lstrip("@")
        url = f"https://www.youtube.com/@{handle_clean}"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AI-Issue-Monitor/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        # channelId 추출
        match = re.search(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"', resp.text)
        if match:
            return match.group(1)
        # 대안: externalId
        match = re.search(r'"externalId":"(UC[a-zA-Z0-9_-]{22})"', resp.text)
        if match:
            return match.group(1)
        logger.warning(f"채널 ID를 찾을 수 없음: {handle}")
        return None
    except Exception as e:
        logger.error(f"채널 ID 조회 실패 ({handle}): {e}")
        return None


def get_channel_rss(channel_id: str) -> list[dict]:
    """RSS 피드에서 최근 영상 목록 반환"""
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(rss_url, headers=headers, timeout=15)
        feed = feedparser.parse(resp.content)
        if feed.bozo and len(feed.entries) == 0:
            logger.warning(f"RSS 파싱 경고: {channel_id}")
        return feed.entries
    except Exception as e:
        logger.error(f"RSS 파싱 실패 ({channel_id}): {e}")
        return []


def is_within_hours(published_str: str, hours: int = 48) -> bool:
    """영상이 지정 시간 이내에 업로드되었는지 확인"""
    try:
        # YouTube RSS는 RFC 3339 형식(예: 2025-03-08T15:07:48+00:00) 반환
        clean_str = published_str.replace("Z", "+00:00")
        published_dt = datetime.fromisoformat(clean_str)
        if published_dt.tzinfo is None:
            published_dt = published_dt.replace(tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        return published_dt >= cutoff
    except Exception as e:
        logger.warning(f"날짜 파싱 오류 ({published_str}): {e}")
        return False


def extract_video_id(url: str) -> Optional[str]:
    """YouTube URL에서 video_id 추출"""
    match = re.search(r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})', url)
    return match.group(1) if match else None


def get_transcript(video_id: str, langs: list[str] = None) -> Optional[str]:
    """트랜스크립트 추출 (없으면 None)"""
    if langs is None:
        langs = ["ko", "en", "ko-KR"]
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=langs)
        text = " ".join([seg["text"] for seg in transcript])
        return text
    except TranscriptsDisabled:
        logger.warning(f"  자막 비활성화: {video_id}")
        return None
    except NoTranscriptFound:
        # 자동 생성 포함 재시도
        try:
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            for t in transcript_list:
                text = " ".join([seg["text"] for seg in t.fetch()])
                return text
        except Exception:
            pass
        logger.warning(f"  자막 없음: {video_id}")
        return None
    except Exception as e:
        logger.warning(f"  트랜스크립트 오류 ({video_id}): {e}")
        return None


def collect_all_channels(hours_back: int = 48, dry_run: bool = False) -> list[dict]:
    """모든 채널에서 최근 영상 수집"""
    collection = CHANNELS_CONFIG["collection"]
    hours = hours_back or collection["hours_back"]
    max_per_channel = collection["max_videos_per_channel"]

    today_str = datetime.now().strftime("%Y-%m-%d")
    transcript_dir = Path(SETTINGS["paths"]["transcripts_dir"]) / today_str
    transcript_dir.mkdir(parents=True, exist_ok=True)

    all_videos = []

    for ch in CHANNELS_CONFIG["channels"]:
        handle = ch["handle"]
        lang = ch["lang"]
        logger.info(f"📡 채널 수집 중: {handle}")

        channel_id = resolve_channel_id(handle)
        if not channel_id:
            continue

        entries = get_channel_rss(channel_id)
        count = 0

        for entry in entries:
            if count >= max_per_channel:
                break
            published = entry.get("published", "")
            if not is_within_hours(published, hours):
                continue

            link = entry.get("link", "")
            video_id = extract_video_id(link)
            if not video_id:
                continue

            title = entry.get("title", "제목 없음")
            logger.info(f"  🎬 [{handle}] {title[:60]}")

            transcript = None
            if not dry_run:
                # 한국어 채널은 ko 먼저, 영어 채널은 en 먼저
                lang_priority = ["ko", "en"] if lang == "ko" else ["en", "ko"]
                transcript = get_transcript(video_id, lang_priority)
                time.sleep(1)  # Rate limit 방지

            video_info = {
                "video_id": video_id,
                "title": title,
                "channel_handle": handle,
                "channel_lang": lang,
                "channel_category": ch["category"],
                "url": link,
                "published": published,
                "has_transcript": transcript is not None,
                "transcript_length": len(transcript) if transcript else 0,
                "summary_for_notebooklm": f"[{handle}] {title}\n\n{transcript[:8000] if transcript else '(자막 없음 - 제목과 채널 정보만 활용)'}",
            }

            # 트랜스크립트 파일 저장
            if transcript and not dry_run:
                safe_id = re.sub(r'[^\w]', '_', f"{handle}_{video_id}")
                (transcript_dir / f"{safe_id}.txt").write_text(
                    f"채널: {handle}\n제목: {title}\nURL: {link}\n\n{transcript}",
                    encoding="utf-8"
                )

            all_videos.append(video_info)
            count += 1

        if entries:
            time.sleep(0.5)

    logger.info(f"\n✅ 수집 완료: 총 {len(all_videos)}개 영상 (트랜스크립트 있음: {sum(1 for v in all_videos if v['has_transcript'])}개)")
    return all_videos


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="YouTube AI 이슈 수집기")
    parser.add_argument("--hours", type=int, default=48, help="수집 시간 범위 (기본: 48시간)")
    parser.add_argument("--dry-run", action="store_true", help="트랜스크립트 다운로드 없이 목록만 출력")
    parser.add_argument("--channel", type=str, help="특정 채널 핸들만 테스트 (예: @nateherk)")
    args = parser.parse_args()

    videos = collect_all_channels(hours_back=args.hours, dry_run=args.dry_run)
    print(f"\n총 {len(videos)}개 영상 수집됨:")
    for v in videos:
        status = "✅" if v["has_transcript"] else "❌"
        print(f"  {status} [{v['channel_handle']}] {v['title'][:50]}")
