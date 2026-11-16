"""Private evidence from rolling, sampled checkpoints and current inputs.

No network or writes. Counts are evidence fragments, never message counts,
participants, complete conversation coverage or topic popularity.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

_HEADER = re.compile(r'^\s*=====\s*\[(.+)\]\s*=====\s*$')
_REF = re.compile(r'^\[([^\]]+)\]\s*(.*)$')
_NOISE = re.compile(r'^(?:사진|동영상|이모티콘|삭제된 메시지|음성메시지|파일:|샵검색|송금)(?:\s|$)')
_URLONLY = re.compile(r'^https?://\S+$', re.I)


def _norm(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _safe_url(value):
    if not isinstance(value, str) or value != value.strip() or any(ord(ch) < 33 for ch in value):
        return ''
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            return ''
        parsed.port
    except ValueError:
        return ''
    return value


def gather(data_root, date, days=14, extra_web=None, extra_rooms=None):
    """Read a KST edition-date window; source dates mean observation, not event time.

    data_root is customer_stories/ containing checkpoints/YYYY-MM-DD.json and
    historical YYYY-MM-DD.json publication payloads. extra_web is an iterable of
    {source, text, url}; extra_rooms maps a private source label to a text block.
    A checkpoint with inputs is usable even while another generation is pending,
    since inputs were frozen; a checkpoint without inputs is only a missing sample.
    Output contains private text and must remain in private state, never a public API.
    """
    from aidaily.customer_stories.pipeline import public_source_label, public_story_text
    if type(days) is not int or not 1 <= days <= 14:
        raise ValueError('window must contain between one and fourteen edition dates')
    end = dt.date.fromisoformat(date)
    if end.isoformat() != date:
        raise ValueError('date must be YYYY-MM-DD')
    start = end - dt.timedelta(days=days-1)
    root = Path(data_root)
    rows, history, receipts, missing, errors = {}, [], [], [], []
    publication_claims = []
    ledger_path=root/'newsroom/story-history.json'
    ledger=json.loads(ledger_path.read_text())if ledger_path.exists()else[]
    confirmed={(r.get('date'),r.get('story_id'))for r in ledger if r.get('status')=='published'}
    ignored_lines = 0

    def source_identity(label, private):
        label = _norm(re.sub(r'\s*\(비공개 대화\)\s*$', '', str(label)))
        public = public_source_label(label)
        # Canonicalize the three built-in public sources and preserve private
        # source distinctions even when an unknown label maps to anonymous 99.
        identity = public if not private and public in ('Reddit', 'HN', '긱뉴스') else label
        return 'source-' + _digest(identity.casefold())[:20], public

    def add(text, label, observed, *, private, url='', provenance=None):
        nonlocal ignored_lines
        text = _norm(text)
        if len(text) < 10 or text.startswith('{') or _NOISE.match(text) or _URLONLY.fullmatch(text):
            ignored_lines += 1
            return None
        source_id, source = source_identity(label, private)
        eid = 'evidence-' + _digest(source_id + '\0' + text)[:32]
        if eid not in rows:
            rows[eid] = dict(evidence_id=eid, text=text, source_id=source_id,
                source=source, sources=[source], url=_safe_url(url), private=private,
                observed_dates=[], date=observed, date_semantics='edition_observation_not_event_time',
                already_published=False, used_by_publication_ids=[], source_previously_cited_by=[], provenance=[])
        row = rows[eid]
        if observed not in row['observed_dates']:
            row['observed_dates'].append(observed)
            row['observed_dates'].sort()
            row['date'] = row['observed_dates'][0]
        if not row['url'] and _safe_url(url):
            row['url'] = _safe_url(url)
        if provenance and provenance not in row['provenance']:
            row['provenance'].append(provenance)
        return eid

    for offset in range(days):
        observed = (start + dt.timedelta(days=offset)).isoformat()
        published = root / (observed + '.json')
        if published.exists():
            try:
                payload = json.loads(published.read_text())
                items = (payload.get('gen') or {}).get('items') or []
                if not isinstance(items, list):
                    raise ValueError()
                for position, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    index = item.get('publication_index', item.get('story_id', position))
                    pid = f'customer_story:{observed}:{index}'
                    content = public_story_text(item.get('content') or '')
                    if not content and item.get('voices'):
                        content = ' '.join(public_story_text(v.get('text') or '') for v in item['voices'] if isinstance(v, dict))
                    entry = dict(publication_id=pid, story_id=item.get('story_id'), date=observed,
                        issue=public_story_text(item.get('issue') or ''), content=content,
                        conditions=public_story_text(item.get('conditions') or ''),
                        sources=[public_source_label(s) for s in item.get('sources',[])],
                        refs=[str(ref) for ref in item.get('refs',[])],
                        url=_safe_url(item.get('primary_url') or ''), evidence_ids=list(item.get('evidence_ids') or []))
                    is_v2=(payload.get('gen')or{}).get('schema_version')==2
                    entry['status']='published'if not is_v2 or(observed,item.get('story_id'))in confirmed else 'generated'
                    history.append(entry)
                    excerpt = _norm((item.get('_knowledge') or {}).get('source_excerpt') or '')
                    if entry['status']=='published':publication_claims.append((entry, excerpt))
            except (OSError, ValueError, TypeError, AttributeError):
                errors.append(dict(date=observed, kind='invalid_publication_snapshot'))
        path = root / 'checkpoints' / (observed + '.json')
        if not path.exists():
            missing.append(observed)
            continue
        try:
            raw = path.read_bytes()
            snapshot = json.loads(raw)
            inputs = snapshot.get('inputs') or {}
            corpus, refmap = inputs.get('corpus'), inputs.get('refmap') or {}
            if not isinstance(corpus, str) or not isinstance(refmap, dict):
                missing.append(observed)
                continue
            sha = hashlib.sha256(raw).hexdigest()
            receipts.append(dict(date=observed, sha256=sha, characters=len(corpus),
                stage=str(snapshot.get('stage') or ''), scope='frozen_truncated_model_input'))
            label = None
            for line_no, line in enumerate(corpus.splitlines(), 1):
                match = _HEADER.match(line)
                if match:
                    label = match.group(1)
                    continue
                if not label:
                    continue
                is_private = '비공개 대화' in label or '오픈채팅' in label or 'GPTers' in label
                ref = _REF.match(line) if not is_private else None
                url = ''
                text = line
                rid = None
                if ref:
                    rid, text = ref.groups()
                    target = refmap.get(rid) or {}
                    if isinstance(target, dict):
                        url = target.get('url') or ''
                provenance = dict(kind='checkpoint',date=observed,sha256=sha,line=line_no)
                if rid:
                    provenance['ref'] = rid
                add(text, label, observed, private=is_private, url=url, provenance=provenance)
        except (OSError, ValueError, TypeError, AttributeError):
            errors.append(dict(date=observed,kind='invalid_checkpoint_snapshot'))

    if extra_web is not None:
        if not isinstance(extra_web, (list, tuple)):
            raise ValueError('extra_web must be a list of normalized rows')
        for item in extra_web:
            if not isinstance(item, dict) or not isinstance(item.get('text'),str):
                raise ValueError('invalid extra web row')
            label = str(item.get('source') or '공개 웹')
            add(item['text'], label, date, private=False, url=item.get('url') or '',
                provenance=dict(kind='current_web_sample',date=date))
    if extra_rooms is not None:
        if not isinstance(extra_rooms, dict) or any(not isinstance(v,str) for v in extra_rooms.values()):
            raise ValueError('extra_rooms must map source labels to text blocks')
        for label, block in extra_rooms.items():
            for line_no, text in enumerate(block.splitlines(),1):
                add(text, label, date, private=True,
                    provenance=dict(kind='current_room_sample',date=date,line=line_no))

    # Match evidence actually cited by prior output. This is conservative: a
    # partial lexical match alone does not mark the entire topic as published.
    # Topic-level semantic repetition is left to the editorial history comparison.
    for row in rows.values():
        for old, excerpt in publication_claims:
            same_source = row['source'] in old['sources']
            ref_used = any(p.get('kind')=='checkpoint' and p.get('date')==old['date']
                and p.get('ref') in old['refs'] for p in row['provenance'])
            exact_excerpt = same_source and len(excerpt)>=15 and excerpt in _norm(row['text'])
            exact_content = same_source and len(_norm(old['content']))>=15 and _norm(old['content']) == _norm(row['text'])
            same_public_url = bool(row['url'] and row['url']==old['url'])
            if same_public_url:
                row['source_previously_cited_by'].append(old['publication_id'])
            if row['evidence_id'] in old['evidence_ids'] or ref_used or exact_excerpt or exact_content:
                row['already_published'] = True
                row['used_by_publication_ids'].append(old['publication_id'])
                if row['evidence_id'] not in old['evidence_ids']:
                    old['evidence_ids'].append(row['evidence_id'])
        row['used_by_publication_ids'] = sorted(set(row['used_by_publication_ids']))
        row['source_previously_cited_by'] = sorted(set(row['source_previously_cited_by']))

    return dict(schema_version=2, window_start=start.isoformat(), window_end=end.isoformat(),
        evidence=sorted(rows.values(), key=lambda r:(r['date'],r['source_id'],r['evidence_id'])),
        history=history, coverage=dict(scope='sampled_checkpoints_and_current_inputs', complete=False,
            date_semantics='edition_observation_not_event_time',
            missing_checkpoint_dates=missing, checkpoint_receipts=receipts, errors=errors,
            current_web_sample_supplied=extra_web is not None,
            current_room_sample_supplied=extra_rooms is not None,
            current_samples_may_be_truncated=True, ignored_short_or_noise_fragments=ignored_lines,
            conversation_share=None), publication_allowed=False)
