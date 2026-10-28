# Changelog

## Unreleased

- Add `watch`: critical desktop notifications for failed backups or checks,
  backups stopped for 36 hours, pending snapshot cleanup and an overdue monthly
  check, with per-problem repeat limits. Runs hourly and on unit failure.
- Add `verify`: a monthly, AC-gated repository data check followed by a restore
  drill that compares 25 random files with unchanged live copies.
- The panel counts a passing monthly check for the backups after it, instead of
  only for the archive made before it.
- Add `archives`, `ls` and `restore --path` for browsing a backup and restoring
  a single file or folder into `~/Restored/ARCHIVE/`, never over live files.
- Add a keyboard-first **Restore files** view to the panel: day picker, folder
  browsing, type-to-filter, file and folder restore, and a Show in Files
  notification. All repository access goes through the CLI.
- Show each folder's total size and file count, and refuse a restore that would
  leave less than 1 GB free.
- Return `{"error": …}` from `--json` commands instead of a traceback.
- Cache a per-archive SQLite index of names, types, sizes and times so folder
  browsing is local after the first listing.
- Pass restore paths to Borg as literal path prefixes and refuse existing targets
  or non-folder parents in the restore location.

## 0.1.0-alpha.2

- Rename the project and panel to Omahottub.
- Add the `omahottub` CLI while retaining `omarchy-backup` compatibility.
- Preserve configuration, service names, plugin ID and existing backup behavior.

## 0.1.0-alpha.1

- Package the Paper-designed backup panel with stable action geometry and separate
  saved/attempt/verification evidence.
- Preserve legacy XPS backend compatibility and the existing plugin identifier.
- Add opt-in Borg 1.4-over-SSH runner and a fixed-purpose Btrfs snapshot helper.
- Add explicit setup, private key handling, recovery, cleanup and removal guides.
- Add regression tests, a real encrypted restore test and CI.
- No automatic prune/compact, backend migration or timer activation.
