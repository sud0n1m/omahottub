# Recovery, rollback, and removal

Keep the exported encrypted Borg key and its password in an independently
retrievable private location. The SSH private key is not the repository key.
Do not depend on obtaining the only password copy from its encrypted backup.
Test on a fresh client without original caches. Use Borg's documented `key import`
when recovering a repository whose encrypted key entry is lost; make a protected
repository copy before destructive recovery procedures.

To inspect history, use the configured Borg 1.4 client with the same pinned SSH
transport and private password handling. The runner's private `last-success.json`
records its most recent archive. Restore into a new directory with
`omarchy-backup restore --archive NAME --destination NEW_DIRECTORY`.
Do not overlay a live home. Verify hashes and permissions, and open restored
application databases using their native tools. A generic SQLite integrity check
may require app-specific functions/extensions. Restore only copies, never run
repair against live originals. Root-owned/group-owned files may require a
separately reviewed privileged ownership restoration.

## Interrupted runs

First confirm no operation is running (`systemctl --user status omarchy-backup.service`
and local processes). Do not break a Borg lock while any writer may be alive.
Normal service stop uses the whole control group. The runner terminates its
owned Borg/SSH process group before snapshot cleanup on handled interruption.
SIGKILL and sudden power loss cannot execute that cleanup.

A stale helper snapshot prevents the next run. After confirming all writers
stopped, inspect and invoke the exact helper:

```sh
sudo -n /usr/local/libexec/omarchy-backup/snapshot audit
sudo -n /usr/local/libexec/omarchy-backup/snapshot delete
```

After cleanup, run `omarchy-backup doctor` to confirm readiness and clear any
cleanup-needed marker. A cleanup failure cannot be hidden by a later skipped run.

Deletion verifies its stored subvolume UUID and read-only property. A missing
record/UUID mismatch is a hard stop requiring administrator inspection. Never
substitute a broad recursive deletion. Existing backups are unaffected.

## Return to the previous XPS backend

Stop/disable only the new timer and service. Move the new config out of
`~/.config/omarchy-backup/config.json`; the panel then uses the legacy XPS
service again. Re-enable that old timer if you previously disabled it. Keep
both repositories and credentials until recovery is independently verified.

## Remove the alpha

1. `systemctl --user disable --now omarchy-backup.timer`, then stop
   `omarchy-backup.service`. Confirm all operations have exited.
2. Clean up a tracked snapshot as above. Do not remove helper metadata first.
3. Remove the plugin with `omarchy plugin remove sudonim.xps-backup` only if you
   intend to remove the backup UI. The legacy installation uses that same ID.
4. Remove the two `omarchy-backup.*` user units, `~/.local/bin/omarchy-backup`
   and `~/.local/lib/omarchy-backup`, then `systemctl --user daemon-reload`.
5. An administrator can remove `/etc/sudoers.d/omarchy-backup`, the installed
   helper and `/etc/omarchy-backup/snapshot.json`. Remove their directories only
   when empty. `/var/lib/omarchy-backup` must contain no snapshot first.
6. Retain private config/state, exported keys, passwords and NAS archives unless
   you separately decide to destroy them. Uninstalling software is not deletion
   authorization for backups. Revoke the dedicated client SSH key if retiring it.
