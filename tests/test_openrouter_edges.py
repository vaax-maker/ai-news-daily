"""Contract edges using the installed SDK, mocked wire protocol and durable state."""
import hashlib
import json
import os
import re
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from aidaily.integrations import openrouter as llm
import test_fleet_text as fixtures

response = fixtures.response
http_error = fixtures.http_error


class EdgeTransportTests(unittest.TestCase):
    # Reuse only the real SDK's isolated transport fixture, not inherited tests.
    setUp = fixtures.FleetTextTests.setUp
    patch = fixtures.FleetTextTests.patch
    client = fixtures.FleetTextTests.client
    transport = fixtures.FleetTextTests.transport
    complete = fixtures.FleetTextTests.complete
    receipt = fixtures.FleetTextTests.receipt

    def path_for(self, business):
        name = hashlib.sha256((llm.PROJECT+'\0'+business).encode()).hexdigest()
        return self.root/'state'/(name+'.json')

    def legacy(self, business, state='local_pending', **extra):
        identity = {'project':llm.PROJECT, 'messages':[
            {'role':'system','content':'한국어로 근거만 요약한다'},
            {'role':'user','content':'GPU 작업은 한 번에 한 건 실행한다.'}],
            'models':llm.DEFAULT_MODELS,'temperature':0.2,'max_tokens':None}
        row = {'project':llm.PROJECT,'request_id':business,'state':state,
               'fingerprint':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),**extra}
        path=self.path_for(business);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(row));return path

    def test_invalid_values_rejected_before_state_sdk_or_any_transport(self):
        bad_tokens=[0,-1,True,False,'12',1.0,[],{},float('nan'),float('inf')]
        bad_temperatures=[True,False,None,'0.2',[],{},-0.1,2.01,float('nan'),float('inf'),-float('inf'),10**1000]
        cases=[{'max_tokens':v} for v in bad_tokens]+[{'temperature':v} for v in bad_temperatures]
        # Also ensure a legitimate long-text capability miss cannot hide bad input.
        cases += [{'max_tokens':0,'long':True},{'temperature':float('nan'),'long':True}]
        with mock.patch.object(llm,'_fleet_module') as sdk, mock.patch.object(llm,'_new_client') as local, \
             mock.patch.object(llm,'_load_key') as key:
            for kwargs in cases:
                long=kwargs.pop('long',False)
                with self.subTest(fields=list(kwargs),long=long):
                    with self.assertRaises((TypeError,ValueError)):
                        llm.complete('system','text'*5000 if long else 'user',**kwargs)
            sdk.assert_not_called();local.assert_not_called();key.assert_not_called()
        self.health.assert_not_called();self.network.assert_not_called();self.content.assert_not_called()
        self.external.assert_not_called()
        self.assertFalse((self.root/'state').exists())

    def test_positive_oversized_token_limit_keeps_full_external_request(self):
        text='원문\n끝까지 보존 '*10
        self.assertLessEqual(len('system')+len(text),16000)
        llm.complete('system',text,max_tokens=12289,temperature=0.0)
        self.health.assert_not_called();self.network.assert_not_called()
        body=json.loads(self.external.call_args.kwargs['data'])
        self.assertEqual(body['messages'][1]['content'],text)
        self.assertEqual(body['max_tokens'],12289)
        self.assertEqual(body['temperature'],0.0)

    def test_long_text_alone_is_known_unsupported_and_unchanged(self):
        text='a'*16001+'마지막 원문'
        llm.complete('system',text,max_tokens=64,temperature=2)
        self.health.assert_not_called();self.network.assert_not_called()
        body=json.loads(self.external.call_args.kwargs['data'])
        self.assertEqual(body['messages'],[{'role':'system','content':'system'},{'role':'user','content':text}])
        self.assertEqual(body['max_tokens'],64)

    def test_valid_boundaries_go_local_and_valid_id_is_unchanged(self):
        self.complete(max_tokens=12288,temperature=2,request_id='A.Valid_id-1')
        self.assertEqual(self.posts[0]['request_id'],'A.Valid_id-1')
        self.assertEqual(self.posts[0]['max_tokens'],12288)
        self.assertEqual(self.posts[0]['temperature'],2)
        self.assertNotIn('fleet_request_id',self.receipt())
        self.assertNotIn('fleet_request_id',llm.last_usage())
        self.external.assert_not_called()

    def test_colon_id_protocol_mapping_saved_before_health_post_and_replay(self):
        business='daily:2026-10-01:news'
        path=self.path_for(business)
        mapped=[]
        def health():
            saved=json.loads(path.read_text())
            self.assertEqual(saved['request_id'],business)
            self.assertRegex(saved['fleet_request_id'],r'^[A-Za-z0-9_.-]{1,80}$')
            mapped.append(saved['fleet_request_id'])
            return {'capabilities':{'chat':{'ready':True}}}
        def protocol(method,endpoint,data=None,**kw):
            if method=='POST':
                if not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',data['request_id']):raise http_error(400)
                saved=json.loads(path.read_text())
                self.assertEqual(data['request_id'],saved['fleet_request_id'])
            return self.transport(method,endpoint,data,**kw)
        self.health.side_effect=health;self.network.side_effect=protocol
        first=self.complete(request_id=business)
        fleet_id=self.posts[0]['request_id']
        self.assertNotEqual(fleet_id,business);self.assertEqual(mapped,[fleet_id])
        self.assertEqual(llm.last_usage()['request_id'],business)
        self.assertEqual(llm.last_usage()['fleet_request_id'],fleet_id)
        receipt_before=path.read_bytes()
        self.assertEqual(self.complete(request_id=business),first)
        self.assertEqual(path.read_bytes(),receipt_before)
        self.assertEqual(len(self.posts),1)
        self.external.assert_not_called()

    def test_long_unicode_and_empty_business_ids_are_preserved_and_stable(self):
        for business in ('업무:요약', 'x'*81, 'x'*500, ''):
            with self.subTest(length=len(business)):
                self.complete(request_id=business)
                mapped=llm.last_usage()['fleet_request_id']
                self.assertRegex(mapped,r'^[A-Za-z0-9_.-]{1,80}$')
                self.assertEqual(llm.last_usage()['request_id'],business)
                self.assertEqual(json.loads(self.path_for(business).read_text())['request_id'],business)
                before=len(self.posts);self.complete(request_id=business)
                self.assertEqual(len(self.posts),before)
                self.assertEqual(llm.last_usage()['fleet_request_id'],mapped)
        self.external.assert_not_called()

    def test_same_business_id_changed_input_conflicts_before_transport(self):
        business='daily:2026-10-01:news'
        self.complete(request_id=business)
        before=self.path_for(business).read_bytes()
        with mock.patch.object(llm,'_new_client') as local:
            with self.assertRaises(ValueError):llm.complete('changed system','new input',request_id=business)
            local.assert_not_called()
        self.assertEqual(self.path_for(business).read_bytes(),before)
        self.assertEqual(len(self.posts),1);self.external.assert_not_called()

    def test_direct_common_transport_rejects_raw_colon_id(self):
        def protocol(method,endpoint,data=None,**kw):
            if method=='POST' and not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}',data['request_id']):raise http_error(400)
            return self.transport(method,endpoint,data,**kw)
        self.network.side_effect=protocol
        direct=self.client(llm.PROJECT,self.root/'direct-control')
        fallback=mock.Mock()
        with self.assertRaises(urllib.error.HTTPError):
            direct.chat([{'role':'user','content':'fixture'}],request_id='direct:colon',fallback=fallback)
        fallback.assert_not_called();self.external.assert_not_called()

    def test_existing_valid_success_receipt_and_ids_are_byte_unchanged(self):
        self.complete(request_id='daily-2026-10-01-news')
        path=self.path_for('daily-2026-10-01-news');before=path.read_bytes()
        common=list((self.root/'state/fleet').glob('*.json'))
        before_common={p.name:p.read_bytes() for p in common}
        self.complete(request_id='daily-2026-10-01-news')
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual({p.name:p.read_bytes() for p in common},before_common)
        self.assertEqual(len(self.posts),1);self.external.assert_not_called()

    def test_existing_valid_accepted_job_resumes_same_id_job_fingerprint(self):
        business='daily-2026-10-01-news'
        def fail_poll(method,endpoint,data=None,**kw):
            if method=='POST':return self.transport(method,endpoint,data,**kw)
            raise urllib.error.URLError(TimeoutError())
        self.network.side_effect=fail_poll
        with self.assertRaises(llm.CompletionPending):self.complete(request_id=business)
        path=self.root/'state/fleet'/self.path_for(business).name
        before=json.loads(path.read_text())
        self.network.side_effect=self.transport;self.complete(request_id=business)
        after=json.loads(path.read_text())
        self.assertEqual(self.posts[0]['request_id'],business)
        self.assertEqual(len(self.posts),1)
        self.assertEqual(after['job_id'],before['job_id'])
        self.assertEqual(after['fingerprint'],before['fingerprint'])
        self.assertNotIn('fleet_request_id',self.receipt());self.external.assert_not_called()

    def test_legacy_incompatible_pending_receipt_never_mints_or_mutates(self):
        business='legacy:accepted'
        path=self.legacy(business)
        shared=self.root/'state/fleet'/path.name;shared.parent.mkdir()
        shared.write_text(json.dumps({'state':'local_accepted','job_id':'accepted-old-job',
                                      'payload':{'project':llm.PROJECT,'request_id':business}}))
        before=path.read_bytes();before_shared=shared.read_bytes()
        with mock.patch.object(llm,'_new_client') as local:
            for _ in range(2):
                with self.assertRaises(llm.CompletionPending):self.complete(request_id=business)
            local.assert_not_called()
        self.assertEqual(path.read_bytes(),before);self.assertEqual(shared.read_bytes(),before_shared)
        self.external.assert_not_called();self.network.assert_not_called()

    def test_local_pending_beyond_limit_is_replaced_once_by_external(self):
        business="stuck-job"
        path=self.legacy(business,local_pending_since=0)
        with mock.patch.object(llm,"_new_client") as local:
            llm.complete("한국어로 근거만 요약한다","GPU 작업은 한 번에 한 건 실행한다.",request_id=business)
            local.assert_not_called()
        self.assertEqual(self.external.call_count,1)
        self.assertEqual(json.loads(path.read_text())["fallback_reason"],"local_pending_timeout")

    def test_local_pending_within_limit_keeps_waiting(self):
        import time
        business="fresh-job"
        self.legacy(business,local_pending_since=time.time())
        with mock.patch.object(llm,"_new_client",side_effect=RuntimeError("no")) as local:
            with self.assertRaises(Exception):
                llm.complete("한국어로 근거만 요약한다","GPU 작업은 한 번에 한 건 실행한다.",request_id=business)
        self.external.assert_not_called()

    def test_orphan_legacy_common_receipt_never_mints_replacement(self):
        business='legacy:orphan';shared=self.root/'state/fleet'/self.path_for(business).name
        shared.parent.mkdir(parents=True);shared.write_text(json.dumps({'state':'local_submitting'}))
        before=shared.read_bytes()
        with mock.patch.object(llm,'_new_client') as local:
            with self.assertRaises(llm.CompletionPending):self.complete(request_id=business)
            local.assert_not_called()
        self.assertEqual(shared.read_bytes(),before)
        self.assertFalse(self.path_for(business).exists())
        self.external.assert_not_called();self.network.assert_not_called()

    def test_legacy_incompatible_cached_success_is_preserved(self):
        business='legacy:completed';path=self.legacy(business,state='succeeded',result=response(),
                                                    metadata={'request_id':business,'provider':'local:qwen3.8'})
        before=path.read_bytes()
        self.assertTrue(self.complete(request_id=business))
        self.assertEqual(path.read_bytes(),before)
        self.assertNotIn('fleet_request_id',llm.last_usage())
        self.external.assert_not_called();self.network.assert_not_called()

    def test_existing_mapping_is_reused_not_regenerated(self):
        business='stored:mapped';self.legacy(business,state='local_pending',fleet_request_id='saved-safe-id')
        self.complete(request_id=business)
        self.assertEqual(self.posts[0]['request_id'],'saved-safe-id')
        self.assertEqual(llm.last_usage()['fleet_request_id'],'saved-safe-id')
        self.external.assert_not_called()

    def test_uncertain_colon_submission_retry_keeps_fleet_id_and_never_pays(self):
        business='uncertain:colon';submitted=[]
        def uncertain(method,endpoint,data=None,**kw):
            if method=='POST':submitted.append(data['request_id'])
            raise urllib.error.URLError(TimeoutError())
        self.network.side_effect=uncertain
        with self.assertRaises(llm.CompletionPending):self.complete(request_id=business)
        saved=json.loads(self.path_for(business).read_text())
        def unavailable(method,endpoint,data=None,**kw):
            if method=='POST':submitted.append(data['request_id'])
            raise http_error(503)
        self.network.side_effect=unavailable
        with self.assertRaises(llm.CompletionPending):self.complete(request_id=business)
        self.assertEqual(submitted,[saved['fleet_request_id']]*2)
        self.external.assert_not_called()

    def test_empty_id_does_not_replace_legacy_auto_receipt(self):
        # Reproduce the former request_id='' automatic-ID behavior.
        automatic=hashlib.sha256(json.dumps({'project':llm.PROJECT,'messages':[
            {'role':'system','content':'한국어로 근거만 요약한다'},
            {'role':'user','content':'GPU 작업은 한 번에 한 건 실행한다.'}],
            'models':llm.DEFAULT_MODELS,'temperature':0.2,'max_tokens':None},sort_keys=True).encode()).hexdigest()
        old=self.legacy('text-'+automatic);before=old.read_bytes()
        with self.assertRaises(llm.CompletionPending):self.complete(request_id='')
        self.assertEqual(old.read_bytes(),before)
        self.external.assert_not_called();self.network.assert_not_called()


if __name__=='__main__':unittest.main()
