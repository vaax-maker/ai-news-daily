"""Compose and send the post-publishing daily Telegram notification."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from aidaily import config
from aidaily.notifications import captions, telegram

_LOCAL_GOV_COUNT = object()
TECH_URL = config.TECH_DAILY_URL
SECTIONS = (
    ("AI뉴스", {"ai_news"}),
    ("YouTube 요약", {"youtube_summary"}),
    ("고객 사용기", {"customer_story"}),
)


def _read_json(path, default):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError,TypeError):return default


def published_articles(rows, date, override=None):
    if not isinstance(rows,list):return []
    # A prior-day exception never makes an otherwise empty current day publishable.
    if not any(row.get('date')==date and row.get('kind') in ('ai_news','youtube_summary','customer_story') and row.get('pub')!='브리프' for row in rows):return []
    use_override=(isinstance(override,dict) and override.get('enabled') is True
        and override.get('display_date')==date=='2026-10-13'
        and override.get('source_date')=='2026-10-12' and override.get('source')=='고객사용기')
    visible=[];seen=set();rooms={}
    for row in sorted(rows,key=lambda r:(str(r.get('id') or ''),json.dumps(r,sort_keys=True,ensure_ascii=False))):
        kind=row.get('kind')
        if kind not in ('ai_news','youtube_summary','customer_story') or row.get('pub')=='브리프':continue
        if kind=='youtube_summary' and row.get('pub')!='개별리포트':continue
        if row.get('date')!=date and not (use_override and kind=='customer_story' and row.get('date')=='2026-10-12'):continue
        identity=str(row.get('id')) if row.get('id') is not None else json.dumps(row,sort_keys=True,ensure_ascii=False)
        if identity in seen:continue
        seen.add(identity)
        if kind=='customer_story':
            room=str(row.get('channel') or row.get('source') or '기타 커뮤니티').strip().split(' · 오픈채팅 · ',1)[0].strip()
            import re
            room=re.sub(r'^오픈채팅\s*[·•-]?\s*','',room)
            room=re.sub(r'\s*\(비공개 대화\)\s*$','',room).strip()
            room={'18478937851255981':'AI무료 강의 & 정보 공유','18472466542857243':'김효율의 AI개발단','18446637407407327':'코난쌤 오픈채팅방','18310729609691586':'AI+스마트글래스','18475047644735325':'ai the astra'}.get(room,room)
            rooms[room]=rooms.get(room,0)+1
            if rooms[room]>4:continue
        visible.append(row)
    return visible


def government_count(date, root=None):
    """Count the same normalized edition items that the public table renders."""
    from aidaily.publishing.gov_section import load_editions
    edition = load_editions(root).get(date)
    if not edition or edition.get('status') not in ('complete', 'partial'):
        return None
    return len(edition.get('items') or [])


def verified_government_count(date):
    """Include counts only after the currently public table matches its edition."""
    try:
        from aidaily.publishing.gov_verification import verify_gov_publication
        result = verify_gov_publication(date)
        count = result.get('items')
        if (result.get('exact_edition') is True and result.get('date') == date
                and result.get('status') in ('complete', 'partial')
                and type(count) is int and count >= 0):
            return count
    except Exception as error:
        print('[notifications] government count omitted: ' + type(error).__name__)
    return None


def build_caption(brief: dict, store_path=None, override_path=None, keywords_path=None, *, republished=False, gov_root=None, gov_count=_LOCAL_GOV_COUNT) -> str:
    date=brief.get('date','')
    rows=_read_json(store_path or config.DOCS_ROOT/'search-index.json',[])
    override=_read_json(override_path or config.DATA_ROOT/'publishing/customer-date-override.json',{})
    day=published_articles(rows,date,override)
    # Modern published rows use the renderer's canonical visibility rules,
    # including normalized room aliases and the four-card display cap.
    if day and any(row.get('source') in ('AI뉴스','오늘 유튜브','고객사용기') for row in rows):
        from aidaily.publishing.editorial import _visible
        root=Path(override_path).parent if override_path else config.DATA_ROOT/'publishing'
        day=_visible(rows,date,root)
    if not day:return ''
    parts=[captions.daily_header(date, republished=republished),'']
    for label,kinds in SECTIONS:
        group=[row for row in day if row.get('kind') in kinds]
        if not group:continue
        detail=''
        if label=='YouTube 요약':detail=f" (AI·기술 {sum(row.get('cat')=='tech' for row in group)} · 경제 {sum(row.get('cat')=='econ' for row in group)})"
        if label=='고객 사용기' and any(row.get('date')!=date for row in group):detail+=' (10/12 발행 자료 포함)'
        parts.append(f'{label} {len(group)}건{detail}')
        parts.extend(f"■ {str(row.get('title') or '').strip()}" for row in group[:2] if str(row.get('title') or '').strip())
        parts.append('')
    count = government_count(date, gov_root) if gov_count is _LOCAL_GOV_COUNT else gov_count
    if type(count) is int and count >= 0:
        parts.extend([f'정부과제 {count}건', ''])
    editorial=_read_json(keywords_path or config.DATA_ROOT/'publishing/today-must-know.json',{})
    by_id={str(row.get('id')):row for row in day}
    if isinstance(editorial,dict) and editorial.get('date')==date:
        keywords=[]
        for item in editorial.get('items',[])[:3]:
            row=by_id.get(str(item.get('id')));quote=item.get('quote');keyword=item.get('keyword')
            if row and isinstance(quote,str) and quote and quote in (row.get('summary_bullets') or []) and isinstance(keyword,str) and keyword.strip():
                keywords.append(f"■ {keyword.strip()}: “{quote}”")
        if keywords:parts+=['오늘의 키워드',*keywords,'']
    parts.append(f'▸ {TECH_URL}?date={date}')
    return '\n'.join(parts)


def load_credentials(path: str | Path | None = None) -> tuple[str, str]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        return token, chat_id
    credential_path = Path(path or os.environ.get(
        "TELEGRAM_CREDENTIALS_FILE", "~/nlm-infographic/deploy/.tg-creds.json"
    )).expanduser()
    try:
        values = json.loads(credential_path.read_text(encoding="utf-8"))
        default = values.get("default") or {}
        return (
            token or str(values.get("token") or default.get("bot_token") or ""),
            chat_id or str(values.get("chat_id") or default.get("chat_id") or ""),
        )
    except (OSError, ValueError, TypeError):
        return token, chat_id


def send_once(date, caption, token, chat_id, receipt_dir=None):
    """Reserve the date before sending; ambiguous outcomes require manual review."""
    captions.validate_daily_header(caption)
    import hashlib
    import fcntl
    directory=Path(receipt_dir or config.DATA_ROOT/'notifications/daily_digest')
    directory.mkdir(parents=True,exist_ok=True)
    path=directory/f'{date}.json'
    with (directory/f'{date}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if path.exists():return {'status':'skipped_existing_receipt'}
        receipt={'date':date,'status':'sending','caption_sha256':hashlib.sha256(caption.encode()).hexdigest()}
        def save():
            temporary=path.with_suffix('.json.new')
            with temporary.open('w') as stream:
                json.dump(receipt,stream);stream.flush();os.fsync(stream.fileno())
            temporary.replace(path)
        save()
        try:
            result=telegram.send_photo('',caption,token,chat_id)
            receipt.update(status='sent',message_id=(result.get('result') or {}).get('message_id'))
            save()
            return receipt
        except Exception as error:
            receipt.update(status='uncertain',error_type=type(error).__name__)
            save()
            raise


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--brief',default=str(config.DOCS_ROOT/'archive/index.json'))
    parser.add_argument('--image',default=str(config.DOCS_ROOT/'hero.png'),help='Compatibility argument; daily announcements are text only')
    parser.add_argument('--store',default=str(config.DOCS_ROOT/'search-index.json'))
    parser.add_argument('--credentials',default=None)
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--receipt-dir',default=None)
    args=parser.parse_args()
    from datetime import datetime
    from zoneinfo import ZoneInfo
    today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    caption=build_caption({'date':today},args.store,gov_count=verified_government_count(today))
    if not caption:
        print('[notifications] skipped: no published articles for today')
        return
    if args.dry_run:
        print(caption)
        return
    token,chat_id=load_credentials(args.credentials)
    if not token or not chat_id:raise ValueError('Telegram credentials required')
    result=send_once(today,caption,token,chat_id,args.receipt_dir)
    print('[notifications] '+result['status'])


if __name__=='__main__':main()
