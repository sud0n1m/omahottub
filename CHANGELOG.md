# Changelog

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
