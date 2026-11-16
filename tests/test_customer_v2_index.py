import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from aidaily import config
from aidaily.customer_stories.story_render import story_anchor

# Use the staged implementation for isolation, normal import after integration.
STAGED = os.environ.get('AIDAILY_TEST_SEARCH_INDEX_PATH')
if STAGED:
    spec=importlib.util.spec_from_file_location('staged_customer_search_index',STAGED)
    search_index=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(search_index)
else:
    from aidaily.publishing import search_index


class CustomerV2IndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.docs=self.root/'docs'; self.data=self.root/'data'
        folder=self.docs/'v2'/config.LEGACY_CUSTOMER_STORIES_PUBLIC_DIR
        folder.mkdir(parents=True)
        (self.data/'customer_stories').mkdir(parents=True)
        (folder/'manifest.json').write_text(json.dumps([{'date':'2026-11-02','title':'종합 제목','n':2}]))
        self.patch=mock.patch.object(config,'DATA_ROOT',self.data)
        self.patch.start();self.addCleanup(self.patch.stop)
    def write(self,gen):
        (self.data/'customer_stories/2026-11-02.json').write_text(json.dumps({'date':'2026-11-02','gen':gen}))
    def item(self,identity='grok-task',index=17):
        return dict(story_id=identity,issue='개인비서에게 맡기는 일',publication_index=index,
                    voices=[{'text':'빠르게 보였다. 그러나 같은 조건에서는 빨라지지 않았다.','source':'오픈채팅 · 모임 3'}],
                    commentary='실행 조건을 함께 확인한다.',primary_url='https://source.example/original',article_kind='explainer')
    def test_main_link_and_complete_public_content_without_private_evidence(self):
        item=self.item();item['dek']='도구 선택을 결정하는 세 가지 확인 질문.'
        self.write({'schema_version':2,'items':[item]})
        row=search_index.load_customer_stories(str(self.docs))[0]
        self.assertEqual(row['summary'],item['dek']);self.assertEqual(row['summary_bullets'],[item['dek']])
        self.assertEqual(row['customer_story_index'],17)
        self.assertTrue(row['url'].startswith(config.TECH_DAILY_URL+'?date=2026-11-02&item='))
        self.assertEqual(row['story_content']['voices'][0]['text'],item['voices'][0]['text'])
        self.assertNotEqual(row['url'],item['primary_url'])
        self.assertEqual(row['article_kind'],'explainer')
    def test_voice_fallback_preserves_negation_and_does_not_embed_evidence(self):
        item=self.item();item['background']=[{'text':'private background id','url':'https://example.org'}]
        item['evidence_ids']=['private-source-id']
        self.write({'schema_version':2,'items':[item]})
        row=search_index.load_customer_stories(str(self.docs))[0]
        self.assertEqual(row['summary'],item['voices'][0]['text'])
        self.assertNotIn('evidence_ids',row);self.assertNotIn('background',row)
        self.assertNotIn('evidence_ids',json.dumps(row['story_content']))
        self.assertEqual(row['channel'],'오픈채팅 · 모임 3')
    def test_integer_identity_and_story_id_fallback_survive_reorder(self):
        a,b=self.item(),self.item('second-task',18);b.pop('publication_index')
        self.write({'schema_version':2,'items':[a,b]})
        first=search_index.enrich_unified(search_index.load_customer_stories(str(self.docs)))
        self.write({'schema_version':2,'items':[b,a]})
        second=search_index.enrich_unified(search_index.load_customer_stories(str(self.docs)))
        self.assertEqual({x['story_id']:(x['id'],x['uid'],x['url']) for x in first},
                         {x['story_id']:(x['id'],x['uid'],x['url']) for x in second})
    def test_empty_v2_does_not_resurrect_old_manifest(self):
        self.write({'schema_version':2,'items':[]})
        self.assertEqual(search_index.load_customer_stories(str(self.docs)),[])
    def test_invalid_v2_identity_or_more_than_two_halts_index(self):
        bad=[{'schema_version':2,'items':[self.item(),self.item()]},
             {'schema_version':2,'items':[self.item('a',17),self.item('b',17)]},
             {'schema_version':2,'items':[self.item(str(i),i) for i in range(3)]},
             {'schema_version':2,'items':[dict(self.item(),publication_index=True)]},
             {'schema_version':2,'items':[dict(self.item(),story_id='')]}]
        for gen in bad:
            with self.subTest(gen=gen):
                self.write(gen)
                with self.assertRaises(ValueError):search_index.load_customer_stories(str(self.docs))
    def test_legacy_record_is_unchanged(self):
        self.write({'items':[{'issue':'기존 제목','content':'기존 본문.','sources':['Reddit'],
                            'publication_index':4,'primary_url':'https://source.example/original','commentary':'해설'}]})
        row=search_index.load_customer_stories(str(self.docs))[0]
        self.assertEqual(row['summary'],'기존 본문.')
        self.assertEqual(row['url'],'https://source.example/original')
        self.assertEqual(row['customer_story_index'],4)
        self.assertNotIn('story_id',row)

if __name__=='__main__':unittest.main()
