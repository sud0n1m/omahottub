#!/usr/bin/env python3
"""Install user runner and inactive units. Never enables a timer or changes old backups."""
import os,shutil,subprocess
from pathlib import Path
if os.geteuid()==0:raise SystemExit('Run without sudo; install-root.py is separate')
root=Path(__file__).resolve().parent;home=Path.home();lib=home/'.local/lib/omarchy-backup';units=home/'.config/systemd/user';bin_dir=home/'.local/bin'
for p in [lib,units,bin_dir]:p.mkdir(parents=True,exist_ok=True)
for name in ['common.py','backup.py','paths.py']:shutil.copyfile(root/'backend'/name,lib/name)
for command_name in ['omahottub','omarchy-backup']:
    command=bin_dir/command_name;command.write_text('#!/bin/sh\nexec /usr/bin/python3 -I "$HOME/.local/lib/omarchy-backup/backup.py" "$@"\n');command.chmod(0o755)
for name in ['omarchy-backup.service','omarchy-backup.timer']:shutil.copyfile(root/'backend'/name,units/name)
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
print('Installed inactive units. Configure credentials, snapshot helper and recovery before enabling the timer.')
