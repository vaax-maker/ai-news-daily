import datetime,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest import mock
from aidaily.publishing.pipeline import ensure_release_allowed
from aidaily import config
class AuthorizationTests(unittest.TestCase):
 def test_pending_public_release_is_not_bypassed_by_generation_approval(self):
  with tempfile.TemporaryDirectory()as folder:
   root=Path(folder);(root/'customer_stories/newsroom').mkdir(parents=True)
   payload=root/'customer_stories'/(datetime.date.today().isoformat()+'.json');payload.write_text(json.dumps({'gen':{'schema_version':2,'items':[]}}))
   auth=root/'customer_stories/newsroom/release-authorization.json'
   with mock.patch.object(config,'DATA_ROOT',root):
    with self.assertRaises(RuntimeError):ensure_release_allowed()
    auth.write_text(json.dumps({'policy':'edition_approved','edition_sha256':hashlib.sha256(payload.read_bytes()).hexdigest()}))
    ensure_release_allowed()
    payload.write_text(payload.read_text()+' ')
    with self.assertRaises(RuntimeError):ensure_release_allowed()
 def test_legacy_without_new_payload_keeps_existing_rules(self):
  with tempfile.TemporaryDirectory()as folder:
   with mock.patch.object(config,'DATA_ROOT',Path(folder)):ensure_release_allowed()
