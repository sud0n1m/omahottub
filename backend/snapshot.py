#!/usr/bin/python3 -I
"""Root-owned, fixed-path snapshot helper. No arbitrary commands or paths accepted."""
import fcntl,json,os,pwd,re,stat,subprocess,sys
from pathlib import Path
CONFIG=Path('/etc/omarchy-backup/snapshot.json')
BASE=Path('/var/lib/omarchy-backup')
SOURCE=Path('/home')
TARGET=BASE/'home'
ENV={'PATH':'/usr/bin','LANG':'C','HOME':'/root'}

def trusted(path,directory=True):
    s=path.lstat()
    if s.st_uid!=0 or s.st_mode&0o022 or not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)):raise RuntimeError('Untrusted root-owned path: '+str(path))

def call(args):return subprocess.check_output(args,cwd='/',env=ENV,text=True,stderr=subprocess.STDOUT,timeout=30).strip()

def identity(path):
    out=call(['/usr/bin/btrfs','subvolume','show',str(path)])
    match=re.search(r'^\s*UUID:\s*([a-f0-9-]+)\s*$',out,re.M)
    if not match:raise RuntimeError('Cannot identify snapshot')
    return match.group(1)

def main():
    if os.geteuid()!=0:raise SystemExit('Requires the installed fixed-command sudo rule')
    if sys.argv[1:] not in [['create'],['delete'],['audit']]:raise SystemExit('Only create, delete or audit (no other arguments)')
    for p in [Path('/etc'),CONFIG.parent,Path('/var'),Path('/var/lib'),BASE,SOURCE]:trusted(p)
    trusted(CONFIG,False)
    cfg=json.loads(CONFIG.read_text());user=pwd.getpwnam(cfg['user'])
    if user.pw_uid<1000 or user.pw_dir!='/home/'+user.pw_name:raise RuntimeError('Requires an ordinary /home/USERNAME account')
    if os.environ.get('SUDO_USER',user.pw_name)!=user.pw_name:raise RuntimeError('Wrong snapshot owner')
    if call(['/usr/bin/findmnt','-n','-o','FSTYPE','--target',str(SOURCE)])!='btrfs':raise RuntimeError('/home must be Btrfs')
    identity(SOURCE)  # Require /home itself to be a subvolume root.
    os.umask(0o077)
    with (BASE/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        record=BASE/'snapshot.json';action=sys.argv[1]
        if action=='audit':
            print('ready' if not TARGET.exists() and not record.exists() else 'snapshot state exists; inspect/clean up before the next run');return
        if action=='create':
            if TARGET.exists() or record.exists():raise RuntimeError('Existing snapshot: inspect and use snapshot delete; refusing replacement')
            try:
                call(['/usr/bin/btrfs','subvolume','snapshot','-r',str(SOURCE),str(TARGET)])
                snap_id=identity(TARGET)
                record.write_text(json.dumps({'uuid':snap_id,'source_uuid':identity(SOURCE)})+'\n')
                if call(['/usr/bin/btrfs','property','get','-ts',str(TARGET),'ro'])!='ro=true':raise RuntimeError('Snapshot is not read-only')
            except BaseException:
                # Only delete a target created in this invocation; trusted parent
                # prevents user substitution. If cleanup fails retain its evidence.
                if TARGET.exists():call(['/usr/bin/btrfs','subvolume','delete',str(TARGET)])
                record.unlink(missing_ok=True)
                raise
            print(TARGET/user.pw_name)
        else:
            if not TARGET.exists():
                record.unlink(missing_ok=True);return
            trusted(TARGET)
            trusted(record,False)
            saved=json.loads(record.read_text())
            if identity(TARGET)!=saved['uuid']:raise RuntimeError('Snapshot identity mismatch; refusing deletion')
            if call(['/usr/bin/btrfs','property','get','-ts',str(TARGET),'ro'])!='ro=true':raise RuntimeError('Snapshot is writable; refusing deletion')
            call(['/usr/bin/btrfs','subvolume','delete',str(TARGET)]);record.unlink()
if __name__=='__main__':main()
