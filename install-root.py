#!/usr/bin/env python3
"""Explicit privileged setup only: install immutable helper + exact sudo commands."""
import argparse,json,os,pwd,re,shutil,stat,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--user',required=True);a=p.parse_args()
if os.geteuid()!=0:raise SystemExit('Run this installer with sudo, after reviewing it')
if not re.fullmatch('[a-z_][a-z0-9_-]*',a.user):raise SystemExit('Unsupported account name')
u=pwd.getpwnam(a.user)
if u.pw_uid<1000 or u.pw_dir!='/home/'+u.pw_name:raise SystemExit('Requires an ordinary /home/USERNAME account')
base=Path('/var/lib/omarchy-backup');etc=Path('/etc/omarchy-backup');lib=Path('/usr/local/libexec/omarchy-backup')
if any(x.exists() for x in [base,etc,lib,Path('/etc/sudoers.d/omarchy-backup')]):raise SystemExit('Existing installation; refusing overwrite. Inspect before upgrade.')
def trusted_mkdir(path):
    for part in reversed([path,*path.parents]):
        if not part.exists():part.mkdir(mode=0o755)
        st=part.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:
            raise SystemExit('Untrusted installation ancestor: '+str(part))
for x in [base,etc,lib,Path('/etc/sudoers.d')]:trusted_mkdir(x)
base.chmod(0o750);os.chown(base,0,u.pw_gid)
helper=lib/'snapshot';shutil.copyfile(Path(__file__).resolve().parent/'backend/snapshot.py',helper);helper.chmod(0o755);os.chown(helper,0,0)
(etc/'snapshot.json').write_text(json.dumps({'user':u.pw_name})+'\n');(etc/'snapshot.json').chmod(0o644)
line=f'{u.pw_name} ALL=(root) NOPASSWD: {helper} create, {helper} delete, {helper} audit\n'
fd,name=tempfile.mkstemp(prefix='omarchy-backup-',dir='/etc/sudoers.d')
try:
    with os.fdopen(fd,'w') as f:f.write(line)
    os.chmod(name,0o440);subprocess.run(['/usr/bin/visudo','-cf',name],check=True)
    os.replace(name,'/etc/sudoers.d/omarchy-backup')
finally:
    if os.path.exists(name):os.unlink(name)
print('Snapshot helper installed. No timer enabled; no backup started.')
