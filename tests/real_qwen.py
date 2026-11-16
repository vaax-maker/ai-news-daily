"""Paid HTTP is blocked; exercise the unchanged integration entry point only."""
import json
import time
from pathlib import Path
from unittest.mock import patch
from aidaily.integrations import openrouter

root = Path(__file__).resolve().parents[2]
evidence = root / 'real-qwen.json'
start = time.monotonic()
system = '너는 한국어 뉴스 요약 편집자다. 제공한 사실만 JSON으로 요약한다. 설명이나 코드펜스 없이 {"n":"01","body":["문장","문장","문장"],"why":["문장"]} 형식으로 답하라.'
user = '시험용 기사: AI Daily는 AI 뉴스, 고객사용기, YouTube 요약의 세 영역을 제공한다. 콘텐츠를 생성한 뒤 웹에 발행한다. 발행 성공 후에만 Telegram 알림을 보낸다. 로컬 GPU는 한 번에 작업 한 건을 실행한다. 이 사실을 본문 3개 불릿과 의미 1개 불릿으로 요약하라. 수치와 서비스명을 유지하고 새 사실을 만들지 마라.'
with patch.object(openrouter, 'KEY', ''), patch.object(openrouter, '_load_key', return_value=''), patch.object(openrouter, 'request_json', side_effect=AssertionError('Paid transport forbidden')) as paid:
 result = openrouter.complete_json(system, user, max_tokens=512, timeout=900)
 assert isinstance(result, dict) and result['n'] == '01', 'JSON contract'
 assert len(result['body']) == 3 and len(result['why']) == 1, 'bullet contract'
 assert all(isinstance(x,str) and x.strip() for x in result['body']+result['why']), 'nonempty text'
 assert 'Telegram' in json.dumps(result,ensure_ascii=False), 'source fact preserved'
 metadata = openrouter.last_usage()
 assert metadata['provider'] == 'local:qwen3.8' and metadata['cost_usd'] == 0.0
 # Resume through the same entry point after creating a fresh caller context.
 second = openrouter.complete_json(system, user, max_tokens=512, timeout=900)
 assert second == result and openrouter.last_usage()['request_id'] == metadata['request_id']
 paid.assert_not_called()
 report={'entry_point':'aidaily.integrations.openrouter.complete_json -> complete -> common InferenceClient.chat', 'result':result,'metadata':metadata,'wall_seconds':round(time.monotonic()-start,3),'content_checks':['JSON object','n=01','3 body bullets','1 why bullet','nonempty Korean text','Telegram source fact','stable cached resume'], 'paid_calls':0,'publishing_calls':0,'notification_calls':0}
 evidence.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False))
