#!/usr/bin/env python3
"""
run_agent.py
AI 이슈 모니터링 에이전트 메인 오케스트레이터
[리서치 에이전트] → [종합편성 에이전트] → [Telegram 발송]
"""

import json
import logging
import sys
import traceback
from pathlib import Path
from datetime import datetime

# 경로 설정
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from youtube_collector import collect_all_channels
from topic_analyzer import analyze_topics_with_ai
from infographic_generator import generate_all
from telegram_sender import send_infographics, send_error_notification

OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(OUTPUT_DIR / "agent.log", mode='a', encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

with open(BASE_DIR / "config" / "settings.json", "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)


def run(hours_back: int = 48, dry_run: bool = False, skip_telegram: bool = False):
    today = datetime.now().strftime("%Y-%m-%d")
    start_time = datetime.now()
    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 AI 이슈 모니터링 에이전트 시작 [{today}]")
    logger.info(f"{'='*60}")

    try:
        # ─── Phase 1: 리서치 에이전트 ────────────────────────────
        logger.info("\n📡 [리서치 에이전트] YouTube 영상 수집 시작...")
        videos = collect_all_channels(hours_back=hours_back, dry_run=dry_run)

        if not videos:
            logger.warning("⚠️ 수집된 영상이 없습니다. 종료합니다.")
            if not skip_telegram:
                send_error_notification("48시간 이내 수집된 영상이 없습니다.")
            return False

        logger.info(f"✅ {len(videos)}개 영상 수집 완료")

        # 영상 목록 저장
        output_dir = Path(SETTINGS["paths"]["output_dir"]) / today
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "videos.json").write_text(
            json.dumps(videos, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # ─── Phase 2: 종합편성 에이전트 (주제 분석) ──────────────
        logger.info("\n🔍 [종합편성 에이전트] 주제 분석 시작...")
        analysis = analyze_topics_with_ai(videos)
        logger.info(f"✅ 주제 분석 완료 (방법: {analysis.get('method', 'unknown')})")

        # 분석 결과 저장
        (output_dir / "analysis.json").write_text(
            json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (output_dir / "report.md").write_text(
            f"# AI 이슈 리포트 ({today})\n\n"
            f"## 오늘의 요약\n{analysis.get('daily_summary', '')}\n\n"
            f"## 공통 주제\n{analysis.get('common_topics_raw', '')}\n\n"
            f"## 개별 주제\n{analysis.get('unique_topics_raw', '')}\n",
            encoding="utf-8"
        )

        # ─── Phase 3: 인포그래픽 생성 ────────────────────────────
        logger.info("\n🎨 인포그래픽 생성 중...")
        if not dry_run:
            png_paths = generate_all(analysis, videos, str(BASE_DIR / "output"))
            logger.info(f"✅ {len(png_paths)}개 인포그래픽 생성 완료")
        else:
            png_paths = []
            logger.info("ℹ️ dry-run 모드: 인포그래픽 생성 스킵")

        # ─── Phase 4: Telegram 발송 ───────────────────────────────
        if not skip_telegram and not dry_run and png_paths:
            logger.info("\n📲 Telegram 발송 중...")
            send_infographics(png_paths, analysis, videos)

        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(f"\n🎉 완료! 총 소요시간: {elapsed:.1f}초")
        logger.info(f"📁 결과물: {output_dir}")
        return True

    except Exception as e:
        error_msg = f"에이전트 실행 오류:\n{traceback.format_exc()}"
        logger.error(error_msg)
        if not skip_telegram and not dry_run:
            try:
                send_error_notification(error_msg[:1000])
            except Exception:
                pass
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI 이슈 모니터링 에이전트")
    parser.add_argument("--hours", type=int, default=48, help="수집 범위 (기본: 48시간)")
    parser.add_argument("--dry-run", action="store_true", help="테스트 모드 (실제 저장/발송 없음)")
    parser.add_argument("--no-telegram", action="store_true", help="Telegram 발송 스킵")
    args = parser.parse_args()

    success = run(
        hours_back=args.hours,
        dry_run=args.dry_run,
        skip_telegram=args.no_telegram,
    )
    sys.exit(0 if success else 1)
