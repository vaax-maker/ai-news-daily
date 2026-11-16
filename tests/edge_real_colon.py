"""One fresh local-only minimal colon business ID call; no corpus or PII."""
import hashlib
import json
import os
import re
import time
from pathlib import Path
from unittest.mock import patch
os.environ['OPENROUTER_API_KEY']='verification-disabled'
from aidaily.integrations import openrouter as llm
root=Path(os.environ['AIDAILY_EDGE_REVIEW']);state=Path(os.environ['AIDAILY_LLM_STATE_DIR'])
business='edge-review:2026-10-01:colon-v1'
metadata=None
started=time.monotonic()
with patch.object(llm,'KEY','verification-disabled'), patch.object(llm,'_load_key',return_value='verification-disabled'), \
     patch.object(llm,'request_json',side_effect=AssertionError('Paid transport blocked')) as paid:
    text=llm.complete('Return only OK.','Reply OK.',max_tokens=16,temperature=0,timeout=240,request_id=business)
    metadata=llm.last_usage()
    assert isinstance(text,str) and text.strip(), 'text output contract'
    assert metadata['request_id']==business
    mapped=metadata['fleet_request_id'];assert re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',mapped)
    assert mapped!=business and metadata['provider']=='local:qwen3.8' and metadata['cost_usd']==0.0
    outer=state/(hashlib.sha256((llm.PROJECT+'\0'+business).encode()).hexdigest()+'.json')
    shared=state/'fleet'/(hashlib.sha256((llm.PROJECT+'\0'+mapped).encode()).hexdigest()+'.json')
    receipt=json.loads(shared.read_text());assert receipt['payload']['request_id']==mapped
    shared_bytes=shared.read_bytes();outer_bytes=outer.read_bytes()
    second=llm.complete('Return only OK.','Reply OK.',max_tokens=16,temperature=0,timeout=240,request_id=business)
    assert second==text and llm.last_usage()['fleet_request_id']==mapped
    assert shared.read_bytes()==shared_bytes and outer.read_bytes()==outer_bytes
    paid.assert_not_called()
    report={'entry_point':'aidaily.integrations.openrouter.complete','business_request_id':business,'fleet_request_id':mapped,
            'model_usage':metadata,'output_text':text,'shared_job_id':receipt['job_id'],'shared_receipt_state':receipt['state'],
            'shared_payload_uses_supported_id':True,'business_id_preserved':True,'same_business_replay_same_result':True,
            'successful_receipts_byte_unchanged_on_replay':True,'paid_calls':0,'publication_calls':0,'telegram_messages':0,
            'source':'minimal synthetic prompt, no corpus/PII','wall_seconds':round(time.monotonic()-started,3)}
    (root/'edge-real-colon.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False))
