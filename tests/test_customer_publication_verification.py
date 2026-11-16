import json,tempfile,unittest
from pathlib import Path
from unittest import mock
from aidaily.publishing import customer_verification as c
from aidaily.customer_stories.story_render import story_anchor
class Response:
 status=200
 def __init__(self,text):self.text=text
 def read(self):return self.text.encode()
 def __enter__(self):return self
 def __exit__(self,*args):pass
class CustomerPublicationTests(unittest.TestCase):
 def fixture(self,root):
  data=root/'data';docs=root/'docs';(data/'customer_stories/newsroom').mkdir(parents=True);docs.mkdir()
  (data/'customer_stories/2026-11-02.json').write_text(json.dumps({'gen':{'schema_version':2,'items':[{'story_id':'new-event','issue':'새 이야기'}]}}))
  url='https://example.org/2026-11-02.html#'+story_anchor('new-event')
  (docs/'v2/uservoice').mkdir(parents=True)
  (docs/'v2/uservoice/2026-11-02.html').write_text('<article id="'+story_anchor('new-event')+'">새 이야기 확인된 사실 사용자 목소리</article>')
  (docs/'search-index.json').write_text(json.dumps([{'kind':'customer_story','date':'2026-11-02','story_id':'new-event','id':'customer_story:2026-11-02:new-event','url':url,'title':'새 이야기','story_content':{'background':[{'text':'새로 확인한 사실','url':'https://official.example/fact'}],'voices':[{'text':'사용자의 실제 질문'}],'commentary':'성능은 별도 확인해야 한다'}}]))
  (data/'customer_stories/newsroom/story-history.json').write_text(json.dumps([{'date':'2026-11-02','story_id':'new-event','status':'generated'}]))
  return data,docs,url
 def test_complete_main_content_required_before_history_is_published(self):
  with tempfile.TemporaryDirectory()as d:
   root=Path(d);data,docs,url=self.fixture(root)
   listing='<article id="item-customer_story:2026-11-02:new-event">새 이야기 확인된 사실 새로 확인한 사실 <a href="https://official.example/fact">출처</a> 사용자 목소리 사용자의 실제 질문 기자의 짚어보기 성능은 별도 확인해야 한다</article>'
   with mock.patch.object(c.config,'DATA_ROOT',data),mock.patch.object(c.config,'DOCS_ROOT',docs):
    with self.assertRaises(RuntimeError):c.verify_customer_publication('2026-11-02',attempts=1,opener=lambda *a,**k:Response('old normal page'))
    self.assertEqual(json.loads((data/'customer_stories/newsroom/story-history.json').read_text())[0]['status'],'generated')
    result=c.verify_customer_publication('2026-11-02',attempts=1,opener=lambda u,**k:Response(listing))
    with self.assertRaises(RuntimeError):
     c.verify_customer_publication('2026-11-02',attempts=1,opener=lambda u,**k:Response(listing.replace('성능은 별도 확인해야 한다','이전 버전 해석')))
    self.assertEqual(result['status'],'verified')
    self.assertEqual(json.loads((data/'customer_stories/newsroom/story-history.json').read_text())[0]['status'],'published')
 def test_missing_local_current_result_is_not_success(self):
  with tempfile.TemporaryDirectory()as d:
   data,docs,url=self.fixture(Path(d));(docs/'search-index.json').write_text('[]')
   with mock.patch.object(c.config,'DATA_ROOT',data),mock.patch.object(c.config,'DOCS_ROOT',docs):
    with self.assertRaises(RuntimeError):c.verify_customer_publication('2026-11-02',attempts=1)
