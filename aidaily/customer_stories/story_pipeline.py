"""Rolling newsroom workspace; prepares evidence without issuing model/publication calls.

python -m aidaily.customer_stories.story_pipeline --date 2026-11-02 --output DIR
Archive summaries are already published evidence, never new reporting or message counts.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from difflib import SequenceMatcher
from aidaily import config
from aidaily.customer_stories.pipeline import public_story_text, public_source_label


def fingerprint(text):
    return hashlib.sha256(re.sub(r'\s+', ' ', text.strip()).casefold().encode()).hexdigest()


def prepare(data_root, date, days=14):
    end = dt.date.fromisoformat(date)
    if not 1 <= days <= 14:
        raise ValueError('window must be between 1 and 14 days')
    start = end - dt.timedelta(days=days-1)
    evidence, missing, digests = [], [], {}
    for offset in range(days):
        day = (start + dt.timedelta(days=offset)).isoformat()
        path = Path(data_root) / (day+'.json')
        if not path.exists():
            missing.append(day)
            continue
        raw = path.read_bytes()
        data = json.loads(raw)
        digests[day] = hashlib.sha256(raw).hexdigest()
        for i, item in enumerate((data.get('gen') or {}).get('items') or []):
            content = public_story_text(item.get('content') or '')
            if not content.strip():
                continue
            index = item.get('publication_index', i)
            # Stable evidence identity includes the text hash to detect edited history.
            eid = f'archive:{day}:{index}:{fingerprint(content)[:12]}'
            evidence.append(dict(evidence_id=eid, date=day,
                issue=public_story_text(item.get('issue') or ''), text=content,
                sources=[public_source_label(str(s)) for s in item.get('sources', [])],
                conditions=public_story_text(item.get('conditions') or ''),
                service=public_story_text(item.get('service') or ''),
                url=item.get('primary_url') or '', already_published=True,
                publication_id=f'customer_story:{day}:{index}'))
    related = []
    # Search suggestions only. No transitive merge or deletion based on similarity.
    for pos, left in enumerate(evidence):
        for right in evidence[pos+1:]:
            score = SequenceMatcher(None, left['issue'].casefold(), right['issue'].casefold()).ratio()
            exact = bool(left['url'] and left['url'] == right['url']) or fingerprint(left['text']) == fingerprint(right['text'])
            if exact or score >= .43:
                related.append(dict(left=left['evidence_id'], right=right['evidence_id'],
                    title_similarity=round(score,4), reason='same_url_or_text' if exact else 'similar_title',
                    decision='needs_editor_review'))
    return dict(schema_version=2, mode='archive_review', window_start=start.isoformat(),
                window_end=end.isoformat(), missing_dates=missing, input_hashes=digests,
                evidence=evidence, related_candidates=related,
                coverage='published_summaries_only', conversation_share=None,
                publication_allowed=False)


EDITOR_SYSTEM = '''너는 신문 기자다. 입력의 근거에서 독자에게 중요한 이야기 최대 2개를 찾는다.
확인된 사실(background)는 제공된 공개 조사자료의 확인된 사실만 짧게 요약하며 URL을 붙인다.
사용자 목소리(voices)는 실제 사용자 경험을 출처와 시점·조건에 귀속시킨다. 원문에 없는 주체·원인·결과·인용을 만들지 않는다.
상황→진행→결과의 기승전결을 개조식으로 구성하되 서로 다른 사람을 한 사람의 연속 경험으로 합성하지 않는다.
본문은 누가 무엇을 시도했고 어떤 결과를 겪었는지 직접 들려준다. '자료에 담겼다', '요약에서 확인했다',
'발행 자료에 따르면' 같은 조사 과정 설명으로 본문을 채우지 않는다. 불확실성은 판단에 필요한 범위만 짧게 쓴다.
이미 발행된 근거만 있는 후보는 재발행하지 않는다. 후속은 기존에 없던 검증 가능한 새 근거가 필수다.
유사도와 대화량은 취재 후보 신호이며 사실 확인이나 중복 확정을 대신하지 않는다.
출력 JSON: {"title":str,"overview":str,"items":[{"story_id":str,"issue":str,
"background":[{"text":str,"url":str,"label":str}],"voices":[{"text":str,"source":str,"date":str,"evidence_ids":[str]}],
"timeline":[{"stage":"상황|진행|결과","text":str,"evidence_ids":[str]}],
"commentary":str,"evidence_ids":[str],"related_links":[{"url":str,"label":str}]}]}.
새 근거가 부족하면 items는 빈 배열이어도 된다. 개인정보·비공개 대화 원문 인용 금지.'''


def validate_report(report, dossier, research=(), history=(), *, archive_review=False):
    """Fail closed on invented IDs/links and recycled publications; semantic review still required."""
    items = report.get('items')
    if not isinstance(items, list) or len(items)>2:
        raise ValueError('report must contain zero to two stories')
    reader_copy = [report.get('overview','')]
    for item in items:
        reader_copy.append(item.get('commentary',''))
        reader_copy.extend(row.get('text','') for key in ('voices','timeline') for row in item.get(key,[]))
    if any(phrase in str(text) for text in reader_copy for phrase in
           ('발행 자료에', '발행 자료에는', '자료에 담겼', '보관 자료에는', '요약에서 확인')):
        raise ValueError('tell the experience directly; remove editorial process prose')
    pool = {row['evidence_id']: row for row in dossier['evidence']}
    urls = {row.get('url') for row in dossier['evidence'] if row.get('url')}
    urls.update(row['url'] for row in research)
    facts = {row['url'] for row in research}
    ids = set(history)
    for item in items:
        sid = item.get('story_id')
        if not isinstance(sid,str) or not re.fullmatch(r'[a-z0-9-]{1,80}',sid) or sid in ids:
            raise ValueError('invalid or previously published story ID')
        ids.add(sid)
        refs = item.get('evidence_ids') or []
        if not refs or any(ref not in pool for ref in refs):
            raise ValueError('unknown or missing story evidence')
        if archive_review and report.get('publication_allowed') is not False:
            raise ValueError('archive review must explicitly disable publication')
        if not archive_review and all(pool[ref].get('already_published',True) for ref in refs):
            raise ValueError('no new evidence: archived story cannot be republished')
        claim_refs={ref for row in item.get('voices',[])+item.get('timeline',[]) for ref in row.get('evidence_ids',[])}
        if not archive_review and not any(ref in claim_refs and pool[ref].get('already_published')is False for ref in refs):
            raise ValueError('new evidence must support a displayed voice or timeline claim')
        for row in item.get('background',[]):
            if row.get('url') not in facts:
                raise ValueError('background needs a supplied public research source')
        for row in item.get('related_links',[]):
            if row.get('url') not in urls:
                raise ValueError('invented related URL')
        for row in item.get('voices',[]) + item.get('timeline',[]):
            evidence_ids = row.get('evidence_ids') or []
            if not evidence_ids or any(ref not in refs for ref in evidence_ids):
                raise ValueError('each voice and timeline claim needs story evidence')
    return report


def generate_story_report(dossier, research=(), history=()):
    """Explicit live generation through the existing provider boundary only.

    Requires new evidence; returned candidate still needs editorial review.
    Never publishes or sends notifications.
    """
    from aidaily.integrations import openrouter
    if not any(row.get('already_published') is False for row in dossier['evidence']):
        raise ValueError('archive-only dossier: collect new reporting before generation')
    user=json.dumps({'dossier':dossier,'research':list(research),'published_story_ids':list(history)},ensure_ascii=False)
    if len(EDITOR_SYSTEM)+len(user)>16000:raise ValueError('private input exceeds local budget; split before generation')
    raw = openrouter.complete(EDITOR_SYSTEM,user,timeout=120,retries=2,max_tokens=4500,allow_external=True)
    report = json.loads(raw)
    validate_report(report,dossier,research,history)
    report.update(schema_version=2,editorial_review='required')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--date',required=True)
    parser.add_argument('--days',type=int,default=14)
    parser.add_argument('--data-root',type=Path,default=config.DATA_ROOT/'customer_stories')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=prepare(args.data_root,args.date,args.days)
    args.output.mkdir(parents=True,exist_ok=True)
    path=args.output/'dossier.json'
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    path.chmod(0o600)
    print(json.dumps({'evidence_count':len(result['evidence']), 'review_pairs':len(result['related_candidates']),
                      'missing_dates':result['missing_dates'], 'publication_allowed':False}))

if __name__=='__main__':main()
