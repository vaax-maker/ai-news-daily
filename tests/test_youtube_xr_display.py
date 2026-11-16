import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import timezone
from aidaily.integrations import youtube
from aidaily.publishing.search_index import load_individual_reports
from aidaily.youtube_summaries.selection import is_xr
DEPLOY=Path.home()/'nlm-infographic/deploy'
def module(name):
    if str(DEPLOY) not in sys.path:sys.path.insert(0,str(DEPLOY))
    spec=importlib.util.spec_from_file_location(name,DEPLOY/(name+'.py'))
    out=importlib.util.module_from_spec(spec);spec.loader.exec_module(out);return out
class XRDisplayTest(unittest.TestCase):
    def test_translated_headline_keeps_original_xr_evidence(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root,'2026-11-04-sample.html').write_text('''<html><head><title>세 기기의 비교 결과</title><meta name="youtube-source-title" content="Meta VR Glasses vs XREAL AURA"></head><body class="cat-tech"><p>YOUTUBE SUMMARIES · 2026-11-04 · Cas and Chary XR</p><p class="lead">원문 요약</p></body></html>''')
            rows=load_individual_reports(root)
            self.assertEqual(len(rows),1)
            self.assertTrue(is_xr(rows[0]))
            briefs=module('render_briefs_lean').collect_items(root,'2026-11-04')
            self.assertEqual(briefs[0]['field'],'XR')
            matrix=module('hero_matrix')
            ordinary={'id':'a','title':'AI 개발','date':'2026-11-04','source':'오늘 유튜브','pub':'개별리포트','cat':'tech'}
            xr={**rows[0],'id':'z','source':'오늘 유튜브'}
            self.assertEqual(matrix.visible_articles([ordinary,xr],'2026-11-04')[0]['id'],'z')
    def test_bounded_video_page_has_actual_date_and_duration(self):
        from types import SimpleNamespace
        payload={'entries':[{'id':'abcdefghijk','title':'VR news','timestamp':1793294088,'duration':600}]}
        with patch.object(youtube.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(payload))) as run:
            rows=youtube.fetch_channel_video_page('channel')
        self.assertEqual(rows[0]['published'].tzinfo,timezone.utc)
        self.assertEqual(rows[0]['duration'],600)
        args=run.call_args.args[0]
        self.assertEqual(args[args.index('--playlist-end')+1],'5')
        self.assertIn('--skip-download',args)
if __name__=='__main__':unittest.main()
