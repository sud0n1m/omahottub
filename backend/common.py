"""Configuration and scope shared by the unprivileged alpha runner."""
import hashlib,json,os,re,shutil,stat
from pathlib import Path
CONFIG=Path.home()/'.config/omarchy-backup/config.json'
STATE=Path.home()/'.local/state/omarchy-backup'
PREFIXES=['.cache','.local/state/omarchy-backup','.local/state/xps-nas-backup','.local/share/Trash','.npm/_cacache','.npm/_logs']
DIRECTORIES=['node_modules','.venv','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','Cache','Code Cache','GPUCache','ShaderCache','GrShaderCache','Crashpad','Crash Reports']

def read(path,default=None):
    try:
        if path.stat().st_size>1024*1024:raise ValueError('JSON exceeds size limit')
        return json.loads(path.read_text())
    except FileNotFoundError:return default

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.chmod(0o600);os.replace(tmp,path)

def config(path=CONFIG):
    c=read(path)
    if not isinstance(c,dict) or c.get('backend')!='borg':raise ValueError('Configure the Borg backend first')
    repo=c.get('repository','')
    if not isinstance(repo,str) or not repo.startswith('ssh://') or any(x in repo for x in ['\n','\r','\0','::']):raise ValueError('repository must be an ssh:// Borg URL')
    if type(c.get('due_hour',18)) is not int or not 0<=c.get('due_hour',18)<=23:raise ValueError('due_hour must be 0..23')
    if type(c.get('require_ac',True)) is not bool:raise ValueError('require_ac must be boolean')
    for key,low,high in [('stale_hours',12,24*14),('verify_days',1,365)]:
        if key in c and (type(c[key]) is not int or not low<=c[key]<=high):raise ValueError(key+' must be an integer from %d to %d'%(low,high))
    for key in ['ssh_key','known_hosts','password_file']:
        if not isinstance(c.get(key),str) or not c[key]:raise ValueError('Missing '+key)
        c[key]=str(Path(c[key]).expanduser().absolute())
    c['borg']=shutil.which(c.get('borg','borg')) or ''
    if not c['borg']:raise ValueError('Borg 1.4.x is required')
    for key,default in [('exclude_prefixes',PREFIXES),('exclude_directories',DIRECTORIES)]:
        values=c.get(key,default)
        if not isinstance(values,list) or any(not isinstance(x,str) or not x or '\x00' in x or '\n' in x or Path(x).is_absolute() or '..' in Path(x).parts or (key=='exclude_directories' and '/' in x) for x in values):raise ValueError('Invalid '+key)
        c[key]=list(dict.fromkeys(default+values))
    c['profile']=profile(c,c['repository'])
    c['targets']=targets(c)
    return c

def profile(c,repository):
    return hashlib.sha256(json.dumps(dict(repository=repository,exclude_prefixes=c['exclude_prefixes'],exclude_directories=c['exclude_directories']),sort_keys=True).encode()).hexdigest()

def targets(c):
    """The primary repository plus optional extra destinations, each with its own receipts."""
    out=[dict(c,name=c.get('name','nas'),receipt='last-success.json',check='last-check.json',label='',verify_days=c.get('verify_days',30))]
    extra=c.get('destinations',[])
    if not isinstance(extra,list):raise ValueError('destinations must be a list')
    for d in extra:
        if not isinstance(d,dict) or not isinstance(d.get('name'),str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,30}',d['name']):raise ValueError('Each destination needs a short lowercase name')
        if d['name'] in [t['name'] for t in out]:raise ValueError('Duplicate destination '+d['name'])
        repo=d.get('repository','')
        if not isinstance(repo,str) or not repo.startswith('ssh://') or any(x in repo for x in ['\n','\r','\0','::']):raise ValueError(d['name']+': repository must be an ssh:// Borg URL')
        t=dict(c,name=d['name'],repository=repo,receipt='last-success.'+d['name']+'.json',check='last-check.'+d['name']+'.json',label='-'+d['name'])
        for key in ['ssh_key','known_hosts','password_file']:
            value=d.get(key,c[key] if key=='password_file' else None)
            if not isinstance(value,str) or not value:raise ValueError(d['name']+': missing '+key)
            t[key]=str(Path(value).expanduser().absolute())
        for key,default,low,high in [('verify_days',90,1,365)]:
            t[key]=d.get(key,default)
            if type(t[key]) is not int or not low<=t[key]<=high:raise ValueError(d['name']+': '+key+' must be an integer from %d to %d'%(low,high))
        t['profile']=profile(c,repo);t.pop('destinations',None);out.append(t)
    return out

def selected(root,c):
    root=Path(root);device=root.stat().st_dev
    def walk(path):
        rel=path.relative_to(root).as_posix();s=path.lstat()
        if any(rel==p or rel.startswith(p+'/') for p in c['exclude_prefixes']):return
        if stat.S_ISDIR(s.st_mode):
            if path.name in c['exclude_directories']:return
            # Parent snapshots leave empty subvolume placeholders (inode 2).
            if s.st_dev!=device or s.st_ino in (2,256):raise RuntimeError('Nested subvolume or mount needs explicit coverage: '+rel)
            yield rel
            for child in sorted(path.iterdir()):yield from walk(child)
        elif stat.S_ISLNK(s.st_mode):yield rel
        elif stat.S_ISREG(s.st_mode):yield rel
    for path in sorted(root.iterdir()):yield from walk(path)
