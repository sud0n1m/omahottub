# Omahottub — alpha

A hot tub time machine for your Omarchy files.

Formerly Omarchy Backup. The `omahottub` command and the original
`omarchy-backup` command run the same backend. Existing `omarchy-backup`
configuration paths, systemd units, snapshot helper and `sudonim.xps-backup`
plugin ID stay unchanged for compatibility; no backup migration is required.

A quiet backup panel for Omarchy Quattro, with an optional Btrfs + Borg 1.4
backup runner. The action stays in one place while status refreshes. Saved
backups, latest attempts, and verification evidence are distinct.

**0.1.0-alpha.2 is for evaluation.** Keep an existing backup until you have
restored and verified your own files. This is a home-data backup, not a bootable
system image. The new privileged helper and Borg runner are intentionally small,
but the packaged backend is not yet a proven unattended full-home NAS deployment.
No pruning or compaction is implemented. Repository storage can grow indefinitely.

## Compatibility

- Omarchy Quattro's plugin-capable shell, Python 3, systemd user services.
- Optional backend: Linux, Borg **1.4.x** on client/server, `/home` itself a Btrfs
  subvolume, a normal `/home/USERNAME` account, SSH destination, root setup once.
- One snapshot-helper account per machine in this alpha. Btrfs-on-`/` with a
  plain `/home` directory, nested subvolumes needing separate coverage, Borg 2,
  cloud transports and multiple profiles are not supported.
- The historical plugin ID `sudonim.xps-backup` is retained to preserve the
  existing XPS installation and bar position. It is not a hardware requirement.

## Install the panel

```sh
omarchy plugin add https://github.com/sud0n1m/omahottub.git --enable
```

Inspect the repository before installing: Omarchy plugins run in the shell
process without sandboxing. The panel uses local status files and systemd;
it does not directly contact your NAS or read backup keys.

**Existing XPS users:** with no `~/.config/omarchy-backup/config.json`, it keeps
using `xps-nas-backup.service` and its existing receipts. Installation does not
switch the backup engine. If the same plugin ID is already installed manually,
back it up and update its files deliberately; `plugin add` refuses duplicate IDs.
Git-managed installations can use `omarchy plugin update sudonim.xps-backup`.
Do not copy the Borg example config merely to customize the existing panel.

**New users:** the panel reports unavailable until a supported backend is set up.
Follow [Borg setup](docs/SETUP.md). Configuring Borg explicitly selects that backend
for the panel. Local installation scripts do not enable timers, initialize NAS
repositories, delete existing backups, or disable another backup service.

## What is backed up

The Borg runner creates a read-only filesystem snapshot and streams selected
paths to Borg. Unchanged file chunks are reused; a complete staging archive and
full download are not required for every backup. The snapshot path stays stable.

By default home files, Git data, SQLite databases and their journals, and browser
application storage are included. `.cache`, backup state, trash, npm cache/logs,
common build/dependency caches and crash reports are excluded; the exact lists
are in `backend/common.py`. Config can add exclusions. Symlinks are preserved
without following their targets. Special files are omitted. Unexpected nested
subvolumes/mounts fail the backup rather than silently claiming coverage.

A frozen filesystem is crash-consistent. It is not a transaction across
applications or multiple databases. Test restoration with each application's
native tools. Linked Git worktrees may need `git worktree repair` **inside the
restore tree**, with original paths inaccessible. Unprivileged restore can map
foreign ownership to the restoring user; Borg retains original IDs in metadata.

## Operations

```sh
omahottub doctor
omahottub run                 # only if daily slot is due and eligible
omahottub check               # explicit full repository data check
omahottub verify              # monthly data check + restore drill, only when due
omahottub watch               # notify about failed, stopped or unchecked backups
omahottub export-key --destination /a/new/private/key-export
omahottub restore --archive home-YYYYMMDDTHHMMSSZ-1234abcd --destination /a/new/restore
```

### More than one destination

The top-level repository is the primary destination (`nas` unless `name` is set).
Add others, for example an off-site Borg host, under `destinations`:

```json
"destinations": [
  {"name": "offsite", "repository": "ssh://user@host.example/./repo",
   "ssh_key": "~/.ssh/omahottub-offsite", "known_hosts": "~/.config/omarchy-backup/known_hosts-offsite",
   "verify_days": 90}
]
```

Each run takes one snapshot and saves the same archive to every destination that
is due. A destination that cannot be reached, for example the home NAS while
travelling, is skipped instead of failing. If one destination fails, the others
still run, and the failure alert names it. `password_file` defaults to the
primary's. `verify` checks each destination on its own schedule (off-site default:
every 90 days, since a full check downloads the repository). `watch` reports
"stopped" only when no destination has saved for `stale_hours`, and separately
when one destination is more than 8 days behind. The restore browser and
`restore` use the primary repository.

### Getting a file or folder back

With the Borg backend, the panel shows **Restore files →**. Pick a day with
‹ › (Ctrl+←/→), browse with the arrow keys and Enter, and type to filter. Enter on
a file restores it; Tab reaches **Restore this folder**. Switching days keeps
you in the same folder, or the nearest one that existed then. A notification
offers **Show in Files** when a restore finishes. The same steps from a terminal:

```sh
omahottub archives                                   # newest first
omahottub ls --archive home-YYYYMMDDTHHMMSSZ-1234abcd --path Projects
omahottub restore --archive home-YYYYMMDDTHHMMSSZ-1234abcd --path Projects/app
```

The first `ls` of an archive builds a local index from Borg's listing; later
folders open without contacting the NAS. Indexes for the three newest indexed
archives are kept in private state and are excluded from backup. On the
author's XPS a 949,000-file archive indexed in about 20 seconds, including Borg's
listing over the LAN, into a 170 MB index. Partial restores land in `~/Restored/ARCHIVE/PATH`, never
on top of your current files. A path that was already restored there is refused,
not overwritten; move it away first. Paths are matched literally, so names such
as `sh:*` restore only themselves. Add `--json` for machine-readable output.

`check` is deliberately separate from backup. `verify` is the scheduled form:
once every `verify_days` (default 30), on AC power, it runs the full repository
data check and then a restore drill. The drill extracts 25 random files of up to
50 MB from the newest archive and compares them byte-for-byte with live files
that have not changed since that backup. Any missing or mismatched file fails it.

`watch` sends a critical desktop notification when a backup or check fails, when
nothing has been saved for `stale_hours` (default 36), when a snapshot needs
cleanup, or when the monthly check is two weeks overdue. Each problem notifies
once and then at most every 12 hours (weekly for the overdue check) while it
lasts; once it clears, the next occurrence notifies immediately. It reads only
local state, so it works offline. The backup and verify units also run it on failure.

```sh
systemctl --user enable --now omarchy-backup-watch.timer omarchy-backup-verify.timer
```
A successful extract does not automatically claim application or full restore
verification. The panel never promotes experiment results to production evidence.
Manual commands and the timer share a nonblocking lock.

[Recovery and cleanup](docs/RECOVERY.md) · [Security boundaries](SECURITY.md) ·
[Testing and known limits](docs/VALIDATION.md)

## Development

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
BORG_TEST_BINARY=/usr/bin/borg python3 tests/integration_borg.py
bash tests/test_qml.sh  # Omarchy + Quickshell + active Wayland session
bash tests/test_restore.sh  # restore browser against a fake CLI; offscreen
omarchy plugin validate .
```

MIT licensed. This project is not affiliated with BorgBackup or Omarchy.
