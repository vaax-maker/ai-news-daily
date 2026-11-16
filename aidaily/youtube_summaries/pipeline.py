#!/usr/bin/env python3
"""Generate YouTube Summaries through shared integrations and OpenRouter.

⚠️ 기본 동작은 STAGING ONLY — origin push·라이브 큐/LOG 수정·텔레그램 발송·vault 수정 없음.
산출은 전부 --staging-dir(기본 /tmp/youtube-summaries-staging)에만 쓴다.
--publish 플래그를 줘야만 실발행(클론→push→LOG갱신)을 시도한다(아래 CLI 참조).

사용:
  python3 -m aidaily.youtube_summaries.pipeline --url "<youtube url>"          # 단일영상 E2E 검증(스테이징만)
  python3 -m aidaily.youtube_summaries.pipeline --url "..." --title "..." --channel "..."  # 슬러그·메타 보강
  python3 -m aidaily.youtube_summaries.pipeline --limit 5                       # config 채널 최근영상 순회(스테이징만)
  python3 -m aidaily.youtube_summaries.pipeline --url "..." --staging-dir /tmp/x
  python3 -m aidaily.youtube_summaries.pipeline --limit 3 --publish --dry-push  # 컷오버 전 검증(push --dry-run, LOG 미기록)
  python3 -m aidaily.youtube_summaries.pipeline --limit 10 --publish            # 실컷오버(클론→push→LOG갱신)
"""
import argparse
import hashlib
import fcntl

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from aidaily import config
from aidaily.integrations import openrouter
from aidaily.integrations.youtube_transcript import transcript_chars, minimum_transcript_chars
from aidaily.integrations.youtube import duration_seconds, fetch_channel, video_metadata, fetch_channel_video_page
from aidaily.publishing.youtube_summaries import publish
from aidaily.youtube_summaries import analyzer, selection

CONFIG_PATH = str(Path(os.environ.get(
    "YOUTUBE_SUMMARIES_CONFIG", str(config.LEGACY_YOUTUBE_CONFIG)
)).expanduser())
DEFAULT_STAGING = str(config.DATA_ROOT / "youtube_summaries" / "staging" / time.strftime("%Y-%m-%d"))
QUEUE_NAME = config.LEGACY_YOUTUBE_QUEUE

CAT_MAP = {"economy": "econ"}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config():
    """Load channel, collection-window, and minimum-duration policy."""
    try:
        return json.load(open(CONFIG_PATH, encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        log(f"config 로드 실패({e}) — 폴백 없이 빈 채널 목록")
        return {}


def load_processed_ids():
    """Read the same local durable history that publication updates."""
    from aidaily.youtube_summaries.processed_state import load_processed_ids as load_local
    return load_local()


def list_channel_videos(channel_id, hours, min_duration, title_include, *, xr_only=False, cache=None, rss_fallback=False):
    """채널 최근 영상(RSS `<published>` 기준 정확한 수집창 필터) → 최소길이·제목필터 통과분만.
    RSS는 레이트리밋이 없어 429 폴백이 불필요 — 길이 확인(yt-dlp)만 영상별로 수행한다."""
    try:
        if cache is not None and channel_id in cache:entries=cache[channel_id]
        else:
            try:
                entries=fetch_channel(channel_id)
            except Exception as exc:
                if not rss_fallback: raise
                log(f"  [{channel_id}] RSS unavailable ({type(exc).__name__}); bounded XR video-page lookup")
                entries=fetch_channel_video_page(channel_id)
            if cache is not None:cache[channel_id]=entries
    except Exception as e:  # noqa: BLE001
        log(f"  [{channel_id}] RSS 조회 실패: {type(e).__name__}: {e}")
        return []
    now = datetime.now(timezone.utc)
    kws = [k.strip().lower() for k in (title_include or []) if k.strip()]
    out = []
    for v in entries:
        vid, title = v["video_id"], v["title"]
        if (now - v["published"]).total_seconds() > hours * 3600:
            continue  # 수집창(hours) 밖 — RSS는 최신순이라 이후로도 계속 밖이지만 안전하게 전건 검사
        if any(kw in title.lower() for kw in ("#shorts", "#short", "#쇼츠")):
            continue
        if kws and not any(kw in title.lower() for kw in kws):
            continue
        if xr_only and not selection.is_xr(v):
            continue
        try:
            dur = v.get("duration") if v.get("duration") is not None else duration_seconds(vid)
        except Exception as exc:
            log(f"  [{vid}] 길이 조회 오류 — 이번 영상 보류: {type(exc).__name__}")
            continue
        if dur is None:
            log(f"  [{vid}] 길이 조회 실패 — 안전하게 제외(숏폼 간주)")
            continue
        if dur < min_duration:
            continue
        out.append({"video_id": vid, "title": title,
                     "published_at":v["published"].isoformat(),
                     "url": f"https://youtu.be/{vid}"})
    return out


def collect_targets(cfg, processed, limit):
    """Reserve XR from normal window, then up to 14 days if necessary."""
    if limit<=0:return []
    hours=int(cfg.get('hours') or 48);min_duration=max(300,int(cfg.get('min_duration') or 300))
    channels=[x for x in cfg.get('channels',[]) if x.get('channel_id')]
    # Search all configured channels, not merely those encountered before the cap.
    cache={};xr=[];xr_ids=set()
    normal_xr_hours=min(hours,14*24)
    windows=(normal_xr_hours,14*24) if normal_xr_hours<14*24 else (normal_xr_hours,)
    for window in windows:
        for ch in channels:
            for v in list_channel_videos(ch['channel_id'],window,min_duration,ch.get('title_include'),xr_only=True,cache=cache,rss_fallback=ch.get('field')=='XR'):
                if v['video_id'] not in processed and v['video_id'] not in xr_ids:
                    xr.append({**v,'channel':ch.get('handle',''),'channel_id':ch['channel_id'],'category':ch.get('category','tech')})
                    xr_ids.add(v['video_id'])
                    if len(xr)>=3:break
            if len(xr)>=3:break
        if len(xr)>=3:break
    # Channels marked "required" by the user are always attempted: every eligible
    # new video is collected and none of them counts toward the ordinary cap.
    required=[]
    for ch in channels:
        if not ch.get('required'):continue
        for v in list_channel_videos(ch['channel_id'],hours,min_duration,ch.get('title_include'),cache=cache):
            if v['video_id'] not in processed and v['video_id'] not in xr_ids:
                required.append({**v,'channel':ch.get('handle',''),'channel_id':ch['channel_id'],'category':ch.get('category','tech'),'_required':True})
    ordinary=[]
    for ch in channels:
        if ch.get('required'):continue
        for v in list_channel_videos(ch['channel_id'],hours,min_duration,ch.get('title_include'),cache=cache):
            if v['video_id'] not in processed and v['video_id'] not in xr_ids:
                # XR candidates are handled exclusively by the bounded
                # three-candidate path above, never smuggled in as ordinary.
                if selection.is_xr(v):continue
                ordinary.append({**v,'channel':ch.get('handle',''),'channel_id':ch['channel_id'],'category':ch.get('category','tech')})
                if len(ordinary)>=limit:break
        if len(ordinary)>=limit:break
    if not xr:return required+selection.prioritize(ordinary,limit)
    # Alternative candidates are attempted only if earlier XR processing failed.
    return required+[xr[0]]+[{**v,'_xr_alternate':True} for v in xr[1:]]+selection.prioritize(ordinary,limit-1)


def _slugify(text, max_len=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].strip("-") or "video"


def channel_slug(handle, channel_id=""):
    """채널 slug 부분 — handle을 romanize하지 않는다. handle의 **영문 토큰만** 뽑아 쓰되
    (예: '조코딩 JoCoding' → 'jocoding'), 4자 미만이면(예: '티타임즈TV' → 'tv') 채널 식별력이
    없다고 보고 channel_id 앞 8자로 대체한다. channel_id도 없으면(예: --url에 --channel-id
    누락) 짧은 영문 토큰이라도 최후 수단으로 쓰되, 그마저 없으면 'ch'."""
    tokens = re.findall(r"[A-Za-z0-9]+", handle or "")
    joined = "".join(tokens).lower()
    if len(joined) >= 4:
        return joined[:20]
    if channel_id:
        return re.sub(r"[^a-z0-9]", "", channel_id.lower())[:8] or "ch"
    return joined or (_slugify(handle) if handle else "ch")


def build_markdown(analysis, title):
    lines = [f"# {title}", "", f"> {analysis.get('card_summary', '')}", ""]
    scope=analysis.get('source_analysis')
    if scope:
        lines += [f"> 분석 범위: 원문 전체 {scope['source_characters']:,}자 · {len(scope['chunks'])}개 구간. 원문 대조한 핵심 인용 {scope['selected_quote_count']}개를 바탕으로 요약했습니다.", "> 분석 기준: 영상 발화자의 견해·경험을 원문에 근거해 정리한 요약입니다.", ""]
    if analysis.get('report_schema') != 'story_topics_v2':
        # Preserve historical report rendering; new reports contain only the
        # source-derived topics followed by their sequential glossary.
        lines += ["## 핵심 개요", ""]
        lines += [f"- {b}" for b in analysis.get("overview", [])]
    for section in analysis.get("sections", []):
        lines += ["", f"## {section['title']}", ""]
        lines += [f"- {bullet}" for bullet in section.get("bullets", [])]
    lines += ["", "## 용어 사전", "", "| 용어 | 뜻 |", "|---|---|"]
    for row in analysis.get("glossary", []):
        term = str(row.get("term") or "").replace("|", "／")
        definition = str(row.get("definition") or "").replace("|", "／")
        lines.append(f"| {term} | {definition} |")
    return "\n".join(lines) + "\n"


def render_report(md_path, out_path, date, channel, video_url, category, *, hide_section_numbers=False):
    cat = CAT_MAP.get(category, category if category in ("tech", "econ", "hub") else "tech")
    renderer_path = Path(__file__).with_name("renderer.py")
    cmd = [sys.executable, str(renderer_path),
           "--in", md_path, "--out", out_path,
           "--eyebrow", f"YOUTUBE SUMMARIES · {date} · {channel}", "--badge", "🎬 영상",
           "--brand", channel, "--footer", f"{channel} · {date}",
           "--video-url", video_url, "--category", cat]
    if hide_section_numbers:
        cmd.append('--hide-section-numbers')
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"YouTube renderer failed: {r.stderr[:300]}")
    return r.stdout.strip()


def _bullet_msg(v, analysis, date):
    """텔레그램 큐 text 필드 — ig_backfill_daily._bullets()가 '- '로 시작하는 줄만 파싱하므로
    그 계약을 그대로 따른다. '—' 금지(쉼표로), 불릿 사이 빈 줄."""
    head = f"[AI 비주얼 리포트] {date}\n[{v['channel']}] {v['title']}"
    bullets = analysis.get("body_bullets", [])[:4]
    bl = "\n\n".join(f"- {b.replace(' — ', ', ').replace('—', ', ')}" for b in bullets)
    return f"{head}\n\n{bl}"


def build_slug(v, analysis, date):
    """slug = {date}-{채널slug}-{slug_hint}. 채널 부분은 handle을 romanize하지 않고
    영문 토큰만 뽑아 쓰거나(channel_slug) channel_id로 대체 — 한글 채널명이 뭉개지지 않는다.
    주제 부분은 LLM이 낸 영문 slug_hint(analyze() 산출) — 한글 제목이어도 영문 slug가 나온다.
    slug_hint가 비정상적으로 짧으면(LLM 실패 등) video_id로 유일성을 보강한다."""
    ch_part = channel_slug(v.get("channel", ""), v.get("channel_id", ""))
    hint = analysis.get("slug_hint") or ""
    if len(hint) < 4:
        hint = f"{hint}-{v['video_id'].lower()}" if hint else v["video_id"].lower()
    return f"{date}-{ch_part}-{hint}"


def frozen_input(v):
    # This survives per-run staging folders and a new process on retry.
    checkpoints=Path(os.environ.get('AIDAILY_YOUTUBE_CHECKPOINTS',str(config.DATA_ROOT/'youtube_input_checkpoints'))).expanduser()
    checkpoints.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=hashlib.sha256(str(v['video_id']).encode()).hexdigest()
    checkpoint=checkpoints/(key+'.json')
    with (checkpoints/(key+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if checkpoint.exists():saved=json.loads(checkpoint.read_text())
        else:
            context={key:v[key] for key in ('title','channel') if v.get(key)}
            transcript=analyzer.fetch_transcript(v['url'], **context)
            if not isinstance(transcript,str) or transcript_chars(transcript)<minimum_transcript_chars():raise RuntimeError('수집 자막이 불완전합니다. 입력을 확정하지 않았습니다.')
            saved={'video':dict(v),'transcript':transcript,'input_sha256':hashlib.sha256(transcript.encode()).hexdigest()}
            temporary=checkpoint.with_name(checkpoint.name+'.new')
            with temporary.open('w') as stream:
                temporary.chmod(0o600);json.dump(saved,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
            os.replace(temporary,checkpoint)
        transcript=saved['transcript']
        if not isinstance(transcript, str) or transcript_chars(transcript) < minimum_transcript_chars():
            raise RuntimeError('저장된 자막이 현재 최소량 기준 미달입니다. 원본을 보존하고 검토합니다.')
        if saved['video']['video_id']!=v['video_id'] or hashlib.sha256(transcript.encode()).hexdigest()!=saved['input_sha256']:
            raise RuntimeError('저장된 자막 입력 검증 실패')
        return saved['video'],transcript


def write_analyzed_report(v, analysis, staging_dir, date, *, slug=None):
    """Render validated analysis, optionally preserving an existing publication URL."""
    slug = slug or build_slug(v, analysis, date)  # Preserve published URLs during explicit revisions.
    log(f"  [{slug}] 슬러그 확정 — 렌더 중...")

    md_path = os.path.join(staging_dir, f"{slug}.md")
    out_path = os.path.join(staging_dir, f"{slug}.html")
    with open(md_path, "w", encoding="utf-8") as markdown_file:
        markdown_file.write(build_markdown(analysis, analysis.get("headline") or v["title"]))
    render_report(md_path, out_path, date, v["channel"], v["url"], analysis["category"],
                  hide_section_numbers=analysis.get('report_schema') == 'story_topics_v2')
    # Exact source metadata is separate from the generated headline, for future images.
    import html
    report_path = Path(out_path)
    report = report_path.read_text(encoding="utf-8")
    metadata = ('<meta name="youtube-source-title" content="' + html.escape(str(v.get("title") or ""), quote=True) + '">'
                + '<meta name="youtube-source-channel" content="' + html.escape(str(v.get("channel") or ""), quote=True) + '">')
    if analysis.get('report_schema') == 'story_topics_v2':
        metadata += ('<meta name="youtube-report-schema" content="story_topics_v2">'
                     + '<meta name="youtube-heading-numbering" content="none">'
                     + '<meta name="youtube-summary-bullets" content="'
                     + html.escape(json.dumps(analysis.get('body_bullets', []), ensure_ascii=False), quote=True) + '">')
    if re.search(r'</head>', report, re.I):
        report = re.sub(r'</head>', lambda match: metadata + match.group(), report, count=1, flags=re.I)
    else:
        report = metadata + report
    report_path.write_text(report, encoding="utf-8")
    log(f"  [{slug}] 리포트 렌더 완료 → {out_path}")

    return slug, {"text": _bullet_msg(v, analysis, date), "category": v.get("category", "tech")}


def process_video(v, staging_dir, date):
    """Freeze source → analyze → render. Pending work cannot advance to publishing."""
    log(f"  [{v.get('title') or v['video_id']}] 저장된 입력 확인 중...")
    v,transcript=frozen_input(v)
    log(f"  자막 {len(transcript)}자 — OpenRouter 분석 중...")
    analysis = analyzer.analyze(transcript, v["title"], v["channel"])

    return write_analyzed_report(v, analysis, staging_dir, date)


def _channel_id_for_handle(cfg, handle):
    """--url 경로에서 --channel이 config의 handle과 일치하면 channel_id를 같이 채워
    channel_slug()가 짧은 영문 토큰(예: '티타임즈TV'→'tv')일 때도 channel_id 폴백을 쓸 수 있게 한다."""
    for ch in (cfg or {}).get("channels", []):
        if ch.get("handle") == handle:
            return ch.get("channel_id", "")
    return ""


def run(urls, staging_dir, limit, title="", channel=""):
    Path(staging_dir).mkdir(parents=True, exist_ok=True)
    with (Path(staging_dir) / "run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _run(urls, staging_dir, limit, title, channel)


def _run(urls, staging_dir, limit, title="", channel=""):
    os.makedirs(staging_dir, exist_ok=True)
    date = time.strftime("%Y-%m-%d")
    processed = load_processed_ids()
    failures = []
    blocked_ids = set()

    if urls:
        cfg = load_config()
        cid = _channel_id_for_handle(cfg, channel) if channel else ""
        targets = []
        for u in urls:
            vid_m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", u) or re.match(r"^([A-Za-z0-9_-]{11})$", u)
            vid = vid_m.group(1) if vid_m else u
            if vid in processed:
                log(f"  [{vid}] 이미 발행된 영상 — 중복 발행 생략")
                continue
            try:
                metadata = video_metadata(u)
            except Exception as exc:
                failures.append({"video_id": vid, "error_type": type(exc).__name__,
                                 "state": "retryable", "stage": "metadata", "video": {"video_id": vid, "url": u, "title": title or vid, "channel": channel or "YouTube"}})
                log(f"  [{vid}] 메타데이터 조회 실패 — 보류: {type(exc).__name__}")
                continue
            resolved_channel = channel or metadata.get("channel") or "YouTube"
            resolved_cid = cid or metadata.get("channel_id") or ""
            configured = next((item for item in cfg.get("channels", [])
                               if item.get("channel_id") == resolved_cid), {})
            targets.append({"video_id": metadata.get("video_id") or vid,
                            "title": title or metadata.get("title") or vid,
                            "url": metadata.get("url") or u,
                            "channel": resolved_channel, "channel_id": resolved_cid,
                            "category": configured.get("category", "tech"),
                            "upload_date": metadata.get("upload_date") or date})
    else:
        cfg = load_config()
        targets = collect_targets(cfg, processed, limit)
        log(f"수집 대상 {len(targets)}건(수집창·dedup·필터 통과)")

    # Carry confirmed retryable failures across dated production staging folders.
    # Review/pending provider jobs remain visible, never become fresh paid work.
    if Path(staging_dir).parent == Path(DEFAULT_STAGING).parent:
        backlog = {}
        rejected_ids = set()
        for manifest in sorted(Path(staging_dir).parent.glob("*/run-status.json")):
            try:
                previous = json.loads(manifest.read_text())
                for video_id in previous.get("done_ids", []):
                    backlog.pop(video_id, None)
                    blocked_ids.discard(video_id)
                for failure in previous.get("failures", []):
                    video = failure.get("video")
                    backlog.pop(failure.get("video_id") or (video or {}).get("video_id"), None)
                    if failure.get("state") == "review_or_pending":
                        blocked_ids.add(failure.get("video_id") or (video or {}).get("video_id"))
                    if (failure.get("state") == "quality_rejected"
                            and failure.get("prompt_sha") == analyzer.PROMPT_SHA):
                        rejected_ids.add(failure.get("video_id") or (video or {}).get("video_id"))
                    if failure.get("state") == "retryable" and video and failure.get("stage") != "metadata":
                        if not urls and selection.is_xr(video):
                            # A prior retry must obey the same 14-day XR window.
                            try:
                                published = datetime.fromisoformat(video.get('published_at') or video.get('upload_date') or '')
                                if published.tzinfo is None: published = published.replace(tzinfo=timezone.utc)
                                age = (datetime.now(timezone.utc)-published).total_seconds()
                            except (ValueError, TypeError):
                                continue
                            if age < 0 or age > 14*24*3600:
                                continue
                        backlog[video["video_id"]] = video
            except (OSError, ValueError, TypeError, KeyError):
                continue
        if rejected_ids:
            log(f"형식 검사 불합격 이력 {len(rejected_ids)}건 제외(같은 프롬프트에서 재시도해도 같은 결과)")
        targets = [v for v in targets if v["video_id"] not in rejected_ids]
        unique = {}
        for video in list(backlog.values())[:(max(0, limit // 3) if targets else limit)] + targets:
            if video["video_id"] not in processed:
                unique.setdefault(video["video_id"], video)
        if urls:
            targets=list(unique.values())[:limit]
        else:
            alternatives=[v for v in unique.values() if v.get('_xr_alternate')]
            required=[v for v in unique.values() if v.get('_required') and not v.get('_xr_alternate')]
            regular=selection.prioritize([v for v in unique.values() if not v.get('_xr_alternate') and not v.get('_required')],limit)
            targets=required+(regular[:1]+alternatives+regular[1:] if regular and selection.is_xr(regular[0]) else regular+alternatives)

    queue, done_ids, xr_done_ids = {}, [], []
    queue_path = os.path.join(staging_dir, QUEUE_NAME)
    try:
        previous = json.loads((Path(staging_dir) / "run-status.json").read_text())
        for failure in previous.get('failures',[]):
            if isinstance(failure,dict) and failure.get('state')=='review_or_pending':
                blocked_ids.add(failure.get('video_id'));failures.append(failure)
        previous_ids = previous["done_ids"]
        previous_queue = previous["queue"]
        hashes = previous["report_hashes"]
        if (previous.get("date") == date and isinstance(previous_ids, list)
                and len(previous_ids) == len(previous_queue)
                and all(Path(slug).name == slug and hashes.get(slug)
                        and hashlib.sha256((Path(staging_dir) / f"{slug}.html").read_bytes()).hexdigest() == hashes[slug]
                        for slug in previous_queue)):
            queue, done_ids = dict(previous_queue), list(previous_ids)
            xr_done_ids = [v for v in previous.get('xr_done_ids',[]) if v in done_ids]
    except (OSError, ValueError, TypeError, KeyError):
        pass
    targets=[v for v in targets if v.get('video_id') not in blocked_ids]
    if not urls and not any(selection.is_xr(v) and not v.get('_xr_alternate') for v in targets):
        for index,v in enumerate(targets):
            if v.get('_xr_alternate'):
                targets[index]={k:value for k,value in v.items() if k!='_xr_alternate'}
                break
    required_ids={v['video_id'] for v in targets if v.get('_required')}
    effective_target_count=max(len(queue),min(limit,sum(not v.get('_xr_alternate') and not v.get('_required') for v in targets))+len(required_ids))
    def persist():
        # Save after every video; an interruption cannot erase earlier successes.
        hashes = {slug: hashlib.sha256((Path(staging_dir) / f"{slug}.html").read_bytes()).hexdigest()
                  for slug in queue if (Path(staging_dir) / f"{slug}.html").is_file()}
        # The status manifest is the authoritative commit, written last.
        payloads = {
            QUEUE_NAME: {"date": date, "messages": queue, "sent": []},
            "processed_video_ids.json": done_ids,
            "run-status.json": {"date": date, "target_count": max(effective_target_count,len(queue)),
                                "done_ids": done_ids, "xr_done_ids": xr_done_ids, "xr_required": False, "xr_policy": "daily_14d_optional",
                                "xr_status": "generated" if xr_done_ids else "not_published", "failures": failures,
                                "queue": queue, "report_hashes": hashes},
        }
        for name, payload in payloads.items():
            path = Path(staging_dir) / name
            temporary = path.with_suffix(path.suffix + ".new")
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)

    for v in targets:
        if v.get('_xr_alternate') and xr_done_ids:continue
        # Preserve already completed reports across a policy change. One XR
        # supplement may exceed the cap when an old full queue contains none;
        # never delete/recreate successful results merely to make room.
        if (not v.get('_required') and sum(x not in required_ids for x in done_ids)>=limit
                and not (not urls and not xr_done_ids and selection.is_xr(v))):
            break
        if v["video_id"] in done_ids:
            continue
        try:
            slug, entry = process_video(v, staging_dir, date)
            queue[slug] = entry
            done_ids.append(v["video_id"])
            if selection.is_xr(v):xr_done_ids.append(v["video_id"])
        except Exception as e:  # noqa: BLE001
            # Preserve blocked/pending provider receipts: isolate, never resubmit
            # under a new ID or bypass the evidence gate.
            failure = {"video_id": v["video_id"], "video": v,
                       "error_type": type(e).__name__,
                       "state": "review_or_pending" if isinstance(e, openrouter.RoutingBlocked) else "retryable"}
            if isinstance(e, analyzer.ReportQualityError):
                # The stored model response is reused for identical input, so a
                # shape rejection would repeat daily and occupy a target slot.
                failure.update(state="quality_rejected", prompt_sha=analyzer.PROMPT_SHA,
                               error=str(e)[:300])
            failures.append(failure)
            log(f"  [실패] {v.get('title') or v['video_id']}: {type(e).__name__}: {e}")
        persist()
    persist()

    log(f"완료: {len(queue)}/{max(effective_target_count,len(queue))}건 성공 → {staging_dir}")
    log(f"큐: {queue_path}")
    return {"date": date, "queue": queue, "done_ids": done_ids,
            "target_count": max(effective_target_count,len(queue)), "staging_dir": staging_dir, "failures": failures,
            "xr_required": False, "xr_policy": "daily_14d_optional",
            "xr_status": "generated" if xr_done_ids else "not_published", "xr_done_ids": xr_done_ids,
            "xr_quality_passed": bool(urls) or bool(xr_done_ids)}


def record_quality_gate(staging_dir, date, status, **fields):
    """Atomically add the gate outcome to this run's authoritative receipt."""
    path = Path(staging_dir) / "run-status.json"
    if not path.is_file():
        # Verification already fails closed on a missing receipt.
        return False
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("date") != date:
        raise RuntimeError("YouTube run receipt date differs")
    state["quality_gate"] = {"status": status, **fields}
    temporary = path.with_suffix(path.suffix + ".new")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", action="append", default=[], help="단일영상 URL(반복 가능, E2E 테스트)")
    ap.add_argument("--title", default="", help="--url 전용: 슬러그·메타에 쓸 영상 제목(미지정 시 video_id로 대체)")
    ap.add_argument("--channel", default="", help="--url 전용: 슬러그·메타에 쓸 채널명")
    ap.add_argument("--staging-dir", default=DEFAULT_STAGING)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--min-success-ratio", type=float, default=0.6,
                    help="targets가 있을 때 필요한 최소 성공 비율")
    ap.add_argument("--publish", action="store_true",
                    help="스테이징 산출을 origin에 실발행(클론→복사→큐병합→commit→push→LOG갱신). "
                         "미지정 시 지금처럼 스테이징만(완전 무변경).")
    ap.add_argument("--dry-push", action="store_true",
                    help="--publish와 함께: 실쓰기 직전까지 다 하되 git push --dry-run(origin 무변경)+LOG 미기록. 검증용.")
    a = ap.parse_args()
    res = run(a.url, a.staging_dir, a.limit, title=a.title, channel=a.channel)
    required = max(1, int(res["target_count"] * a.min_success_ratio + 0.999)) if res["target_count"] else 0
    passed = len(res["queue"]) >= required
    # Publication verification reads this receipt; a withheld run must not be
    # expected on the public list.
    record_quality_gate(res["staging_dir"], res["date"], "passed" if passed else "failed",
                        succeeded=len(res["queue"]), required=required,
                        min_success_ratio=a.min_success_ratio)
    if res["target_count"]:
        if not passed:
            raise SystemExit(
                f"YouTube Summaries quality gate failed: {len(res['queue'])}/"
                f"{res['target_count']} (required {required})"
            )
    # XR is an optional daily edition: no eligible XR does not block other videos.
    if a.publish:
        if not res["queue"]:
            log("발행 대상 0건 — publish 생략")
            return
        publish(res["staging_dir"], res["date"], res["queue"], res["done_ids"],
                dry_run=a.dry_push)


if __name__ == "__main__":
    main()
