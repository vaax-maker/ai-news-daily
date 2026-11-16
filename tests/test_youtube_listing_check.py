import tempfile,unittest
from pathlib import Path
from aidaily.publishing.youtube_listing_check import verify

class PublicationTests(unittest.TestCase):
    def test_existing_list_is_not_proof_this_report_was_published(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);date='2026-10-28';slug=date+'-new-video'
            for kind in ('ai','econ'):(root/f'{date}-daily-brief-{kind}.html').write_text('<html>Existing reports<!-- '+slug+'.html --></html>')
            (root/(slug+'.html')).write_text('<html>New report</html>')
            (root/'assets/ig').mkdir(parents=True);(root/'assets/ig'/(slug+'.jpg')).write_bytes(b'\xff\xd8fixture')
            with self.assertRaisesRegex(RuntimeError,'missing from daily list'):verify(root,date,[slug])
            for wrong in ['/wrong/'+slug+'.html', 'https://other.invalid/'+slug+'.html']:
                (root/f'{date}-daily-brief-ai.html').write_text('<a href="'+wrong+'">Wrong</a>')
                with self.assertRaisesRegex(RuntimeError,'missing from daily list'):verify(root,date,[slug])
            (root/f'{date}-daily-brief-ai.html').write_text('<a href="./'+slug+'.html">Report</a>')
            self.assertTrue(verify(root,date,[slug]))
            with self.assertRaisesRegex(RuntimeError,'date differs'):verify(root,date,['2026-10-27-video'])

    def test_missing_category_brief_is_not_a_failure(self):
        # A category with zero items that day has no brief file at all (by design,
        # see render_briefs_lean.py). verify() must not crash on that absence.
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);date='2026-11-17';slug=date+'-new-video'
            (root/f'{date}-daily-brief-ai.html').write_text('<a href="./'+slug+'.html">Report</a>')
            (root/(slug+'.html')).write_text('<html>New report</html>')
            (root/'assets/ig').mkdir(parents=True);(root/'assets/ig'/(slug+'.jpg')).write_bytes(b'\xff\xd8fixture')
            self.assertTrue(verify(root,date,[slug]))

    def test_no_category_briefs_at_all_is_a_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);date='2026-11-17';slug=date+'-new-video'
            with self.assertRaisesRegex(RuntimeError,'No daily brief list exists'):verify(root,date,[slug])
