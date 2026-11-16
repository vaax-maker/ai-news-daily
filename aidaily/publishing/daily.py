"""Resumable daily production, independent of the runtime Git working tree."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from zoneinfo import ZoneInfo

from aidaily import config
from aidaily.publishing.pipeline import public_outputs

ADMIN_CONFIG_PATH = Path.home() / '.config/aidaily/admin-notifications.json'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.new')
    with temporary.open('w') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def fingerprint(paths):
    result = hashlib.sha256()
    for path in sorted(map(Path, paths), key=str):
        result.update(str(path).encode())
        result.update(path.read_bytes() if path.is_file() else b'<missing>')
    return result.hexdigest()


def generation_outputs(stage, date):
    if stage == 'gov':
        return [config.DATA_ROOT / 'ai_news/gov/editions' / f'{date}.json']
    if stage == 'horizon':
        return [config.DATA_ROOT / 'ai_news/horizon/editions' / f'{date}.json']
    if stage == 'customer':
        return [config.DOCS_ROOT / 'v2/uservoice' / f'{date}.html',
                config.DATA_ROOT / 'customer_stories' / f'{date}.json']
    return [config.DOCS_ROOT / 'archive/index.json', config.DOCS_ROOT / 'daily.html']


def publication_inputs(date):
    paths = [config.PROJECT_ROOT / p for p in public_outputs(date) if p != 'docs/search-index.json']
    paths.append(config.PUBLISHING_REPOSITORY / 'index.html')
    paths.extend(config.PUBLISHING_REPOSITORY.glob(f'{date}-*.html'))
    if horizon_enabled(date):
        paths.extend(generation_outputs('horizon', date))
    if gov_enabled(date):
        paths.extend(generation_outputs('gov', date))
    return paths



def gov_enabled(date):
    try:
        settings = json.loads((config.DATA_ROOT / 'ai_news/gov/settings.json').read_text())
        return settings.get('enabled') is True and date >= settings['start']
    except (OSError, ValueError, KeyError, TypeError):
        return False


def gov_generated(date):
    try:
        from aidaily.publishing.gov_section import normalize_edition
        edition = normalize_edition(json.loads(generation_outputs('gov', date)[0].read_text()), date)
        return edition['status'] in ('complete', 'partial')
    except (OSError, ValueError, KeyError, TypeError):
        return False


def gov_optional_status(date):
    try:
        data = json.loads((config.DATA_ROOT / 'ai_news/gov/runs' / f'{date}.json').read_text())
        return 'failed' if data.get('status') in ('failed', 'auth_required', 'invalid') else 'pending'
    except (OSError, ValueError, TypeError):
        return 'failed'


def horizon_enabled(date):
    try:
        setting = json.loads((config.DATA_ROOT / 'ai_news/horizon/settings.json').read_text())
        return setting.get('enabled', True) and setting['pilot']['start'] <= date <= setting['pilot']['end']
    except (OSError, ValueError, KeyError, TypeError):
        return False


def horizon_generated(date):
    try:
        from aidaily.publishing.horizon_section import normalize_edition
        value = normalize_edition(json.loads(generation_outputs('horizon', date)[0].read_text()), date)
        return value['status'] in ('complete', 'partial')
    except (OSError, ValueError, KeyError, TypeError):
        return False


def horizon_optional_status(date):
    try:
        value = json.loads((config.DATA_ROOT / 'ai_news/horizon/runs' / f'{date}.json').read_text())
        return 'pending' if value.get('status') in ('pending', 'scoring', 'fetching_original', 'enriching') else 'failed'
    except (OSError, ValueError, TypeError):
        return 'failed'


def today_generated(date):
    try:
        rows = json.loads((config.DOCS_ROOT / 'archive/index.json').read_text())
        edition = next(row for row in rows if row.get('date') == date)
        return bool(edition.get('stories')) and all(
            story.get('body_bullets') for story in edition['stories'])
    except (OSError, ValueError, StopIteration, KeyError, TypeError):
        return False


def customer_generated(date):
    try:
        report = json.loads((config.DATA_ROOT / 'customer_stories' / f'{date}.json').read_text())
        page = (config.DOCS_ROOT / 'v2/uservoice' / f'{date}.html').read_text()
        return report.get('date') == date and bool((report.get('gen') or {}).get('items')) and date in page
    except (OSError, ValueError, TypeError):
        return False


def verify_publication(date, *, attempts=24, delay=10, opener=None):
    """Confirm this date's news and exact YouTube outputs before notifying."""
    opener = opener or urllib.request.urlopen
    rows = json.loads((config.DOCS_ROOT / 'search-index.json').read_text())
    news = [row for row in rows if row.get('date') == date and row.get('kind') == 'ai_news']
    if not news:
        raise RuntimeError('No current-day news in publication index')
    headline = html.escape(str(news[0]['title']))
    url = config.TECH_DAILY_URL + '?date=' + date
    expected_label = date.replace('-', '.')
    last_error = None
    for attempt in range(attempts):
        try:
            with opener(url, timeout=30) as response:
                page = response.read().decode('utf-8')
                if response.status == 200 and expected_label in page and (
                        headline in page or str(news[0]['title']) in page):
                    from aidaily.publishing.youtube_verification import verify_youtube_publication
                    youtube = verify_youtube_publication(date, opener=opener)
                    from aidaily.publishing.customer_verification import verify_customer_publication
                    customer = verify_customer_publication(date, attempts=1, opener=opener)
                    result = {'url': url, 'http_status': 200, 'date': date,
                              'headline_confirmed': True, 'customer': customer, **youtube}
                    if horizon_enabled(date):
                        from aidaily.publishing.horizon_verification import verify_horizon_publication
                        try:
                            result['horizon'] = verify_horizon_publication(date, opener=opener)
                        except (OSError, ValueError, RuntimeError) as error:
                            # The experimental section has its own result; a stale
                            # Horizon page must not block verified regular news.
                            result['horizon'] = {'status': 'verification_failed',
                                'optional': True, 'error_type': type(error).__name__}
                    if gov_enabled(date):
                        from aidaily.publishing.gov_verification import verify_gov_publication
                        try:
                            result['gov'] = verify_gov_publication(date, opener=opener)
                        except (OSError, ValueError, RuntimeError) as error:
                            result['gov'] = {'status': 'verification_failed', 'optional': True,
                                             'error_type': type(error).__name__}
                    return result
        except (OSError, ValueError, RuntimeError) as error:
            last_error = error
        if attempt + 1 < attempts:
            time.sleep(delay)
    detail = ': ' + str(last_error) if last_error else ''
    raise RuntimeError('Published current-day page is not yet confirmed by HTTPS' + detail)



def record_horizon_publication(date, verification):
    """Only HTTPS-confirmed editions become future duplicate exclusions."""
    if not verification.get('exact_edition') or verification.get('status') not in ('complete', 'partial'):
        return
    from aidaily.publishing.horizon_section import load_editions
    edition = load_editions().get(date)
    if not edition:
        raise RuntimeError('Verified Horizon edition missing locally')
    digest = hashlib.sha256(json.dumps(edition, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if digest != verification.get('edition_sha256'):
        raise RuntimeError('Horizon edition changed after HTTPS verification')
    path = config.DATA_ROOT / 'ai_news/horizon/published-history.json'
    if path.exists():
        history = json.loads(path.read_text())
        if not isinstance(history, list):
            raise ValueError('Horizon publication history must be a list')
    else:
        history = []
    entry = {'date': date, 'status': 'published',
             'verified_at': dt.datetime.now(ZoneInfo('Asia/Seoul')).isoformat(),
             'items': [{key: item[key] for key in ('id', 'title', 'url')} for item in edition['items']]}
    save(path, [row for row in history if row.get('date') != date] + [entry])


def alert_failure(state, state_path, stage, error):
    """Persist an admin incident; never route failure notices to the reader digest."""
    incident = {'date': state['date'], 'stage': stage, 'error_type': type(error).__name__,
                'status': 'recorded', 'recorded_at': dt.datetime.now().isoformat()}
    token = os.environ.get('AIDAILY_ADMIN_TELEGRAM_TOKEN', '')
    chat = os.environ.get('AIDAILY_ADMIN_TELEGRAM_CHAT_ID', '')
    if not (token and chat):
        try:
            setting = json.loads(ADMIN_CONFIG_PATH.read_text())
            if setting.get('enabled') and setting.get('verified_chat_type') == 'private':
                from aidaily.notifications.daily_digest import load_credentials
                candidate_token, candidate_chat = load_credentials()
                if hashlib.sha256(candidate_chat.encode()).hexdigest() == setting.get('chat_sha256'):
                    token, chat = candidate_token, candidate_chat
        except (OSError, ValueError, TypeError):
            pass
    key = hashlib.sha256(f'{state["date"]}:{stage}:{type(error).__name__}'.encode()).hexdigest()
    alerts = state.setdefault('alerts', {})
    if key in alerts:
        return
    if token and chat:
        incident['status'] = 'sending'
        alerts[key] = incident
        save(state_path, state)  # Reserve before sending; uncertain deliveries never auto-resend.
        try:
            from aidaily.notifications.telegram import send_admin_text
            result = send_admin_text(f'AI Daily 발행 중단 · {state["date"]}\n단계: {stage}\n오류: {type(error).__name__}\n기존 로그와 체크포인트에서 재개할 수 있습니다.', token, chat)
            incident.update(status='sent', message_id=(result.get('result') or {}).get('message_id'))
        except Exception:
            incident['status'] = 'uncertain'
    else:
        incident['status'] = 'admin_destination_not_configured'
    alerts[key] = incident
    save(state_path, state)


def notification_receipt(date):
    path = config.DATA_ROOT / 'notifications/daily_digest' / f'{date}.json'
    if not path.exists():
        return {'status': 'not_sent'}
    try:
        value = json.loads(path.read_text())
        if (isinstance(value, dict) and value.get('date', date) == date
                and value.get('status') in ('sent', 'sending', 'uncertain')):
            return value
    except (OSError, ValueError, TypeError):
        pass
    # An unreadable receipt is not evidence that no message was sent.
    return {'status': 'uncertain'}


def run_day(date, *, adopt_generated=False, no_notify=False, prepare_only=False, wait_for_lock=False,
            notify_only=False):
    if notify_only and (no_notify or prepare_only):
        raise ValueError('notify-only cannot suppress notification or prepare content')
    directory = config.DATA_ROOT / 'publishing/daily_runs'
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / f'{date}.json'
    with (directory / 'pipeline.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | (0 if wait_for_lock else fcntl.LOCK_NB))
        except BlockingIOError:
            print('[daily] already running; duplicate execution skipped', flush=True)
            return
        state = json.loads(state_path.read_text()) if state_path.exists() else {'date': date, 'stages': {}}
        prior_error = {key: state.get(key) for key in ('status', 'current_stage', 'error_type')}
        stage = 'startup'
        try:
            stages = [
                ('customer', 'aidaily.customer_stories.pipeline', ['--docs-root', 'docs', '--since', '1d', '--date', date]),
                ('news', 'aidaily.ai_news.pipeline', ['--docs-root', 'docs']),
            ]
            if horizon_enabled(date):
                stages.append(('horizon', 'aidaily.ai_news.horizon', ['--date', date]))
            if gov_enabled(date):
                stages.append(('gov', 'aidaily.ai_news.gov', ['--date', date]))
            stages.extend([
                ('publish', 'aidaily.publishing.pipeline', []),
                ('verify', None, []),
                ('notify', 'aidaily.notifications.daily_digest', []),
            ])
            if notify_only:
                stages = [entry for entry in stages if entry[0] in ('verify', 'notify')]
            for stage, module, extra in stages:
                if prepare_only and stage == 'publish':
                    state.update(status='prepared', current_stage=None)
                    save(state_path, state)
                    return
                if stage == 'notify' and no_notify:
                    receipt = notification_receipt(date)
                    state['notification_status'] = receipt['status']
                    if receipt['status'] != 'sent':
                        state['stages']['notify'] = {'status': 'deferred', 'reason': 'no_notify',
                            'delivery_status': receipt['status'], 'recorded_at': dt.datetime.now().isoformat()}
                    else:
                        state['stages']['notify'] = {'status': 'complete', 'reused_receipt': True,
                            'delivery_status': 'sent', 'completed_at': dt.datetime.now().isoformat()}
                    save(state_path, state)
                    continue
                outputs = generation_outputs(stage, date) if stage in ('customer', 'news', 'horizon', 'gov') else publication_inputs(date)
                if stage in ('verify', 'notify'):
                    outputs.append(config.DOCS_ROOT / 'search-index.json')
                digest = fingerprint(outputs)
                previous = state['stages'].get(stage, {})
                if stage not in ('verify', 'notify') and previous.get('status') in ('complete', 'empty') and previous.get('fingerprint') == digest:
                    print(f'[daily] {stage}: reused completed stage', flush=True)
                    continue
                adopt = adopt_generated and ((stage == 'news' and today_generated(date)) or
                    (stage == 'customer' and customer_generated(date)) or
                    (stage == 'horizon' and horizon_generated(date)) or
                    (stage == 'gov' and gov_generated(date)))
                state.update(status='running', current_stage=stage)
                state['stages'][stage] = {'status': 'running'}
                save(state_path, state)
                print(f'[daily] {stage}: ' + ('adopt existing generated output' if adopt else 'start'), flush=True)
                detail = {}
                code = 0
                if stage == 'verify':
                    detail = verify_publication(date)
                    state['publication_status'] = 'verified'
                    try:
                        record_horizon_publication(date, detail.get('horizon') or {})
                    except (OSError, ValueError, RuntimeError) as error:
                        detail['horizon_history'] = {'status': 'failed', 'optional': True,
                                                     'error_type': type(error).__name__}
                elif stage == 'notify' and notification_receipt(date)['status'] == 'sent':
                    detail = {'delivery_status': 'sent', 'reused_receipt': True}
                elif stage == 'notify' and notification_receipt(date)['status'] in ('sending', 'uncertain'):
                    state['notification_status'] = notification_receipt(date)['status']
                    raise RuntimeError('Notification delivery is uncertain; inspect the existing receipt, do not resend')
                elif not adopt:
                    if stage in ('horizon', 'gov'):
                        interpreter = config.DATA_ROOT / 'ai_news/horizon/.venv/bin/python' if stage == 'horizon' else sys.executable
                        try:
                            code = subprocess.run([str(interpreter), '-m', module, *extra], cwd=config.PROJECT_ROOT, timeout=(1200 if prepare_only else 120) if stage == 'horizon' else 180).returncode
                        except subprocess.TimeoutExpired:
                            code = 75
                        except OSError:
                            code = 1
                        if code or not (horizon_generated(date) if stage == 'horizon' else gov_generated(date)):
                            # An optional experiment must not suppress existing
                            # news or turn a pending model job into empty success.
                            state['stages'][stage] = {'status': horizon_optional_status(date) if stage == 'horizon' else gov_optional_status(date),
                                'optional': True, 'exit_code': code,
                                'recorded_at': dt.datetime.now().isoformat()}
                            save(state_path, state)
                            print(f'[daily] {stage}: deferred; existing publication continues', flush=True)
                            continue
                        detail = {'optional': True}
                    else:
                        code = subprocess.run([sys.executable, '-m', module, *extra], cwd=config.PROJECT_ROOT).returncode
                    if code and stage == 'customer' and code != 2:
                        # Customer stories are local-only (private sources). A pending or
                        # blocked local model must not suppress the news edition.
                        state['stages'][stage] = {'status': 'deferred', 'optional': True, 'exit_code': code,
                            'recorded_at': dt.datetime.now().isoformat()}
                        save(state_path, state)
                        print('[daily] customer: deferred; news publication continues', flush=True)
                        continue
                    if code and not (stage == 'customer' and code == 2):
                        raise RuntimeError(f'{stage} exited {code}; resume the same run')
                if stage == 'notify':
                    receipt = config.DATA_ROOT / 'notifications/daily_digest' / f'{date}.json'
                    if not receipt.exists() or json.loads(receipt.read_text()).get('status') != 'sent':
                        raise RuntimeError('Notification receipt missing or uncertain; do not resend blindly')
                    state['notification_status'] = 'sent'
                state['stages'][stage] = {'status': 'empty' if code == 2 else 'complete',
                    'fingerprint': fingerprint(outputs), 'completed_at': dt.datetime.now().isoformat(), **detail}
                save(state_path, state)
            receipt = notification_receipt(date)
            state['notification_status'] = receipt['status']
            state.update(status='complete' if receipt['status'] == 'sent' else 'published_unnotified',
                         current_stage=None)
            if prior_error.get('error_type'):
                state.setdefault('recovery_history', []).append({**prior_error,
                    'recovered_at': dt.datetime.now().isoformat(),
                    'publication_status': state.get('publication_status'),
                    'notification_status': state['notification_status']})
            state.pop('error_type', None)
            save(state_path, state)
        except Exception as error:
            state.update(status='failed', current_stage=stage, error_type=type(error).__name__)
            state['stages'][stage] = {'status': 'failed', 'error_type': type(error).__name__}
            save(state_path, state)
            alert_failure(state, state_path, stage, error)
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adopt-generated', action='store_true', help='Reuse valid outputs already generated today')
    parser.add_argument('--no-notify', action='store_true')
    parser.add_argument('--wait-for-lock', action='store_true', help='Wait for an in-progress preparation before scheduled release')
    parser.add_argument('--prepare-only', action='store_true', help='Generate only; defer publication and notifications to the scheduled release')
    parser.add_argument('--notify-only', action='store_true', help='Verify the public edition and recover its missing daily notification without generating or publishing')
    args = parser.parse_args()
    if args.notify_only and (args.no_notify or args.prepare_only):
        parser.error('--notify-only cannot be combined with --no-notify or --prepare-only')
    date = dt.datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
    run_day(date, adopt_generated=args.adopt_generated, no_notify=args.no_notify, prepare_only=args.prepare_only,
            wait_for_lock=args.wait_for_lock, notify_only=args.notify_only)


if __name__ == '__main__':
    main()
