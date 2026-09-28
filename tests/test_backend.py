import importlib.util,json,os,stat,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import common,backup
spec=importlib.util.spec_from_file_location('view',Path(__file__).resolve().parents[1]/'status.py');view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)

class Backend(unittest.TestCase):
 def test_scope_keeps_databases_and_does_not_follow_symlinks(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for name in ['db.sqlite','db.sqlite-wal','app/IndexedDB/store','line\nbreak','--name','.cache/excluded','app/node_modules/pkg']:
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture')
   (root/'external').symlink_to('/etc')
   rows=set(common.selected(root,{'exclude_prefixes':common.PREFIXES,'exclude_directories':common.DIRECTORIES}))
   self.assertTrue({'db.sqlite','db.sqlite-wal','app/IndexedDB/store','line\nbreak','--name','external'}<=rows)
   self.assertNotIn('.cache/excluded',rows);self.assertFalse(any(x.startswith('external/') for x in rows))
 def test_scope_refuses_nested_subvolume_placeholder(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);child=root/'nested';child.mkdir();original=Path.lstat
   def lstat(p):
    s=original(p)
    if p==child:
     values=list(s);values[1]=2;return os.stat_result(values)
    return s
   with patch.object(Path,'lstat',lstat):
    with self.assertRaises(RuntimeError):list(common.selected(root,{'exclude_prefixes':[],'exclude_directories':[]}))
 def test_due_rejects_other_profile_and_future_receipts(self):
  now=datetime(2026,9,27,20,tzinfo=timezone.utc);c={'profile':'one','due_hour':18}
  self.assertFalse(backup.due({'profile':'one','finished':now.isoformat()},c,now))
  self.assertTrue(backup.due({'profile':'two','finished':now.isoformat()},c,now))
  self.assertTrue(backup.due({'profile':'one','finished':(now+timedelta(hours=1)).isoformat()},c,now))
 def test_backup_success_does_not_claim_verification(self):
  now=datetime.now(timezone.utc);c={'profile':'one','due_hour':0};receipt={'profile':'one','finished':now.isoformat(),'stats':{'deduplicated_size':0}}
  service={'ActiveState':'inactive'};timer={'ActiveState':'active','UnitFileState':'enabled'}
  data=view.borg_view({},receipt,{},c,service,timer,now)
  self.assertEqual(data['state'],'complete');self.assertFalse(data['checksPassed']);self.assertEqual(data['lastSize'],'0.00 GB')
  data=view.borg_view({'profile':'one','state':'failed'},receipt,{},c,service,timer,now)
  self.assertEqual(data['state'],'failure');self.assertNotEqual(data['lastSuccess'],'None recorded')
 def test_failure_always_cleans_snapshot(self):
  c={'profile':'one','require_ac':False}
  expected='/var/lib/omarchy-backup/home/'+Path.home().name
  with patch.object(backup,'read',return_value={}),patch.object(backup,'emit'),patch.object(backup,'snapshot',side_effect=[expected,'']) as snap,patch.object(backup,'capture',side_effect=RuntimeError('fixture')):
   with self.assertRaises(RuntimeError):backup.run(c)
   self.assertEqual([x.args[0] for x in snap.call_args_list],['create','delete'])
 def test_no_snapshot_for_covered_slot(self):
  with patch.object(backup,'read',return_value={}),patch.object(backup,'due',return_value=False),patch.object(backup,'emit'),patch.object(backup,'snapshot') as snap:
   backup.run({'profile':'one'});snap.assert_not_called()
 def test_cleanup_failure_stays_visible_until_explicit_recovery(self):
  with tempfile.TemporaryDirectory() as d,patch.object(backup,'STATE',Path(d)),patch.object(backup,'read',return_value={}),patch.object(backup,'emit'),patch.object(backup,'capture') as capture:
   c={'profile':'one','require_ac':False};expected='/var/lib/omarchy-backup/home/'+Path.home().name
   with patch.object(backup,'snapshot',side_effect=[expected,RuntimeError('cleanup failed')]):
    with self.assertRaises(RuntimeError):backup.run(c)
   self.assertTrue((Path(d)/'cleanup-needed.json').exists())
   with self.assertRaisesRegex(RuntimeError,'cleanup requires attention'):backup.run(c)
   self.assertEqual(capture.call_count,1)
 def test_environment_does_not_inherit_other_borg_secrets(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d)
   for name in ['key','password','hosts']:(root/name).write_text('fixture');(root/name).chmod(0o600)
   c={'ssh_key':str(root/'key'),'password_file':str(root/'password'),'known_hosts':str(root/'hosts')}
   with patch.dict(os.environ,{'BORG_PASSPHRASE':'fixture','BORG_RELOCATED_REPO_ACCESS_IS_OK':'yes'}):
    env=backup.environment(c)
   self.assertNotIn('BORG_PASSPHRASE',env);self.assertNotIn('BORG_RELOCATED_REPO_ACCESS_IS_OK',env)
 def test_invalid_prefix_refused(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'config';p.write_text(json.dumps({'backend':'borg','repository':'ssh://test@example.invalid/repo','ssh_key':'/fixture/key','known_hosts':'/fixture/hosts','password_file':'/fixture/password','borg':'/usr/bin/true','exclude_prefixes':['../secret']}))
   with self.assertRaises(ValueError):common.config(p)
if __name__=='__main__':unittest.main()
