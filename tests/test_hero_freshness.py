import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aidaily.ai_news import visuals, hero_validation as gate

class HeroFreshnessTests(unittest.TestCase):
    def brief(self):
        d='2026-10-12'
        return {'date':d,'stories':[{'headline':'news','body':'current news'}],
                'customer_story':{'headline':'customer','body':'feedback','report_date':d},
                'youtube_story':{'headline':'video','body':'report','report_date':d}}

    def test_yesterday_youtube_never_falls_back(self):
        with patch('aidaily.publishing.search_index.load_individual_reports',return_value=[{'date':'2026-10-11','title':'old','cat':'tech'}]):
            self.assertIsNone(visuals._today_youtube_story('2026-10-12'))

    def test_injected_stale_source_prevents_external_generation(self):
        b=self.brief();b['customer_story']['report_date']='2026-10-11'
        with tempfile.TemporaryDirectory() as td, patch.object(visuals.CLIENT,'generate') as generate:
            p=Path(td)/'hero.png';p.write_bytes(b'old')
            with self.assertRaises(ValueError):visuals.generate_hero(p,b)
            generate.assert_not_called();self.assertEqual(p.read_bytes(),b'old')
            self.assertFalse(json.loads(gate.manifest_path(p).read_text())['active'])

    def test_blank_and_forged_prepared_sources_rejected(self):
        b=self.brief();b['customer_story']['body']='  '
        with self.assertRaises(ValueError):visuals._selected_stories(b)
        b=self.brief();b['cover_stories']=[b['youtube_story']]*3
        with self.assertRaises(ValueError):visuals._selected_stories(b)

    def test_reuse_requires_date_hash_and_current_sources(self):
        b=self.brief();sources=visuals._selected_stories(b)
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'hero.png';p.write_bytes(b'image')
            self.assertFalse(gate.validate_hero(p,b));gate.write_manifest(p,b['date'],sources)
            self.assertTrue(gate.validate_hero(p,b));self.assertTrue(gate.validate_published_hero(p,b['date']))
            changed=copy.deepcopy(b);changed['customer_story']['body']='new input'
            self.assertFalse(gate.validate_hero(p,changed));self.assertFalse(gate.validate_published_hero(p,'2026-10-13'))
            p.write_bytes(b'bad');self.assertFalse(gate.validate_hero(p,b))

    def test_override_and_inactive_preserve_original(self):
        b=self.brief()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'hero.png';p.write_bytes(b'image');gate.write_manifest(p,b['date'],visuals._selected_stories(b))
            m=Path(td)/'cover.manifest.json';m.write_bytes(gate.manifest_path(p).read_bytes())
            self.assertTrue(gate.validate_published_hero(p,b['date'],manifest_path_override=m))
            r=json.loads(m.read_text());r['sources'][0]['date']='2026-10-11';m.write_text(json.dumps(r))
            self.assertFalse(gate.validate_published_hero(p,b['date'],manifest_path_override=m))
            gate.invalidate_hero(p,b['date'],'failed');self.assertFalse(gate.validate_hero(p,b));self.assertEqual(p.read_bytes(),b'image')

    def test_mocked_generation_records_sources_and_hash(self):
        import base64
        png=base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aRlwAAAAASUVORK5CYII=")
        b=self.brief()
        with tempfile.TemporaryDirectory() as td, patch.object(visuals.CLIENT, 'generate', return_value=(png, {})), patch.object(visuals.visual_brief, 'enrich_stories'), patch.object(visuals.content_settings, 'load', return_value={}):
            p=Path(td)/'hero.png';visuals.generate_hero(p,b)
            self.assertTrue(gate.validate_hero(p,b))
            metadata=json.loads(gate.manifest_path(p).read_text())
            self.assertEqual([x['role'] for x in metadata['sources']],list(gate.ROLES))
