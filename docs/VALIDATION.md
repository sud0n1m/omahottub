# Alpha validation

Release preparation on 2026-09-27:

- 28 Python tests: original status/receipt behavior plus Borg profile/due logic,
  separate verification evidence, preserved success after failure, cache selection,
  unexpected subvolume refusal, cleanup after capture failure, and root helper
  argument/identity checks.
- Real Borg 1.4.5 integration: encrypted initial backup, unchanged backup with
  zero new chunks, empty-client-cache restore, hashes/modes/xattrs/hardlinks/
  symlinks/empty directories, SQLite integrity, and full repository data check.
- Actual Quickshell asynchronous test: pending preflight, external-start race,
  duplicate activation guard, start failure, status failure and confirmation
  timeout. Its command shim cannot start a real backup.
- Omarchy manifest validation. Manual visual/keyboard validation of the Paper
  layout was completed on the predecessor UI; the release UI keeps that layout.

The predecessor experiments additionally restored a real 32.9 GB local home
snapshot and synthetic data over restricted direct NAS SSH, including an upload
disconnect. These establish the design's feasibility; they are not an end-to-end
acceptance test of this newly packaged backend on a second machine.

Not yet established: second-machine installation, unattended full-home NAS
recovery with this package, privileged exact-ownership restoration, broad
application recovery, supported nested-subvolume layouts, off-site recovery,
or key custody for a new user's installation. A test pass is not proof that a
user configured credentials, coverage, retention capacity and recovery correctly.

No production cutover is performed by publishing this alpha. Backend selection
is explicit. Existing legacy XPS operation remains supported when no new backend
config is present.

The fixed-purpose root helper installation/audit on the development workstation
is awaiting OS authentication at release preparation. Its mocked boundary tests
pass; a successful privileged installation has not yet been claimed. The local
user-unit installer was exercised and leaves the new timer disabled. Legacy
XPS status output matched the existing production adapter exactly.
