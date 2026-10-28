import json,os,sys,tempfile,time,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import browse,watch
import importlib.util
spec=importlib.util.spec_from_file_location('view',Path(__file__).resolve().parents[1]/'status.py');view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)
AT=datetime(2026,10,28,12,tzinfo=timezone.utc);C={'profile':'p'}

class Watch(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.state=Path(self.tmp.name)
  self.patches=[patch.object(m,'STATE',self.state) for m in (watch,browse)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in self.patches:p.stop()
  self.tmp.cleanup()
 def put(self,name,value):(self.state/name).write_text(json.dumps(value))
 def healthy(self):
  self.put('last-success.json',{'finished':(AT-timedelta(hours=20)).isoformat(),'profile':'p'})
  self.put('last-check.json',{'finished':(AT-timedelta(days=3)).isoformat(),'profile':'p'})
  self.put('status.json',{'state':'success'})
 def test_healthy_backups_stay_quiet(self):
  self.healthy();sent=[]
  self.assertEqual(watch.watch(C,AT,lambda t,b:sent.append(t)),[]);self.assertEqual(sent,[])
 def test_each_problem_notifies_once_then_repeats_and_clears(self):
  self.healthy();self.put('status.json',{'state':'failed'});sent=[]
  note=lambda t,b:sent.append(t)
  watch.watch(C,AT,note);watch.watch(C,AT+timedelta(hours=1),note)
  self.assertEqual(sent,['Backup failed'])
  watch.watch(C,AT+timedelta(hours=13),note);self.assertEqual(sent,['Backup failed']*2)
  # Recovery forgets the episode; the next failure notifies immediately.
  self.put('status.json',{'state':'success'});watch.watch(C,AT+timedelta(hours=14),note)
  self.put('status.json',{'state':'failed'});watch.watch(C,AT+timedelta(hours=15),note)
  self.assertEqual(sent,['Backup failed']*3)
 def test_stale_cleanup_and_overdue_check_are_reported(self):
  self.healthy();self.put('last-success.json',{'finished':(AT-timedelta(hours=37)).isoformat(),'profile':'p'})
  (self.state/'cleanup-needed.json').write_text('{}');self.put('last-check.json',{'finished':(AT-timedelta(days=45)).isoformat(),'profile':'p'})
  bodies={}
  self.assertEqual(watch.watch(C,AT,lambda t,b:bodies.update({t:b})),['cleanup','stale','unverified'])
  self.assertIn('1 days ago',bodies['Backups have stopped'])
  self.assertEqual(watch.watch({'profile':'p','stale_hours':48},AT,lambda t,b:None),['cleanup','unverified'])
 def test_missing_or_broken_state_counts_as_stale(self):
  (self.state/'last-success.json').write_text('{"finished":"not a time"}')
  self.assertEqual(watch.watch(C,AT,lambda t,b:None),['stale'])
 def test_verify_due_monthly_and_for_new_profile(self):
  self.assertTrue(watch.verify_due(C,AT))
  self.put('last-check.json',{'finished':(AT-timedelta(days=29)).isoformat(),'profile':'p'});self.assertFalse(watch.verify_due(C,AT))
  self.assertTrue(watch.verify_due(C,AT+timedelta(days=1)));self.assertTrue(watch.verify_due({'profile':'other'},AT))
 def drill_setup(self,home,changed=False,corrupt=False,lose=False):
  name='home-20261028T010000Z-0123abcd';taken=time.time()+5  # backup taken after the files were written
  for rel in ['a.txt','dir/b.txt']:
   p=home/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('live '+rel)
  rows=[json.dumps(x).encode() for x in [{'type':'d','path':'dir'},{'type':'-','path':'a.txt','size':10},{'type':'-','path':'dir/b.txt','size':14}]]
  browse.build_index({},None,name,rows)
  if changed:(home/'a.txt').write_text('edited later');os.utime(home/'a.txt',(taken+60,taken+60))
  stamp=datetime.fromtimestamp(taken).strftime('%Y-%m-%dT%H:%M:%S.000000')
  def borg(c,args,label,cwd=None,output=True):
   if args[0]=='list':return json.dumps({'archives':[{'name':name,'time':stamp}]})
   for p in args[3:]:
    rel=p[3:]
    if lose and rel=='a.txt':continue
    t=Path(cwd)/rel;t.parent.mkdir(parents=True,exist_ok=True);t.write_text('live '+rel+('!' if corrupt and rel=='a.txt' else ''))
   os.chmod(Path(cwd)/'dir',0o500)
  return borg
 def test_drill_compares_unchanged_files_and_cleans_up(self):
  home=self.state/'home';borg=self.drill_setup(home)
  r=watch.drill({'repository':'/r'},borg,home);self.assertEqual((r['sampled'],r['compared'],r['mismatches']),(2,2,0))
  self.assertFalse((self.state/'drill').exists())
 def test_drill_skips_files_changed_since_backup(self):
  home=self.state/'home';r=watch.drill({'repository':'/r'},self.drill_setup(home,changed=True),home)
  self.assertEqual((r['compared'],r['mismatches']),(1,0))
 def test_drill_fails_on_mismatch_or_missing_file(self):
  for kw,msg in [({'corrupt':True},'1 mismatched'),({'lose':True},'1 missing')]:
   home=self.state/('home-'+msg[2:])
   with self.subTest(msg),self.assertRaisesRegex(RuntimeError,msg):watch.drill({'repository':'/r'},self.drill_setup(home,**kw),home)
 def test_panel_counts_a_recent_monthly_check_for_later_backups(self):
  now=datetime.now(timezone.utc);c={'profile':'p','due_hour':0}
  receipt={'profile':'p','finished':now.isoformat(),'stats':{'deduplicated_size':0}}
  svc={'ActiveState':'inactive'};tmr={'ActiveState':'active','UnitFileState':'enabled'}
  recent={'profile':'p','finished':(now-timedelta(days=20)).isoformat(),'drill':{'sampled':25}}
  data=view.borg_view({},receipt,recent,c,svc,tmr,now)
  self.assertTrue(data['checksPassed']);self.assertEqual(data['verificationSummary'],'✓ Data check and restore drill passed')
  data=view.borg_view({},receipt,dict(recent,finished=(now-timedelta(days=40)).isoformat()),c,svc,tmr,now)
  self.assertFalse(data['checksPassed']);self.assertEqual(data['verificationSummary'],'Monthly data check overdue')
if __name__=='__main__':unittest.main()
