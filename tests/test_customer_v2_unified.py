import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from aidaily import config

ORIGINAL_DEPLOY=config.YOUTUBE_SUMMARIES_REPOSITORY/'deploy'
if str(ORIGINAL_DEPLOY) not in sys.path:sys.path.insert(0,str(ORIGINAL_DEPLOY))
RENDERER=Path(os.environ.get('AIDAILY_TEST_UNIFIED_RENDERER',str(ORIGINAL_DEPLOY/'render_unified.py')))
spec=importlib.util.spec_from_file_location('customer_v2_unified_renderer',RENDERER)
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)

class CustomerV2UnifiedTests(unittest.TestCase):
    def row(self,identity='one'):
        today=datetime.date.today().isoformat()
        return dict(id='customer_story:'+today+':'+identity,story_id=identity,kind='customer_story',
            source='고객사용기',pub='고객사용기',cat='tech',date=today,title='Grok에 맡기는 업무 '+identity,
            summary='메인에서 잘라 보여주던 미리보기.',summary_bullets=['메인에서 잘라 보여주던 미리보기.'],
            channel='오픈채팅 · 모임 1',url='https://example.org/기술.html?date='+today+'&item=story-'+identity,
            story_content={'background':[{'text':'공식 문서는 작업의 승인 구조를 설명한다.','url':'https://docs.example.org/facts','label':'공식 문서'}],
                'voices':[{'text':'일부 기능은 동작했다. 그러나 같은 조건에서 작업 전체를 완료한 것은 아니다.','source':'오픈채팅 · 모임 1'}],
                'timeline':[{'text':'작업 조건을 다시 확인하고 실제 입력으로 시험했다.'}],
                'commentary':'요청한 결과가 나왔는지 입력부터 확인해야 한다.',
                'related_links':[{'url':'https://docs.example.org/faq','label':'관련 FAQ'}]})
    def render(self,rows):
        tokens=renderer.load_tokens(ORIGINAL_DEPLOY/'design/tokens.json')
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(renderer,'snapshot_rail',return_value=''),mock.patch.object(renderer,'load_customer_date_override',return_value=None):
            renderer.render_tech(tokens,rows,Path(tmp))
            return (Path(tmp)/'기술.html').read_text()
    def client(self,page,rows):
        node=shutil.which('node')
        if not node:self.skipTest('Node runtime unavailable')
        helpers=re.search(r'function storySourceUrl\(value\)\{.*?(?=function dailyWrapHtml)',page,re.S)
        self.assertIsNotNone(helpers)
        escape=re.search(r'function esc\(s\)\{[^\n]+\}',page).group(0)
        script=escape+"\nvar TK={line:'line',ink:'ink',muted:'muted'};function articleBadge(r){return '<span>#01</span>';}function shareIcon(tone,url){return '<button data-share=\\\"'+esc(url)+'\\\">공유</button>';}function shareUrl(r){return r.url;}\n"+helpers.group(0)+"\nconsole.log(customerGroupBlock("+json.dumps(rows,ensure_ascii=False)+",'color'));"
        result=subprocess.run([node,'-e',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        return result.stdout
    def assert_full_story(self,body):
        self.assertIn('확인된 사실',body);self.assertIn('사용자 목소리',body)
        self.assertIn('그러나 같은 조건에서 작업 전체를 완료한 것은 아니다.',body)
        self.assertIn('작업 조건을 다시 확인하고 실제 입력으로 시험했다.',body)
        self.assertIn('요청한 결과가 나왔는지 입력부터 확인해야 한다.',body)
        self.assertIn('https://docs.example.org/facts',body)
        self.assertIn('https://docs.example.org/faq',body)
        self.assertIn('오픈채팅 · 모임 1',body)
        self.assertNotIn('기사 읽기',body)
        self.assertIn('display:flex;flex-direction:column',body)
        article=re.search(r'<article class="customer-story-full".*?</article>',body,re.S).group(0)
        self.assertNotIn('메인에서 잘라 보여주던 미리보기.',article)
        heading=re.search(r'<h3[^>]*>(.*?)</h3>',article,re.S).group(1)
        self.assertNotIn('<a ',heading)
    def test_ssr_shows_complete_article_in_single_column_without_detail_cta(self):
        page=self.render([self.row('one'),self.row('two')]);body=page.split('<script',1)[0]
        self.assert_full_story(body)
        from html.parser import HTMLParser
        class VisibleText(HTMLParser):
            def __init__(self): super().__init__(); self.hidden=False; self.text=[]
            def handle_starttag(self,tag,attrs):
                if tag in ('style','script'): self.hidden=True
            def handle_endtag(self,tag):
                if tag in ('style','script'): self.hidden=False
            def handle_data(self,data):
                if not self.hidden:self.text.append(data)
        visible=VisibleText();visible.feed(page)
        self.assertNotIn('.customer-story-full h4', ''.join(visible.text))
        self.assertEqual(len(re.findall(r'<article class="customer-story-full"',body)),2)
        self.assertIn('누적 취재 · 하루 최대 2편',body)
        self.assertNotIn('출처별 최대 4개',body)
    def test_dynamic_date_switch_executes_full_article_rendering(self):
        rows=[self.row('one'),self.row('two')]
        body=self.client(self.render(rows),rows)
        self.assert_full_story(body)
        self.assertEqual(len(re.findall(r'<article class="customer-story-full"',body)),2)
    def test_ssr_and_client_escape_text_and_reject_dangerous_source_links(self):
        row=self.row();row['title']='<img src=x onerror=alert(1)>'
        row['story_content']['voices'][0]['text']='<script>alert(2)</script> 그러나 완료한 것은 아니다.'
        row['story_content']['background'] += [
            {'text':'unsafe fact should not display','url':'javascript:alert(3)'},
            {'text':'credentialed fact should not display','url':'https://u:p@example.org'}]
        row['story_content']['related_links'] += [{'url':'data:text/html,bad','label':'bad link'}]
        page=self.render([row])
        for body in (page.split('<script',1)[0],self.client(page,[row])):
            self.assertNotIn('<script>',body);self.assertNotIn('<img ',body)
            self.assertIn('&lt;script&gt;',body)
            self.assertNotIn('javascript:',body);self.assertNotIn('data:text/html',body)
            self.assertNotIn('unsafe fact should not display',body)
            self.assertNotIn('credentialed fact should not display',body)
            self.assertNotIn('기사 읽기',body)
    def test_legacy_source_group_layout_remains(self):
        row=self.row();row.pop('story_id');row.pop('story_content')
        body=self.render([row]).split('<script',1)[0]
        self.assertIn('출처별 최대 4개',body)
        self.assertIn('주요 주제 1개',body)
        self.assertNotIn('<article class="customer-story-full"',body)

if __name__=='__main__':unittest.main()
