#!/usr/bin/env python3
"""Unprivileged Borg runner. Snapshot privileges are confined to snapshot.py."""
import argparse,fcntl,json,os,re,shlex,signal,socket,subprocess,sys,time,uuid
from urllib.parse import urlsplit
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import CONFIG,STATE,config,read,write
import browse,watch
HELPER='/usr/local/libexec/omarchy-backup/snapshot'

def now():return datetime.now().astimezone().isoformat()
def due(receipt,c,at=None):
    at=at or datetime.now().astimezone();slot=at.replace(hour=c.get('due_hour',18),minute=0,second=0,microsecond=0)
    if at<slot:slot-=timedelta(days=1)
    try:
        stamp=datetime.fromisoformat(receipt['finished'])
        return receipt.get('profile')!=c['profile'] or not slot<=stamp<=at
    except (KeyError,TypeError,ValueError):return True

def ac_online(root=Path('/sys/class/power_supply')):
    for p in root.iterdir():
        try:
            if (p/'type').read_text().strip()!='Battery' and (p/'online').read_text().strip()=='1':return True
        except OSError:pass
    return False

def environment(c):
    for key in ['ssh_key','password_file']:
        s=Path(c[key]).stat()
        if s.st_uid!=os.getuid() or s.st_mode&0o077:raise ValueError(key+' must be owned by you and mode 0600')
    if not Path(c['known_hosts']).is_file():raise ValueError('Pinned known_hosts file is required')
    env={k:v for k,v in os.environ.items() if not k.startswith('BORG_')}
    env.update(BORG_PASSCOMMAND=shlex.join(['/usr/bin/cat',c['password_file']]),BORG_CACHE_DIR=str(STATE/'cache'),BORG_SECURITY_DIR=str(STATE/'security'),
        BORG_RSH=shlex.join(['ssh','-i',c['ssh_key'],'-o','IdentitiesOnly=yes','-o','IdentityAgent=none','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+c['known_hosts'],'-o','ConnectTimeout=8','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3']))
    return env

def emit(state,reason,c,**extra):
    write(STATE/'status.json',dict(state=state,reason=reason,time=now(),profile=c['profile'],**extra))

def borg(c,args,label,cwd=None,output=True):
    env=environment(c)
    with (STATE/(label+'.stdout')).open('wb') as out,(STATE/(label+'.stderr')).open('wb') as err:
        result=subprocess.Popen([c['borg'],*args],cwd=cwd,env=env,stdout=out,stderr=err,start_new_session=True)
        try:result.wait(timeout=14400)
        except BaseException:
            if result.poll() is None:
                os.killpg(result.pid,signal.SIGTERM)
                try:result.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(result.pid,signal.SIGKILL);result.wait(timeout=10)
            raise
    if result.returncode:raise RuntimeError('Borg '+label+' returned '+str(result.returncode)+'; inspect private '+label+'.stderr')
    # Large listings are streamed from the private stdout file instead of loaded.
    return (STATE/(label+'.stdout')).read_text() if output else STATE/(label+'.stdout')

def snapshot(action):
    return subprocess.check_output(['/usr/bin/sudo','-n',HELPER,action],text=True,timeout=60).strip()

def reachable(t,timeout=5):
    # A destination that cannot be reached (away from home, offline) is skipped, not failed.
    url=urlsplit(t['repository'])
    if not url.hostname:return True
    try:
        with socket.create_connection((url.hostname,url.port or 22),timeout=timeout):return True
    except OSError:return False

def run(c):
    if (STATE/'cleanup-needed.json').exists():raise RuntimeError('Snapshot cleanup requires attention; clean up and run doctor')
    pending=[t for t in c.get('targets',[c]) if due(read(STATE/t.get('receipt','last-success.json'),{}),t)]
    if not pending:emit('skipped','covered',c);return
    if c.get('require_ac',True) and not ac_online():emit('skipped','power',c);return
    pending=[t for t in pending if reachable(t)]
    if not pending:emit('skipped','network',c);return
    made=False;failed=[]
    try:
        emit('running','snapshot',c)
        # The root helper never executes this user-owned runner.
        source=Path(snapshot('create'));made=True
        expected=Path('/var/lib/omarchy-backup/home')/Path.home().name
        if source!=expected:raise RuntimeError('Unexpected snapshot path')
        # One frozen snapshot feeds every destination, so their archives match.
        name='home-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
        for t in pending:
            emit('running','backup',c,destination=t.get('name','nas'))
            try:capture(t,source,name)
            except Exception:failed.append(t.get('name','nas'))
    finally:
        if made:
            try:snapshot('delete')
            except BaseException:
                write(STATE/'cleanup-needed.json',{'time':now()})
                raise
    if failed:raise RuntimeError('Backup failed for '+', '.join(failed)+'; inspect private backup logs')
    emit('success','saved',c)

def capture(c,source,name):
    write(STATE/'capture-config.json',c)
    output=borg(c,['create','--json','--compression','zstd,3','--lock-wait','30','--paths-from-command','--paths-delimiter','\\0',c['repository']+'::'+name,'--','/usr/bin/python3','-I',str(Path(__file__).with_name('paths.py')),str(STATE/'capture-config.json')],'backup'+c.get('label',''),source)
    archive=json.loads(output)['archive']
    receipt={'archive':name,'finished':now(),'profile':c['profile'],'destination':c.get('name','nas'),'duration_s':archive['duration'],'stats':archive['stats']}
    # Saved evidence survives a later snapshot cleanup or verification failure.
    write(STATE/c.get('receipt','last-success.json'),receipt)
    return receipt

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['doctor','init','run','check','verify','watch','restore','export-key','archives','ls']);parser.add_argument('--archive');parser.add_argument('--path');parser.add_argument('--destination',type=Path);parser.add_argument('--json',action='store_true');a=parser.parse_args()
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    c=config()
    # Browsing an already-indexed archive is local: no lock, NAS or Borg needed.
    if a.action=='ls' and browse.indexed(browse.archive_name(a.archive)):return show(browse.listing(a.archive,a.path or ''),a.json)
    if a.action=='watch':print('Problems: '+(', '.join(watch.watch(c)) or 'none'));return
    if a.action=='verify' and not any(watch.verify_due(t) for t in c.get('targets',[c])):print('Monthly check not due');return
    if a.action=='verify' and c.get('require_ac',True) and not ac_online():print('Monthly check waits for AC power');return
    with (STATE/'runner.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            # A scheduled check simply waits for tomorrow rather than reporting a failure.
            if a.action=='verify':print('A backup is running; the monthly check will retry');return
            raise SystemExit('Another backup operation is active')
        version=subprocess.check_output([c['borg'],'--version'],text=True,timeout=10)
        # The first word is the executable's own name, e.g. 'borg-1.4.5 1.4.5' for a pinned download.
        if not re.fullmatch(r'\S+ 1\.4\.\d+\s*',version):raise SystemExit('This alpha requires Borg 1.4.x')
        def stop(signum,frame):raise InterruptedError('Backup operation interrupted')
        signal.signal(signal.SIGTERM,stop)
        try:
            if a.action=='doctor':
                environment(c)
                if snapshot('audit')!='ready':raise RuntimeError('Snapshot state needs cleanup before another run')
                (STATE/'cleanup-needed.json').unlink(missing_ok=True)
                print('Config, local credentials and snapshot helper ready; NAS access not tested.')
            elif a.action=='init':
                borg(c,['init','--encryption=repokey',c['repository']],'init');print('Encrypted repository initialized. Export its key before scheduling.')
            elif a.action=='run':run(c)
            elif a.action=='check':
                emit('running','verify',c);borg(c,['check','--verify-data','--lock-wait','30',c['repository']],'check')
                write(STATE/'last-check.json',{'finished':now(),'profile':c['profile']});emit('success','verified',c)
            elif a.action=='verify':
                failed=[]
                for t in c.get('targets',[c]):
                    if not watch.verify_due(t) or not reachable(t):continue
                    try:
                        emit('running','verify',c,destination=t.get('name','nas'));borg(t,['check','--verify-data','--lock-wait','30',t['repository']],'check'+t.get('label',''))
                        emit('running','drill',c,destination=t.get('name','nas'));result=watch.drill(t,borg)
                        write(STATE/t.get('check','last-check.json'),{'finished':now(),'profile':t['profile'],'drill':result})
                        print('%s: data check passed; restore drill compared %d of %d sampled files with 0 mismatches.'%(t.get('name','nas'),result['compared'],result['sampled']))
                    except Exception as e:failed.append(t.get('name','nas'));print('%s: %s'%(t.get('name','nas'),e))
                if failed:raise RuntimeError('Data check failed for '+', '.join(failed))
                emit('success','verified',c)
            elif a.action=='export-key':
                if not a.destination or a.destination.exists():raise ValueError('Choose a new destination for the encrypted key export')
                borg(c,['key','export',c['repository'],str(a.destination.absolute())],'export-key');print('Exported encrypted key. Store it and the password off this machine.')
            elif a.action=='archives':show({'archives':browse.archives(c,borg)},a.json)
            elif a.action=='ls':
                browse.build_index(c,borg,browse.archive_name(a.archive));show(browse.listing(a.archive,a.path or ''),a.json)
            elif a.action=='restore' and a.path is not None:
                if a.destination:raise ValueError('Partial restores always go to ~/Restored/ARCHIVE; omit --destination')
                if not browse.indexed(browse.archive_name(a.archive)):browse.build_index(c,borg,a.archive)
                show({'restored':str(browse.restore(c,borg,a.archive,a.path))},a.json)
            elif a.action=='restore':
                if not a.archive or not re.fullmatch(r'home-[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}',a.archive):raise ValueError('Select an exact archive name from last-success.json or Borg list')
                if not a.destination or a.destination.exists():raise ValueError('Restore requires a new, nonexistent directory')
                a.destination.mkdir(parents=True,mode=0o700)
                borg(c,['extract',c['repository']+'::'+a.archive],'restore',a.destination.absolute())
                print('Extracted. Verify files and application recovery before using them; foreign ownership may map to your user.')
        except BaseException:
            # Runner errors name destinations and private log files, never paths or secrets.
            if a.action in ['run','check','verify']:emit('failed',str(sys.exc_info()[1]) if sys.exc_info()[0] is RuntimeError else 'operation failed; inspect private runner logs',c)
            raise
def show(value,as_json):
    if as_json:print(json.dumps(value));return
    if 'archives' in value:
        for x in value['archives']:print(x['time'][:16].replace('T',' '),x['name'])
    elif 'entries' in value:
        for x in value['entries']:print(('%12s '%('-' if x['type']=='d' else x['size']))+x['name']+('/' if x['type']=='d' else ''))
    else:print('Restored to '+value['restored']+'. Nothing in your home folder was changed.')

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError,SystemExit) as e:
        # The panel reads one JSON object either way; a traceback stays a CLI-only detail.
        if '--json' not in sys.argv or (isinstance(e,SystemExit) and not isinstance(e.code,str)):raise
        print(json.dumps({'error':str(e.code if isinstance(e,SystemExit) else e)}));sys.exit(1)
