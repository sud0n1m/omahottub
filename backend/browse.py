"""Restore browser: archive list, per-archive local index and non-overwriting partial restore.
The index holds file names only; it is private state and is rebuilt from Borg, never from the live home.
"""
import json,os,re,shutil,sqlite3,stat
from pathlib import Path
from common import STATE,write
ARCHIVE=re.compile(r'home-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}')
RESTORED=Path.home()/'Restored'
INDEX_VERSION='1'
KEEP_INDEXES=3
HEADROOM=1024**3

def archive_name(name):
    if not isinstance(name,str) or not ARCHIVE.fullmatch(name):raise ValueError('Select an exact archive name from omahottub archives')
    return name

def clean_path(value):
    # Archive paths are relative to the snapshot home; '' is its root.
    if not isinstance(value,str) or '\0' in value or value.startswith('/'):raise ValueError('Path must be relative to your home folder')
    parts=[x for x in value.split('/') if x not in ('','.')]
    if '..' in parts:raise ValueError('Path must not contain ..')
    return '/'.join(parts)

def archives(c,borg):
    rows=json.loads(borg(c,['list','--json','--lock-wait','30',c['repository']],'archives'))['archives']
    found=sorted(({'name':x['name'],'time':x['time']} for x in rows if ARCHIVE.fullmatch(x.get('name',''))),key=lambda x:x['name'],reverse=True)
    write(STATE/'archives.json',{'archives':found})
    return found

def index_path(name):return STATE/'index'/(archive_name(name)+'.sqlite')

def build_index(c,borg,name,lines=None):
    target=index_path(name);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=target.with_suffix('.tmp');tmp.unlink(missing_ok=True)
    listing=None
    if lines is None:
        listing=borg(c,['list','--json-lines','--lock-wait','30',c['repository']+'::'+name],'index',output=False);lines=listing.open('rb')
    try:
        with sqlite3.connect(tmp) as db:
            db.execute('CREATE TABLE entries(parent TEXT NOT NULL,name TEXT NOT NULL,type TEXT NOT NULL,size INTEGER,mtime TEXT,PRIMARY KEY(parent,name)) WITHOUT ROWID')
            db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
            count=0;batch=[]
            for line in lines:
                item=json.loads(line);path=item['path']
                parent,_,leaf=path.rpartition('/')
                batch.append((parent,leaf,item['type'],item.get('size'),item.get('mtime')));count+=1
                if len(batch)>=5000:db.executemany('INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?)',batch);batch=[]
            db.executemany('INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?)',batch)
            db.executemany('INSERT INTO meta VALUES (?,?)',[('version',INDEX_VERSION),('archive',name),('entries',str(count))])
        tmp.chmod(0o600);os.replace(tmp,target)
    finally:
        tmp.unlink(missing_ok=True)
        if listing:lines.close();listing.unlink(missing_ok=True)
    # Indexes are a local convenience cache; only the newest few are kept.
    for old in sorted(target.parent.glob('home-*.sqlite'),reverse=True)[KEEP_INDEXES:]:old.unlink(missing_ok=True)
    return target

def indexed(name):
    target=index_path(name)
    try:
        with sqlite3.connect('file:'+str(target)+'?mode=ro',uri=True) as db:
            return target if db.execute("SELECT value FROM meta WHERE key='version'").fetchone()==(INDEX_VERSION,) else None
    except sqlite3.Error:return None

def listing(name,path):
    path=clean_path(path);target=indexed(name)
    if not target:raise RuntimeError('Archive is not indexed yet')
    with sqlite3.connect('file:'+str(target)+'?mode=ro',uri=True) as db:
        if path:
            parent,_,leaf=path.rpartition('/');row=db.execute('SELECT type FROM entries WHERE parent=? AND name=?',(parent,leaf)).fetchone()
            if not row or row[0]!='d':raise ValueError('Folder not found in this backup')
        rows=db.execute("SELECT name,type,size,mtime FROM entries WHERE parent=? ORDER BY type!='d',name",(path,)).fetchall()
        files,size=subtree(db,path) if path else (None,None)
    return {'archive':name,'path':path,'files':files,'bytes':size,'entries':[{'name':n,'type':t,'size':s,'mtime':m} for n,t,s,m in rows]}

def subtree(db,path):
    # '0' sorts right after '/', so this range is every descendant folder via the primary key.
    return db.execute("SELECT count(*),coalesce(sum(size),0) FROM entries WHERE type!='d' AND (parent=? OR (parent>=? AND parent<?))",(path,path+'/',path+'0')).fetchone()

def entry(name,path):
    target=indexed(name)
    if not target:raise RuntimeError('Archive is not indexed yet')
    parent,_,leaf=path.rpartition('/')
    with sqlite3.connect('file:'+str(target)+'?mode=ro',uri=True) as db:
        row=db.execute('SELECT type,size FROM entries WHERE parent=? AND name=?',(parent,leaf)).fetchone()
        if not row:raise ValueError('Path not found in this backup')
        return (row[0],subtree(db,path)[1]) if row[0]=='d' else (row[0],row[1] or 0)

def restore_destination(name,path,base=None):
    """Return the per-archive restore root; refuse to touch anything that already exists."""
    root=Path(base or RESTORED)/archive_name(name);path=clean_path(path)
    if not path:raise ValueError('Choose a file or folder; full restores use --destination')
    current=root.parent
    for part in [root.name,*path.split('/')[:-1]]:
        current=current/part
        try:s=current.lstat()
        except FileNotFoundError:continue
        if not stat.S_ISDIR(s.st_mode):raise ValueError('Restore location is not a plain folder: '+str(current))
    if os.path.lexists(root/path):raise ValueError('Already restored at '+str(root/path)+'; move it away first')
    return root

def restore(c,borg,name,path,base=None):
    path=clean_path(path)
    if not path:raise ValueError('Choose a file or folder; full restores use --destination')
    _,size=entry(name,path)
    root=restore_destination(name,path,base)
    existing=next(p for p in [root,*root.parents] if p.exists())
    if shutil.disk_usage(existing).free<size+HEADROOM:raise ValueError('Not enough free space to restore %.1f GB and keep 1 GB spare'%(size/1e9))
    root.mkdir(parents=True,exist_ok=True,mode=0o700)
    # pp: keeps names like 'sh:*' literal; Borg would otherwise treat them as patterns.
    borg(c,['extract','--lock-wait','30',c['repository']+'::'+name,'pp:'+path],'restore',root)
    return root/path
