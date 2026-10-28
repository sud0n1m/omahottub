"""Alerts for stopped or failing backups, and the monthly data check with a restore drill.
watch() only reads local state; verify() is the one place that reads the whole repository.
"""
import hashlib,os,shutil,sqlite3,stat,subprocess
from datetime import datetime,timedelta
from pathlib import Path
from common import STATE,read,write
import browse
# (key, repeat): each problem notifies once, then at most this often while it lasts.
REPEAT={'failed':timedelta(hours=12),'stale':timedelta(hours=12),'cleanup':timedelta(hours=12),'unverified':timedelta(days=7)}
DRILL_FILES=25
DRILL_MAX_BYTES=50*1000**2

def when(value):
    try:
        t=datetime.fromisoformat(value)
        return t if t.tzinfo else None
    except (TypeError,ValueError):return None

def problems(c,at):
    found={}
    saved=read(STATE/'last-success.json',{});status=read(STATE/'status.json',{});check=read(STATE/'last-check.json',{})
    if (STATE/'cleanup-needed.json').exists():
        found['cleanup']=('Backup snapshot needs cleanup','Backups are paused until the leftover snapshot is removed. Run: omahottub doctor')
    if status.get('state')=='failed':
        found['failed']=('Backup failed','The latest backup or check failed. Earlier backups are still available. Open the Omahottub panel for details.')
    last=when(saved.get('finished'))
    if not last or at-last>timedelta(hours=c.get('stale_hours',36)):
        age='No backup has been saved yet.' if not last else 'Last saved %s (%d days ago).'%(last.astimezone(at.tzinfo).strftime('%a %b %-d, %H:%M'),(at-last).days)
        found['stale']=('Backups have stopped',age+' Backups need AC power, the home network and a logged-in session.')
    checked=when(check.get('finished'))
    if last and (not checked or at-checked>timedelta(days=c.get('verify_days',30)+14)):
        found['unverified']=('Backup data check overdue','The monthly repository check and restore drill have not passed recently. Run: omahottub verify')
    return found

def watch(c,at=None,notify=None):
    at=at or datetime.now().astimezone()
    notify=notify or (lambda title,body:subprocess.run(['notify-send','--app-name=Omahottub','--urgency=critical','--icon=dialog-warning',title,body],timeout=10,check=False))
    sent=read(STATE/'alerts.json',{});found=problems(c,at);keep={}
    for key,(title,body) in found.items():
        last=when(sent.get(key))
        if last and at-last<REPEAT[key]:keep[key]=sent[key];continue
        notify(title,body);keep[key]=at.isoformat()
    # A resolved problem is forgotten, so the next occurrence notifies at once.
    write(STATE/'alerts.json',keep)
    return sorted(found)

def verify_due(c,at=None):
    at=at or datetime.now().astimezone();check=read(STATE/'last-check.json',{});done=when(check.get('finished'))
    return check.get('profile')!=c['profile'] or not done or at-done>=timedelta(days=c.get('verify_days',30))

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def drill(c,borg,home=None):
    """Extract a random sample of the newest archive and compare it with unchanged live files."""
    home=Path(home or Path.home());latest=browse.archives(c,borg)[0];name=latest['name']
    taken=datetime.fromisoformat(latest['time']).timestamp()
    if not browse.indexed(name):browse.build_index(c,borg,name)
    with sqlite3.connect('file:'+str(browse.index_path(name))+'?mode=ro',uri=True) as db:
        rows=db.execute("SELECT parent,name FROM entries WHERE type='-' AND size<=? ORDER BY random() LIMIT ?",(DRILL_MAX_BYTES,DRILL_FILES)).fetchall()
    paths=[(p+'/'+n) if p else n for p,n in rows]
    target=STATE/'drill';shutil.rmtree(target,ignore_errors=True);target.mkdir(mode=0o700)
    try:
        borg(c,['extract','--lock-wait','30',c['repository']+'::'+name,*['pp:'+p for p in paths]],'drill',target)
        result=dict(archive=name,sampled=len(paths),compared=0,mismatches=0,missing=0)
        for rel in paths:
            got=target/rel
            if not got.is_file():result['missing']+=1;continue
            try:live=(home/rel).lstat()
            except FileNotFoundError:continue
            # Only files untouched since the snapshot can be compared with the live copy.
            if not stat.S_ISREG(live.st_mode) or max(live.st_mtime,live.st_ctime)>taken:continue
            result['compared']+=1
            if sha(got)!=sha(home/rel):result['mismatches']+=1
    finally:
        for root,dirs,_ in os.walk(target):os.chmod(root,0o700)
        shutil.rmtree(target,ignore_errors=True)
    if result['missing'] or result['mismatches']:raise RuntimeError('Restore drill failed: %(missing)d missing, %(mismatches)d mismatched of %(sampled)d'%result)
    return result
