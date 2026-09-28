# Omarchy Backup — alpha

A quiet backup panel for Omarchy Quattro, with an optional Btrfs + Borg 1.4
backup runner. The action stays in one place while status refreshes. Saved
backups, latest attempts, and verification evidence are distinct.

**0.1.0-alpha.1 is for evaluation.** Keep an existing backup until you have
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
omarchy plugin add https://github.com/sud0n1m/omarchy-backup.git --enable
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
omarchy-backup doctor
omarchy-backup run                 # only if daily slot is due and eligible
omarchy-backup check               # explicit full repository data check
omarchy-backup export-key --destination /a/new/private/key-export
omarchy-backup restore --archive home-YYYYMMDDTHHMMSSZ-1234abcd --destination /a/new/restore
```

`check` is deliberately separate from backup. This alpha has no automatic
verification schedule; arrange periodic checks and restore drills yourself.
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
omarchy plugin validate .
```

MIT licensed. This project is not affiliated with BorgBackup or Omarchy.
