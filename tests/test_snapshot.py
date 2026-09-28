import importlib.util,os,pwd,sys,tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('snapshot',Path(__file__).resolve().parents[1]/'backend/snapshot.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class Snapshot(unittest.TestCase):
 def test_user_owned_root_path_refused(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(RuntimeError):s.trusted(Path(d))
 def test_arbitrary_arguments_refused(self):
  with patch.object(os,'geteuid',return_value=0),patch.object(sys,'argv',['snapshot','delete','/home']):
   with self.assertRaises(SystemExit):s.main()
 def test_identity_mismatch_never_deletes(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);target=base/'home';target.mkdir();cfg=base/'config';user=pwd.getpwuid(os.getuid());cfg.write_text(json.dumps({'user':user.pw_name}));(base/'snapshot.json').write_text(json.dumps({'uuid':'expected'}))
   with patch.multiple(s,BASE=base,TARGET=target,CONFIG=cfg),patch.object(s,'trusted'),patch.object(s,'identity',return_value='different'),patch.object(s,'call',return_value='btrfs') as call,patch.object(os,'geteuid',return_value=0),patch.object(sys,'argv',['snapshot','delete']):
    with self.assertRaisesRegex(RuntimeError,'identity mismatch'):s.main()
    self.assertFalse(any('delete' in x.args[0] for x in call.call_args_list))
if __name__=='__main__':unittest.main()
