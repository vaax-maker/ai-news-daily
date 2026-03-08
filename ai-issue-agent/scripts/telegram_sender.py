#!/usr/bin/env python3
"""
telegram_sender.py
생성된 인포그래픽 PNG를 Telegram Bot으로 자동 발송합니다.
"""

import os
import logging
import asyncio
from pathlib import Path
from datetime import datetime

import telegram
from telegram import Bot
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def get_bot() -> Bot:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN 환경변수가 설정되지 않았습니다.")
    return Bot(token=token)


def get_chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID 환경변수가 설정되지 않았습니다.")
    return chat_id


async def send_infographics_async(png_paths: list[str], analysis: dict, videos: list[dict]):
    """인포그래픽 PNG를 Telegram으로 발송"""
    bot = get_bot()
    chat_id = get_chat_id()
    today = datetime.now().strftime("%Y년 %m월 %d일")
    
    # 헤더 메시지
    header_msg = (
        f"🤖 *AI 이슈 데일리 리포트*\n"
        f"📅 {today}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📊 분석 영상: {analysis.get('video_count', 0)}개\n"
        f"✅ 자막 수집: {analysis.get('has_transcript_count', 0)}개\n"
        f"📡 채널 수: {len(set(v['channel_handle'] for v in videos))}개\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"💡 {analysis.get('daily_summary', '')[:200]}"
    )
    
    await bot.send_message(
        chat_id=chat_id,
        text=header_msg,
        parse_mode=ParseMode.MARKDOWN,
    )
    logger.info("✅ 헤더 메시지 발송 완료")
    
    # 인포그래픽 PNG 발송
    for i, png_path in enumerate(png_paths):
        if not Path(png_path).exists():
            logger.warning(f"PNG 파일 없음: {png_path}")
            continue
        
        caption_map = {
            "01_common": "🔥 *공통 AI 이슈* — 여러 채널이 다룬 주제",
            "02_unique": "📌 *개별 AI 이슈* — 채널별 단독 이슈",
        }
        caption = next((v for k, v in caption_map.items() if k in Path(png_path).name), f"AI 이슈 #{i+1}")
        
        with open(png_path, "rb") as f:
            await bot.send_photo(
                chat_id=chat_id,
                photo=f,
                caption=caption,
                parse_mode=ParseMode.MARKDOWN,
            )
        logger.info(f"✅ PNG 발송: {Path(png_path).name}")
        await asyncio.sleep(1)  # Rate limit 방지
    
    # 영상 링크 목록 발송
    video_links = "\n".join(
        f"• [{v['channel_handle']}] [{v['title'][:40]}]({v['url']})"
        for v in videos[:10]
    )
    if video_links:
        await bot.send_message(
            chat_id=chat_id,
            text=f"📺 *오늘의 수집 영상 목록*\n\n{video_links}",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
    
    logger.info("🎉 Telegram 발송 완료!")


def send_infographics(png_paths: list[str], analysis: dict, videos: list[dict]):
    """동기 래퍼"""
    asyncio.run(send_infographics_async(png_paths, analysis, videos))


async def send_error_notification_async(error_msg: str):
    """에러 발생 시 Telegram 알림"""
    try:
        bot = get_bot()
        chat_id = get_chat_id()
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ *AI 이슈 에이전트 오류*\n📅 {today}\n\n```\n{error_msg[:1000]}\n```",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        logger.error(f"에러 알림 발송 실패: {e}")


def send_error_notification(error_msg: str):
    asyncio.run(send_error_notification_async(error_msg))


if __name__ == "__main__":
    # 테스트 발송
    import sys
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        test_analysis = {"video_count": 5, "has_transcript_count": 4, "daily_summary": "테스트 발송입니다."}
        test_videos = [{"channel_handle": "@test", "title": "테스트 영상", "url": "https://youtube.com"}]
        send_infographics([test_path], test_analysis, test_videos)
    else:
        print("사용법: python telegram_sender.py <png_path>")
