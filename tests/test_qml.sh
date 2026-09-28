#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
mkdir "$scratch/qs" "$scratch/bin"
cat > "$scratch/bin/python3" <<'PY'
#!/usr/bin/python3
import json,os,time,sys
from pathlib import Path
value=json.loads(Path(os.environ['BACKUP_QML_TEST_STATE']).read_text())
time.sleep(.08)  # Asynchronous snapshot: UI must not act on the prior value.
if value.pop('_fail',False):sys.exit(1)
print(json.dumps(value))
PY
cat > "$scratch/bin/systemctl" <<'PY'
#!/usr/bin/python3
import os,sys,json
from pathlib import Path
with Path(os.environ['BACKUP_QML_TEST_CALLS']).open('a') as f:f.write(' '.join(sys.argv[1:])+'\n')
if sys.argv[1:]!=['--user','start','--no-block','xps-nas-backup.service']:sys.exit(2)
sys.exit(1 if json.loads(Path(os.environ['BACKUP_QML_TEST_STATE']).read_text()).get('_startFail') else 0)
PY
chmod 700 "$scratch/bin/"*
ln -s /usr/share/omarchy/shell/Commons "$scratch/qs/Commons"
ln -s /usr/share/omarchy/shell/Ui "$scratch/qs/Ui"
ln -s "$here/.." "$scratch/qs/Plugin"
printf '%s\n' '{"state":"due","canStart":true,"serviceRunning":false,"managerAvailable":true,"lastCheckTime":"a"}' > "$scratch/state.json"
cp "$here/test_async.qml" "$scratch/qs/shell.qml"
log="$scratch/quickshell.log"
calls="$scratch/systemctl-calls"
BACKUP_QML_TEST_CALLS="$calls" BACKUP_QML_TEST_STATE="$scratch/state.json" PATH="$scratch/bin" \
  WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}" QT_QPA_PLATFORM=wayland \
  /usr/bin/timeout 30s /usr/bin/quickshell -p "$scratch/qs/shell.qml" --no-color >"$log" 2>&1
if ! rg -q 'BACKUP_ASYNC_GUARDS_READY' "$log" || ! rg -q 'BACKUP_QML_COMPONENTS_READY' "$log" \
  || rg -q '(TEST_FAILED|SERVICE_ERROR|PANEL_ERROR|Error loading|TypeError|ReferenceError)' "$log" \
  || ! test -f "$calls" || ! test "$(wc -l < "$calls")" -eq 4 \
  || test "$(rg -Fxc -- '--user start --no-block xps-nas-backup.service' "$calls")" -ne 4; then
  cat "$log"
  if test -f "$calls"; then cat "$calls"; fi
  exit 1
fi
rg 'BACKUP_(QML_COMPONENTS|ASYNC_GUARDS)_READY' "$log"
