import json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import browse
NAME='home-20261023T010000Z-0123abcd'
ITEMS=[('d','Projects',0),('d','Projects/app',0),('-','Projects/app/main.py',12),('-','Projects/app/sh:*',3),('l','Projects/link',0),('-','notes.txt',5),('d','Documents',0),('-','line\nbreak',1)]

def lines():return [json.dumps({'type':t,'path':p,'size':s,'mtime':'2026-10-23T01:00:00'}).encode()+b'\n' for t,p,s in ITEMS]

class Browse(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.state=patch.object(browse,'STATE',self.root/'state');self.state.start()
 def tearDown(self):self.state.stop();self.tmp.cleanup()
 def test_paths_stay_inside_home(self):
  self.assertEqual(browse.clean_path('./Projects//app/'),'Projects/app');self.assertEqual(browse.clean_path(''),'')
  for bad in ['/etc','Projects/../../etc','a\0b',None]:
   with self.assertRaises(ValueError):browse.clean_path(bad)
  with self.assertRaises(ValueError):browse.archive_name('home-1; rm -rf ~')
 def test_index_lists_one_folder_with_directories_first(self):
  browse.build_index({},None,NAME,lines())
  root=browse.listing(NAME,'')
  self.assertEqual([(x['name'],x['type']) for x in root['entries']],[('Documents','d'),('Projects','d'),('line\nbreak','-'),('notes.txt','-')])
  self.assertEqual([x['name'] for x in browse.listing(NAME,'Projects/app')['entries']],['main.py','sh:*'])
  with self.assertRaisesRegex(ValueError,'Folder not found'):browse.listing(NAME,'notes.txt')
  self.assertEqual((root['files'],root['bytes']),(None,None))
  folder=browse.listing(NAME,'Projects');self.assertEqual((folder['files'],folder['bytes']),(3,15))
  self.assertEqual(browse.entry(NAME,'Projects/app/main.py'),('-',12))
 def test_subtree_excludes_sibling_with_shared_prefix(self):
  browse.build_index({},None,NAME,lines()+[json.dumps({'type':'-','path':'Projects-old/x','size':100}).encode(),json.dumps({'type':'d','path':'Projects-old','size':0}).encode()])
  self.assertEqual(browse.entry(NAME,'Projects'),('d',15))
 def test_unindexed_archive_needs_borg(self):
  self.assertIsNone(browse.indexed(NAME))
  with self.assertRaisesRegex(RuntimeError,'not indexed'):browse.listing(NAME,'')
 def test_failed_index_build_leaves_no_partial_index(self):
  with self.assertRaises(ValueError):browse.build_index({},None,NAME,lines()+[b'not json\n'])
  self.assertIsNone(browse.indexed(NAME));self.assertEqual(list((self.root/'state/index').iterdir()),[])
 def test_only_newest_indexes_are_kept(self):
  names=['home-2026102%dT010000Z-0123abcd'%d for d in range(7)]
  for n in names:browse.build_index({},None,n,lines())
  self.assertEqual(sorted(p.stem for p in (self.root/'state/index').glob('*.sqlite')),names[-browse.KEEP_INDEXES:])
 def test_restore_never_overwrites_or_follows_links(self):
  base=self.root/'Restored';browse.build_index({},None,NAME,lines());calls=[]
  def borg(c,args,label,cwd=None,output=True):
   calls.append((args,cwd));target=Path(cwd)/args[-1][3:];target.parent.mkdir(parents=True,exist_ok=True);target.write_text('x')
  c={'repository':'/repo'}
  self.assertEqual(browse.restore(c,borg,NAME,'Projects/app/sh:*',base),base/NAME/'Projects/app/sh:*')
  self.assertEqual(calls[0][0][-1],'pp:Projects/app/sh:*');self.assertEqual(calls[0][1],base/NAME)
  with self.assertRaisesRegex(ValueError,'Already restored'):browse.restore(c,borg,NAME,'Projects/app/sh:*',base)
  (base/NAME/'Documents').symlink_to(self.root)
  with self.assertRaisesRegex(ValueError,'not a plain folder'):browse.restore_destination(NAME,'Documents/x',base)
  with self.assertRaisesRegex(ValueError,'not found'):browse.restore(c,borg,NAME,'missing',base)
  with self.assertRaisesRegex(ValueError,'Choose a file'):browse.restore(c,borg,NAME,'',base)
  self.assertEqual(len(calls),1)
  with patch.object(browse,'HEADROOM',10**18),self.assertRaisesRegex(ValueError,'Not enough free space'):browse.restore(c,borg,NAME,'notes.txt',base)
  self.assertFalse((base/NAME/'notes.txt').exists())
 def test_archives_filters_and_caches_newest_first(self):
  out=json.dumps({'archives':[{'name':'home-20261022T010000Z-0123abcd','time':'t1'},{'name':'other','time':'t0'},{'name':NAME,'time':'t2'}]})
  found=browse.archives({'repository':'/repo'},lambda c,args,label:out)
  self.assertEqual([x['name'] for x in found],[NAME,'home-20261022T010000Z-0123abcd'])
  self.assertEqual(json.loads((self.root/'state/archives.json').read_text())['archives'],found)
if __name__=='__main__':unittest.main()
