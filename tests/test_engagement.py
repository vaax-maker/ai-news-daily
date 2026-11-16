import json
from pathlib import Path
import subprocess
import unittest

from aidaily.publishing.engagement import stable_uid, instrument_html


class EngagementTests(unittest.TestCase):
    def test_python_and_server_identity_agree_and_survive_reordering(self):
        rows = [
            {'kind':'ai_news','date':'2026-10-20','id':'ai_news:2026-10-20:01','title':'제품 공개','url':'https://EXAMPLE.com/news?a=1&utm_source=telegram#part'},
            {'kind':'ai_news','date':'2026-10-20','id':'ai_news:2026-10-20:02','title':'새 모델','url':'https://example.com/한글?a=2&b=hello+world'},
            {'kind':'ai_news','date':'2026-10-20','title':'  새   기능 ','url':'https://vaax-maker.github.io/ai-news-daily/archive.html'},
            {'kind':'customer_story','date':'2026-10-20','id':'customer_story:2026-10-20:3','customer_story_index':3},
            {'kind':'youtube_summary','url':'https://wootom.github.io/news/2026-10-20-video.html'},
        ]
        root=Path(__file__).resolve().parents[1]
        script="import {stableUid} from './aidaily/admin/engagement-store.mjs';const rows="+json.dumps(rows)+";console.log(JSON.stringify(rows.map(stableUid)));"
        result=subprocess.run(['node','--input-type=module','-e',script],cwd=root,capture_output=True,text=True,check=True)
        self.assertEqual([stable_uid(r) for r in rows],json.loads(result.stdout))
        self.assertEqual(stable_uid(rows[0]),stable_uid({**rows[0],'id':'ai_news:2026-10-20:99'}))
        self.assertNotEqual(stable_uid(rows[0]),stable_uid({**rows[0],'url':'https://example.com/news?a=2'}))

    def test_tracking_is_idempotent_and_has_no_admin_credentials(self):
        endpoint='https://public.example/aidaily-events/pixel.gif'
        original='<html><body><h1>뉴스</h1></body></html>'
        once=instrument_html(original,endpoint)
        twice=instrument_html(once,endpoint)
        self.assertEqual(once,twice)
        self.assertEqual(twice.count('id="aidaily-pv"'),1)
        self.assertIn('replaceState',once)
        self.assertNotIn('localStorage',once)
        self.assertNotIn('Authorization',once)
        self.assertNotIn('document.cookie',once)

    def test_redirects_and_missing_receiver_are_not_instrumented(self):
        page='<meta http-equiv="refresh" content="0;url=elsewhere">'
        self.assertEqual(instrument_html(page,'https://example/pixel.gif'),page)
        self.assertEqual(instrument_html('<body>news</body>',''),'<body>news</body>')
        self.assertEqual(instrument_html('fixture','https://example/pixel.gif'),'fixture')


if __name__ == '__main__':
    unittest.main()
