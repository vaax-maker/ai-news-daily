"""Real local-only completion using the project's established news prompt."""
import json
import time
from pathlib import Path
from unittest.mock import patch
from aidaily.ai_news import summarizer
from aidaily.integrations import openrouter
root=Path(__file__).resolve().parents[2]
start=time.monotonic()
rows=[{'n':'01','headline':'AI Daily의 세 콘텐츠 영역과 발행 순서', 'body':'AI Daily는 AI 뉴스, 고객사용기, YouTube 요약의 세 콘텐츠 영역을 제공한다. 각 영역의 생성기는 콘텐츠만 생성하고 직접 발행하지 않는다. 공통 publishing 모듈이 웹 발행을 담당하며, 발행 성공 후에만 notifications 모듈이 Telegram 알림을 보낸다. 로컬 GPU는 한 번에 한 작업만 실행한다.', 'takeaway':'생성, 발행, 알림 단계를 분리해 웹 발행이 실패하면 Telegram 알림을 보내지 않는다.'}]
user='입력 뉴스 1건:\n'+json.dumps(rows,ensure_ascii=False)
with patch.object(openrouter,'KEY',''), patch.object(openrouter,'_load_key',return_value=''), patch.object(openrouter,'request_json',side_effect=AssertionError('Paid transport forbidden')) as paid:
 out=openrouter.complete_json(summarizer.SYS,user,models=[summarizer.MODEL],max_tokens=1024,timeout=900,request_id="review-01a0f538-news-final-v1")
 metadata=openrouter.last_usage()
 report={'entry_point':'aidaily.integrations.openrouter.complete_json','prompt':'Established aidaily.ai_news.summarizer.SYS with synthetic source facts', 'result':out,'metadata':metadata,'wall_seconds':round(time.monotonic()-start,3),'paid_calls':0,'publishing_calls':0,'notification_calls':0}
 (root/'real-qwen-news.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 assert isinstance(out,list) and len(out)==1 and out[0]['n']=='01','JSON array contract'
 assert summarizer._valid_generated(out[0],rows[0]),'existing news bullet quality gate'
 assert len(out[0]['body'])==3,'body count'
 assert 'Telegram' in json.dumps(out,ensure_ascii=False),'source fact'
 assert metadata['provider']=='local:qwen3.8' and metadata['cost_usd']==0
 again=openrouter.complete_json(summarizer.SYS,user,models=[summarizer.MODEL],max_tokens=1024,timeout=900,request_id="review-01a0f538-news-final-v1")
 assert again==out,'stable receipt resume'
 paid.assert_not_called()
 report['checks']=['Valid JSON array','one item n=01','3 complete body bullets','existing _valid_generated gate','Telegram source fact','stable cached resume']
 (root/'real-qwen-news.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False))
