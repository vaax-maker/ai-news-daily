import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from aidaily.customer_stories import community_tap as tap
from aidaily.customer_stories import pipeline

class CommunityTapTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.cfg=self.root/'sources.json'
        self.env=patch.dict(os.environ,{'CUSTOMER_STORIES_COMMUNITY_CONFIG':str(self.cfg)})
        self.env.start()
        self.data=patch.object(tap.config,'DATA_ROOT',self.root)
        self.data.start()
        self.source=dict(id=tap.SOURCE_ID,enabled=True,approved=True,chat_id='123456',ssh_user='fovea',anonymous_label=tap.LABEL)
    def tearDown(self):
        self.data.stop();self.env.stop();self.temp.cleanup()
    def enable(self):
        self.cfg.write_text(json.dumps({'sources':[self.source]}))
    def payload(self, mid='1', text='도구의 검색 기능을 함께 사용했습니다'):
        return dict(received_count=1,messages=[dict(id=mid,text=text,type=1,timestamp=time.time()-1)])
    def test_absent_disabled_no_fetch(self):
        with patch.object(tap,'fetch') as fetch:
            self.assertEqual(tap.collect(fetcher=fetch),{'status':'disabled'})
            fetch.assert_not_called()
        self.source['approved']=False;self.enable()
        self.assertEqual(tap.approved_tap_paths(),[])
    def test_scope_fail_closed(self):
        self.source['id']='other';self.enable()
        with self.assertRaises(ValueError):tap.approved_sources()
    def test_incremental_merge_and_private_mode(self):
        self.enable()
        tap.collect(fetcher=lambda *_:self.payload())
        tap.collect(fetcher=lambda *_:self.payload())
        tap.collect(fetcher=lambda *_:self.payload('2','다른 메시지입니다'))
        path=tap.tap_path(self.source)
        self.assertEqual(len(path.read_text().splitlines()),2)
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual((Path(str(path)+'.lock').stat().st_mode&0o777),0o600)
    def test_fetch_only_and_coverage(self):
        self.enable();out=self.root/'snapshot.json'
        receipt=tap.collect('14d',str(out),True,lambda *_:self.payload())
        self.assertFalse(tap.tap_path(self.source).exists())
        self.assertEqual(receipt['history_completeness'],'not_verified')
        self.assertEqual(len(json.loads(out.read_text())['messages']),1)
    def test_fixed_window_boundaries_and_separate_counts(self):
        self.enable()
        end=1800000000
        start=end-14*86400
        rows=[dict(id=str(i),text='boundary text',type=1,timestamp=ts)
              for i,ts in enumerate([start-1,start,start+1,end-1,end,end+1,'bad'],1)]
        payload=dict(received_count=8,messages=rows)  # one row stripped remotely
        out=self.root/'fixed.json'
        receipt=tap.collect('14d',str(out),True,lambda *_:payload,clock=lambda:end)
        self.assertEqual((receipt['requested_start'],receipt['requested_end']),(start,end))
        self.assertEqual((receipt['received_count'],receipt['accepted_count'],receipt['invalid_count'],receipt['outside_window_count']),(8,3,2,3))
        self.assertEqual((receipt['acquired_oldest_ts'],receipt['acquired_newest_ts']),(start-1,end+1))
        self.assertEqual((receipt['oldest_ts'],receipt['newest_ts']),(start,end-1))
        self.assertEqual([r['id'] for r in json.loads(out.read_text())['messages']],['2','3','4'])

    def test_invalid_timestamps(self):
        self.enable();payload=self.payload()
        payload['messages'][0]['timestamp']='invalid'
        rows,invalid=tap.normalize(self.source,payload)
        self.assertEqual((rows,invalid),([],1))
        for value in ['NaN',float('inf'),-1,True]:
            with self.assertRaises(ValueError):tap.timestamp(value)
    def test_reader_labels_scope_and_cross_path_dedup(self):
        self.enable();legacy=self.root/'legacy.jsonl';now=time.time()
        rows=[dict(chat_id=cid,chat_name=name,ts=now,text='기존 방 메시지 '+str(i)) for i,(cid,name) in enumerate(pipeline._OPEN_CHAT_ROOM_NAMES.items(),1)]
        rows.append(dict(chat_id='gpters',chat_name='GPTers 덕후',ts=now,text='기존 GPTers 메시지'))
        rows.append(dict(chat_id='other',ts=now,text='중복 메시지'))
        legacy.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        path=tap.tap_path(self.source);path.parent.mkdir(parents=True)
        path.write_text(''.join(json.dumps(dict(chat_id=cid,chat_name='spoof',ts=ts,text=text))+'\n' for cid,ts,text in [('123456',now,'새 모임 메시지'),('123456',now,'중복 메시지'),('other',now,'범위 밖 메시지'),('123456',float('nan'),'유효하지 않은 시간')]))
        with patch.object(pipeline,'COMMUNITY_TAP_FILE',str(legacy)):
            rooms,hashes=pipeline.load_jsonl_rooms(exclude_ids=())
            self.assertEqual(set(rooms),{f'오픈채팅 · 모임 {i}' for i in range(1,8)}|{'오픈채팅 · 모임 99'})
            self.assertEqual(rooms[tap.LABEL],'새 모임 메시지')
            self.assertEqual(len(hashes),len(set(hashes)))
            self.assertEqual(pipeline.load_jsonl_rooms(exclude_ids=(),seen=dict.fromkeys(hashes)),({},[]))
    def test_bad_optional_config_preserves_legacy(self):
        legacy=self.root/'legacy.jsonl'
        legacy.write_text(json.dumps(dict(id='1',chat_id='654321',chat_name='오픈채팅 · 모임 1',text='실제 도구의 검색 설정을 조정하고 결과를 비교했습니다',ts=time.time()-1),ensure_ascii=False)+'\n')
        from io import StringIO
        for bad in ('{invalid',json.dumps({'sources':[dict(self.source,chat_id='invalid')]})):
            self.cfg.write_text(bad)
            with patch.object(pipeline,'COMMUNITY_TAP_FILE',legacy),patch('sys.stderr',new_callable=StringIO) as err:
                rooms,_=pipeline.load_jsonl_rooms(exclude_ids=())
            self.assertIn('오픈채팅 · 모임 1',rooms)
            self.assertNotIn(tap.LABEL,rooms)
            self.assertIn('legacy sources preserved',err.getvalue())

    def test_ssh_registry_host_alias_and_redaction_program(self):
        self.enable();registry=self.root/'registry.json'
        registry.write_text(json.dumps({'services':{'abot-host-web':{'instances':{'pro':{'tailnet':'https://registered.example:9443'}}}}}))
        class Result:
            returncode=0;stdout='{"messages":[],"received_count":0}'
        with patch.dict(os.environ,{'ABOT_SERVICES_FILE':str(registry)}):
            calls=[]
            tap.fetch(self.source,'14d',lambda cmd,**kwargs:(calls.append(cmd) or Result()))
        self.assertIn('fovea@registered.example',calls[0]);self.assertIn('HostKeyAlias=pro',calls[0]);self.assertIn('StrictHostKeyChecking=yes',calls[0])
        self.assertNotIn('sender',tap.REMOTE)
        with self.assertRaises(ValueError):tap.fetch(self.source,'14d;bad')


class RemoteSanitizationTests(unittest.TestCase):
    def test_remote_drops_participants_and_rejects_other_room(self):
        import subprocess
        import sys
        from contextlib import redirect_stdout
        from io import StringIO
        private=dict(id='1',text='selected text',timestamp='2026-11-02T00:00:00Z',type=1,chat_id='123456',sender={'name':'PRIVATE'})
        class Result:
            returncode=0
            stdout=json.dumps([private,dict(id='2',text={'sender':'PRIVATE'},timestamp=1)])
        output=StringIO()
        with patch.object(sys,'argv',['remote','123456','14d']),patch.object(subprocess,'run',return_value=Result()),redirect_stdout(output):
            exec(tap.REMOTE,{})
        payload=json.loads(output.getvalue())
        self.assertEqual(payload['received_count'],2)
        self.assertEqual(set(payload['messages'][0]),{'id','text','timestamp','type'})
        self.assertEqual(len(payload['messages']),1)
        self.assertNotIn('PRIVATE',output.getvalue())
        private['chat_id']='999'
        Result.stdout=json.dumps([private])
        with patch.object(sys,'argv',['remote','123456','14d']),patch.object(subprocess,'run',return_value=Result()),self.assertRaises(SystemExit) as error:
            exec(tap.REMOTE,{})
        self.assertEqual(error.exception.code,22)

if __name__=='__main__':unittest.main()
