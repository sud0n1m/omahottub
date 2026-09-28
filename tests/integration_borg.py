#!/usr/bin/env python3
"""Real Borg 1.4 capture, no-change incremental, fresh-cache restore and data check.
Synthetic only. Set BORG_TEST_BINARY to a trusted Borg executable.
"""
import hashlib,json,os,secrets,shutil,sqlite3,stat,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import backup,common

def manifest(root):
 rows={};inodes={}
 for p in sorted(root.rglob('*')):
  rel=str(p.relative_to(root));s=p.lstat();row={'mode':stat.S_IMODE(s.st_mode),'xattrs':{k:os.getxattr(p,k,follow_symlinks=False).hex() for k in os.listxattr(p,follow_symlinks=False)}}
  if p.is_symlink():row['link']=os.readlink(p)
  elif p.is_dir():row['directory']=True
  else:row.update(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),link_to=inodes.setdefault(s.st_ino,rel))
  rows[rel]=row
 return rows

os.umask(0o077)
with tempfile.TemporaryDirectory(prefix='omarchy-backup-integration-') as tmp:
 root=Path(tmp);backup.STATE=root/'state';backup.STATE.mkdir();source=root/'source';source.mkdir()
 for name in ['file','line\nbreak','--name','app/IndexedDB/store']:
  p=source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(secrets.token_bytes(1024))
 (source/'private').write_text('synthetic');(source/'private').chmod(0o600);os.setxattr(source/'private','user.test',b'yes');os.link(source/'private',source/'hardlink');(source/'link').symlink_to('/not-present');(source/'empty').mkdir()
 with sqlite3.connect(source/'state.sqlite') as db:db.execute('CREATE TABLE t(x)');db.execute('INSERT INTO t VALUES (42)')
 expected=manifest(source)
 for name in ['password','key','hosts']:(root/name).write_text(secrets.token_hex(32));(root/name).chmod(0o600)
 c={'borg':os.environ.get('BORG_TEST_BINARY','/usr/bin/borg'),'repository':str(root/'repository'),'profile':'fixture','password_file':str(root/'password'),'ssh_key':str(root/'key'),'known_hosts':str(root/'hosts'),'exclude_prefixes':common.PREFIXES,'exclude_directories':common.DIRECTORIES}
 backup.borg(c,['init','--encryption=repokey',c['repository']],'init')
 first=backup.capture(c,source,'home-20260927T000000Z-00000001');second=backup.capture(c,source,'home-20260927T000000Z-00000002');assert second['stats']['deduplicated_size']==0
 # Start with empty client state, relying on the encrypted repository key.
 shutil.rmtree(backup.STATE/'cache');shutil.rmtree(backup.STATE/'security')
 restored=root/'restored';restored.mkdir();backup.borg(c,['extract',c['repository']+'::'+first['archive']],'restore',restored)
 assert manifest(restored)==expected
 with sqlite3.connect(restored/'state.sqlite') as db:assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)];assert db.execute('SELECT x FROM t').fetchall()==[(42,)]
 backup.borg(c,['check','--verify-data',c['repository']],'check')
 print(json.dumps({'initial_backup':True,'unchanged_new_data_bytes':second['stats']['deduplicated_size'],'fresh_cache_full_restore':True,'hashes_modes_xattrs_links_match':True,'sqlite_integrity':True,'full_data_check':True}))
