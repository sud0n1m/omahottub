import hashlib,json,os,sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import common,backup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import watch
import importlib.util
spec=importlib.util.spec_from_file_location('view',Path(__file__).resolve().parents[1]/'status.py');view=importlib.util.module_from_spec(spec);spec.loader.exec_module(view)
AT=datetime(2026,10,28,20,tzinfo=timezone.utc)

def write_config(d,**extra):
    p=Path(d)/'config.json'
    p.write_text(json.dumps(dict(backend='borg',repository='ssh://u@nas.example/r',ssh_key='/k/nas',known_hosts='/k/hosts',password_file='/k/pw',borg='/usr/bin/true',**extra)))
    return common.config(p)

class Config(unittest.TestCase):
    def test_primary_profile_is_unchanged_by_destinations(self):
        with tempfile.TemporaryDirectory() as d:
            plain=write_config(d);multi=write_config(d,destinations=[dict(name='offsite',repository='ssh://x@off.example/./repo',ssh_key='/k/off',known_hosts='/k/offhosts')])
        old=hashlib.sha256(json.dumps({k:plain[k] for k in ['repository','exclude_prefixes','exclude_directories']},sort_keys=True).encode()).hexdigest()
        self.assertEqual(plain['profile'],old);self.assertEqual(multi['profile'],old)
        self.assertEqual([t['name'] for t in multi['targets']],['nas','offsite'])
        off=multi['targets'][1]
        self.assertEqual((off['receipt'],off['check'],off['label'],off['password_file'],off['verify_days']),('last-success.offsite.json','last-check.offsite.json','-offsite','/k/pw',90))
        self.assertNotEqual(off['profile'],old)
    def test_bad_destinations_refused(self):
        good=dict(repository='ssh://x@off.example/./repo',ssh_key='/k/off',known_hosts='/k/h')
        for bad in [[dict(good,name='Off Site')],[dict(good,name='nas')],[dict(good,name='a'),dict(good,name='a')],[dict(good,name='a',repository='/local')],[dict(good,name='a',ssh_key='')],[dict(good,name='a',verify_days=0)],'x']:
            with self.subTest(bad),tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):write_config(d,destinations=bad)

class Run(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=Path(self.tmp.name)
        self.c=dict(profile='p1',repository='ssh://u@nas/r',require_ac=False)
        self.c['targets']=[dict(self.c,name='nas',receipt='last-success.json',check='last-check.json',label=''),
            dict(self.c,name='offsite',repository='ssh://x@off/./repo',profile='p2',receipt='last-success.offsite.json',check='last-check.offsite.json',label='-offsite')]
        self.home='/var/lib/omarchy-backup/home/'+Path.home().name
    def tearDown(self):self.tmp.cleanup()
    def go(self,reach,capture_fail=()):
        captured=[];events=[]
        def capture(t,source,name):
            if t['name'] in capture_fail:raise RuntimeError('boom')
            captured.append((t['name'],name))
        with patch.object(backup,'STATE',self.state),patch.object(backup,'reachable',side_effect=lambda t:t['name'] in reach),\
             patch.object(backup,'snapshot',side_effect=lambda a:self.home if a=='create' else '') as snap,\
             patch.object(backup,'capture',side_effect=capture),patch.object(backup,'emit',side_effect=lambda s,r,c,**k:events.append((s,r,k.get('destination')))):
            try:backup.run(self.c);err=None
            except RuntimeError as e:err=str(e)
        return captured,events,err,[x.args[0] for x in snap.call_args_list]
    def test_unreachable_destination_is_skipped_not_failed(self):
        captured,events,err,snap=self.go({'offsite'})
        self.assertIsNone(err);self.assertEqual([n for n,_ in captured],['offsite']);self.assertEqual(events[-1][:2],('success','saved'));self.assertEqual(snap,['create','delete'])
    def test_one_snapshot_feeds_every_destination_with_one_archive_name(self):
        captured,_,err,snap=self.go({'nas','offsite'})
        self.assertIsNone(err);self.assertEqual([n for n,_ in captured],['nas','offsite']);self.assertEqual(len({a for _,a in captured}),1);self.assertEqual(snap,['create','delete'])
    def test_failure_of_one_destination_does_not_stop_the_other(self):
        captured,events,err,snap=self.go({'nas','offsite'},capture_fail={'nas'})
        self.assertEqual([n for n,_ in captured],['offsite']);self.assertIn('Backup failed for nas',err);self.assertEqual(snap,['create','delete'])
        self.assertNotIn(('success','saved',None),events)
    def test_nothing_reachable_takes_no_snapshot(self):
        captured,events,err,snap=self.go(set())
        self.assertEqual((captured,snap,err),([],[],None));self.assertEqual(events,[('skipped','network',None)])
    def test_only_due_destinations_run(self):
        (self.state/'last-success.json').write_text(json.dumps({'finished':datetime.now().astimezone().isoformat(),'profile':'p1'}))
        with patch.object(backup,'due',side_effect=lambda r,t,at=None:t['name']=='offsite'):
            captured,_,err,_=self.go({'nas','offsite'})
        self.assertEqual([n for n,_ in captured],['offsite'])

class Watch(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.state=Path(self.tmp.name);self.p=patch.object(watch,'STATE',self.state);self.p.start()
        self.c={'profile':'p1','targets':[dict(name='nas',receipt='last-success.json',check='last-check.json',verify_days=30),dict(name='offsite',receipt='last-success.offsite.json',check='last-check.offsite.json',verify_days=90)]}
    def tearDown(self):self.p.stop();self.tmp.cleanup()
    def put(self,name,hours):(self.state/name).write_text(json.dumps({'finished':(AT-timedelta(hours=hours)).isoformat()}))
    def test_travel_keeps_backups_fresh_but_flags_home_copy_later(self):
        self.put('last-success.json',24*3);self.put('last-success.offsite.json',10);self.put('last-check.json',1);self.put('last-check.offsite.json',1)
        self.assertEqual(watch.watch(self.c,AT,lambda t,b:None),[])
        self.put('last-success.json',24*9);bodies={}
        self.assertEqual(watch.watch(self.c,AT,lambda t,b:bodies.update({t:b})),['behind']);self.assertIn('nas',bodies['Some backups are behind'])
    def test_stale_only_when_no_destination_saved(self):
        self.put('last-success.json',40);self.put('last-success.offsite.json',38);self.put('last-check.json',1);self.put('last-check.offsite.json',1)
        self.assertEqual(watch.watch(self.c,AT,lambda t,b:None),['stale'])
    def test_overdue_check_names_the_destination(self):
        self.put('last-success.json',2);self.put('last-success.offsite.json',2);self.put('last-check.json',24);self.put('last-check.offsite.json',24*110);bodies={}
        self.assertEqual(watch.watch(self.c,AT,lambda t,b:bodies.update({t:b})),['unverified']);self.assertIn('for offsite',bodies['Backup data check overdue'])
    def test_verify_due_reads_each_destinations_own_record(self):
        nas=dict(self.c['targets'][0],profile='p1');off=dict(self.c['targets'][1],profile='p2')
        (self.state/'last-check.json').write_text(json.dumps({'finished':(AT-timedelta(days=1)).isoformat(),'profile':'p1'}))
        self.assertFalse(watch.verify_due(nas,AT));self.assertTrue(watch.verify_due(off,AT))
        (self.state/'last-check.offsite.json').write_text(json.dumps({'finished':(AT-timedelta(days=60)).isoformat(),'profile':'p2'}))
        self.assertFalse(watch.verify_due(off,AT));self.assertTrue(watch.verify_due(off,AT+timedelta(days=31)))
    def test_failure_alert_carries_the_reason(self):
        self.put('last-success.json',2);self.put('last-success.offsite.json',2);self.put('last-check.json',1);self.put('last-check.offsite.json',1)
        (self.state/'status.json').write_text(json.dumps({'state':'failed','reason':'Backup failed for offsite; inspect private backup logs'}));bodies={}
        watch.watch(self.c,AT,lambda t,b:bodies.update({t:b}));self.assertTrue(bodies['Backup failed'].startswith('Backup failed for offsite'))

class Panel(unittest.TestCase):
    def test_offsite_save_counts_while_away_and_details_list_each(self):
        now=datetime.now(timezone.utc);c={'profile':'p1','due_hour':0,'name':'nas'};off={'name':'offsite','profile':'p2','due_hour':0}
        svc={'ActiveState':'inactive'};tmr={'ActiveState':'active','UnitFileState':'enabled'}
        old={'profile':'p1','finished':(now-timedelta(days=3)).isoformat(),'stats':{'deduplicated_size':1}}
        fresh={'profile':'p2','finished':now.isoformat(),'stats':{'deduplicated_size':5*10**8}}
        data=view.borg_view({'state':'skipped','reason':'network','profile':'p1'},old,{},c,svc,tmr,now,[(off,fresh,{})])
        self.assertEqual(data['state'],'complete');self.assertEqual(data['lastSize'],'0.50 GB')
        self.assertTrue(data['destinations'].startswith('nas: ') and '\noffsite: Today' in data['destinations'])
        data=view.borg_view({'state':'skipped','reason':'network','profile':'p1'},old,{},c,svc,tmr,now,[(off,{},{})])
        self.assertEqual((data['state'],data['headline']),('nas','Waiting for network'))
        self.assertEqual(view.borg_view({},old,{},c,svc,tmr,now)['destinations'],'')
if __name__=='__main__':unittest.main()
