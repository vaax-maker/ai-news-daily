"""One stored sample/domain; private content stays on mini1, paid HTTP blocked."""
import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import patch

# Prevent import-time external key-file lookup during this verification harness.
os.environ['OPENROUTER_API_KEY'] = 'verification-disabled'
from aidaily.ai_news import summarizer
from aidaily.customer_stories import pipeline as customer
from aidaily.youtube_summaries import analyzer
from aidaily.integrations import openrouter as llm

review = Path(os.environ['AIDAILY_SAMPLE_REVIEW'])
source = Path.home() / 'aidaily'
report_path = review / 'representative-results.json'
progress_path = review / 'representative-progress.json'
report = {'domains': [], 'paid_network_calls': 0, 'publication_calls': 0,
          'notification_calls': 0, 'source_content_in_report': False}

def write():
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

def sample(domain, system, user, call, gate, provenance):
    row = {'domain': domain, 'source': provenance, 'input_sha256': hashlib.sha256((system+'\0'+user).encode()).hexdigest(),
           'input_chars': len(system)+len(user), 'local_supported': len(system)+len(user)<=16000,
           'input_truncated': False, 'output_content_in_report': False, 'paid_transport_interceptions': 0}
    report['domains'].append(row)
    progress_path.write_text(json.dumps({'phase': domain, 'completed_domains': len(report['domains'])-1, 'total_domains': 3}))
    write()
    start = time.monotonic()
    def block_paid(*args, **kwargs):
        row['paid_transport_interceptions'] += 1
        raise AssertionError('Paid transport blocked by representative harness')
    with patch.object(llm, 'KEY', 'verification-disabled'), \
         patch.object(llm, '_load_key', return_value='verification-disabled'), \
         patch.object(llm, 'request_json', side_effect=block_paid):
        try:
            result = call()
            row['model_usage'] = llm.last_usage()
            row['gate'] = gate(result)
            row['outcome'] = 'gate_pass' if row['gate']['passed'] else 'quality_review'
        except llm.CompletionPending:
            row['outcome'] = ('unsupported_paid_transport_blocked' if not row['local_supported']
                              else 'paid_transport_blocked' if row['paid_transport_interceptions'] else 'local_pending')
            row['gate'] = {'passed': False, 'evaluated': False}
        except Exception as exc:
            row['outcome'] = 'quality_review' if llm.last_usage() else 'routing_review'
            row['error_type'] = type(exc).__name__
            row['model_usage'] = llm.last_usage()
            row['gate'] = {'passed': False, 'evaluated': False}
    row['wall_seconds'] = round(time.monotonic()-start,3)
    write()

# Select one existing stored news item, without truncating any field.
archive_path = source / 'docs/archive/index.json'
archive = json.loads(archive_path.read_text())
entry = next(e for e in archive if e.get('stories'))
story = entry['stories'][0]
news = {k: story.get(k, '') for k in ('n','headline','body','takeaway')}
news_user = '입력 뉴스 1건:\n' + json.dumps([news], ensure_ascii=False)
def news_gate(result):
    valid = isinstance(result, list) and len(result)==1 and isinstance(result[0],dict)
    return {'passed': bool(valid and str(result[0].get('n'))==str(news['n']) and summarizer._valid_generated(result[0],news)),
            'evaluated': True, 'item_count': len(result) if isinstance(result,list) else None,
            'body_count': len(result[0].get('body',[])) if valid else None,
            'why_count': len(result[0].get('why',[])) if valid else None}
sample('news', summarizer.SYS, news_user,
       lambda: llm.complete_json(summarizer.SYS, news_user, models=[summarizer.MODEL], max_tokens=1024, timeout=120,
                                request_id='review-representative-news-v1'), news_gate,
       {'path': str(archive_path), 'date': entry.get('date'), 'kind': 'one full stored news source item'})

# Raw private conversations are deliberately excluded. Reuse all nine safe,
# already-anonymized public-source items in the stored customer-story sample.
customer_path = source / 'data/customer_stories/latest.json'
stored = json.loads(customer_path.read_text())
allowed = ('Reddit', 'Hacker News', '긱뉴스', 'GeekNews')
blocks = []
for name in allowed:
    items = [i for i in stored['gen']['items'] if i.get('sources') == [name]]
    if items:
        lines = [f'[{name[0]}{index}] '+json.dumps({k:i.get(k,'') for k in ('issue','content','commentary','service','model','conditions')},ensure_ascii=False)
                 for index,i in enumerate(items,1)]
        blocks.append(f'===== [{name}] =====\n'+'\n'.join(lines))
corpus = '\n\n'.join(blocks)
customer_user = customer._build_user(corpus)
def customer_gate(result):
    customer._validate(result)
    issues = customer.evidence_issues(result, corpus)
    # Structural/numeric checks are measured, without claiming full PII/fact
    # acceptance or running a second model-based judge beyond one sample.
    return {'passed': not issues, 'evaluated': True, 'item_count':len(result['items']),
            'numeric_evidence_issue_count':len(issues),'full_semantic_or_pii_acceptance':False}
sample('customer_stories', customer.SYSTEM, customer_user,
       lambda: customer.generate(corpus), customer_gate,
       {'path':str(customer_path),'date':stored.get('date'),
        'kind':'all safe stored published public-source items as resummary input; no raw private corpus available',
        'public_items':sum(len([i for i in stored['gen']['items'] if i.get('sources')==[n]]) for n in allowed)})

# Preserve the entire existing long transcript. Do not use analyzer.analyze's
# legacy [:30000] cap to make it eligible for local Qwen.
youtube_path = Path.home() / 'nlm-infographic/deploy/publish-one-jobs/fEm_transcript.json'
transcript = json.loads(youtube_path.read_text())['transcript']
youtube_user = '저장된 영상 전체 자막:\n'+transcript
assert transcript and youtube_user.endswith(transcript)
def youtube_gate(result):
    if not isinstance(result,dict):return {'passed':False,'evaluated':True}
    analyzer._validate_report(result)
    return {'passed':True,'evaluated':True,'middle_sections':len(result['sections'])}
sample('youtube_summaries', analyzer.SYS, youtube_user,
       lambda: llm.complete_json(analyzer.SYS, youtube_user, timeout=120,
                                request_id='review-representative-youtube-full-v1'), youtube_gate,
       {'path':str(youtube_path),'kind':'full stored transcript; existing legacy data boundary',
        'transcript_chars':len(transcript)})
report['representative_quality_accepted'] = False
write()
progress_path.write_text(json.dumps({'phase':'complete','completed_domains':3,'total_domains':3}))
print(json.dumps({'outcomes': [{k:r.get(k) for k in ('domain','outcome','input_chars','local_supported','wall_seconds')} for r in report['domains']],
                  'paid_network_calls':0}, ensure_ascii=False))
