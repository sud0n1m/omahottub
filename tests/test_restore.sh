#!/usr/bin/env bash
# Restore browser QML against a fake omahottub CLI. Nothing contacts a repository.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
mkdir "$scratch/qs" "$scratch/bin"
cat > "$scratch/bin/omahottub" <<'PY'
#!/usr/bin/python3
import json,os,sys,time
from pathlib import Path
with Path(os.environ['RESTORE_TEST_CALLS']).open('a') as f:f.write(json.dumps(sys.argv[1:])+'\n')
a=sys.argv[1:];arg=lambda k:a[a.index(k)+1]
A,B='home-20261023T010000Z-0123abcd','home-20261022T010000Z-0123abcd'
def out(v,code=0):print(json.dumps(v));sys.exit(code)
if a[0]=='archives':out({'archives':[{'name':A,'time':'2026-10-23T18:00:12.000000'},{'name':B,'time':'2026-10-22T18:00:09.000000'}]})
if a[0]=='ls':
 name,path=arg('--archive'),arg('--path')
 if name==A and path=='' and not Path(os.environ['RESTORE_TEST_SLOW']).exists():Path(os.environ['RESTORE_TEST_SLOW']).touch();time.sleep(2)
 tree={'':[{'name':'Projects','type':'d','size':0},{'name':"it's a.txt",'type':'-','size':2048}],
       'Projects':[{'name':'app','type':'d','size':0},{'name':'README.md','type':'-','size':12},{'name':'notes','type':'-','size':5}]}
 if path not in tree or (name==B and path):out({'error':'Folder not found in this backup'},1)
 out({'archive':name,'path':path,'files':None if not path else 3,'bytes':None if not path else 17,'entries':tree[path]})
if a[0]=='restore':
 path=arg('--path')
 if path=='Projects/README.md':out({'error':'Already restored at /x/Projects/README.md; move it away first'},1)
 if path=='crash':print('Traceback (most recent call last):');sys.exit(1)
 out({'restored':os.environ['HOME']+'/Restored/'+arg('--archive')+'/'+path})
sys.exit(2)
PY
for tool in notify-send gdbus; do
  printf '#!/usr/bin/python3\nimport json,os,sys\nfrom pathlib import Path\nwith Path(os.environ["RESTORE_TEST_CALLS"]).open("a") as f:f.write(json.dumps(["%s",*sys.argv[1:]])+"\\n")\n' "$tool" > "$scratch/bin/$tool"
done
chmod 700 "$scratch/bin/"*
cp "$here/test_restore.qml" "$scratch/qs/shell.qml"
log="$scratch/quickshell.log"; calls="$scratch/calls"
RESTORE_TEST_PLUGIN="$(cd "$here/.." && pwd)" RESTORE_TEST_CALLS="$calls" RESTORE_TEST_SLOW="$scratch/slow" RESTORE_TEST_BIN="$scratch/bin" RESTORE_TEST_SHOT="${RESTORE_TEST_SHOT:-}" \
  HOME="$scratch/home" PATH="$scratch/bin" WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}" QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}" \
  /usr/bin/timeout 40s /usr/bin/quickshell -p "$scratch/qs/shell.qml" --no-color >"$log" 2>&1 || true
if ! grep -q 'RESTORE_BROWSER_READY' "$log" || grep -qE '(TEST_FAILED|COMPONENT_ERROR|Error loading|TypeError|ReferenceError)' "$log"; then
  cat "$log"; test -f "$calls" && cat "$calls"; exit 1
fi
grep 'RESTORE_BROWSER_READY' "$log"
