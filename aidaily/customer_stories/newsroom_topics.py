"""Configurable discovery groups. Group similarity is not a same-event decision."""
import re
from aidaily.customer_stories.editorial_selection import evaluate_candidates, EditorialConfig

GROUPS = [
 ('chatgpt-codex-limits',r'(?s)(?=.*(?:codex|코덱스))(?=.*(?:chatgpt|챗\s*(?:지피티|gpt)))(?=.*(?:limit|한도|사용량|통합|공유))','ChatGPT·Codex 한도 통합과 사용자 질문'),
 ('grok-bot',r'grok[ -]?bot|그록\s*봇|그락\s*봇','개인 AI 비서의 작업 위임과 도구 선택'),
 ('whisper',r'whisper|위스퍼|음성.?인식|\bSTT\b|Notesoop','음성인식 도구의 실제 비교와 활용'),
 ('claude-code',r'claude\s*code|클로드\s*코드','코딩 에이전트의 실제 작업과 제약'),
 ('codex',r'\bcodex\b|코덱스','코딩 에이전트의 실행 결과와 사용 경험'),
 ('cursor',r'\bcursor\b|커서','코딩 도구 선택과 실제 활용'),
 ('chatgpt',r'chatgpt|챗지피티|챗GPT','AI 도구의 안내와 실제 활용'),
]
PROMOTION=re.compile(r'모집|할인코드|얼리버드|선착순|구매링크|광고문의')
EXPERIENCE=re.compile(r'돌려봤|돌려보|써봤|써보|사용해.?보|해봤|경험|실패|오류|작동하지|결과가')

def discovery(dossier, research_by_service, settings):
 topics=[];buckets={key:[]for key,_,_ in GROUPS}
 for row in dossier['evidence']:
  for key,pattern,label in GROUPS:
   if re.search(pattern,row['text'],re.I):buckets[key].append(row);break
 for key,_,label in GROUPS:
  rows=buckets[key]
  if not rows:continue
  observations=[]
  for row in rows:
   observations.append(dict(evidence_id=row['evidence_id'],source_id=row['source_id'],
     date=(row.get('observed_dates')or[row['date']])[-1],kind='promotion' if PROMOTION.search(row['text']) else 'experience' if EXPERIENCE.search(row['text']) else 'question',
     already_published=row['already_published']))
  topics.append(dict(topic_id=key,service=key,label=label,observations=observations,
    research=research_by_service.get(key,{}).get('sources',[]),already_reported=False,new_development=False))
 config=EditorialConfig(**settings.get('selection',{}))
 result=evaluate_candidates(topics,config)
 return topics,result
