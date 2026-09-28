# Alpha validation

Release preparation on 2026-09-27:

- 29 Python tests: original status/receipt behavior plus Borg profile/due logic,
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

The fixed-purpose root helper was installed with OS authentication on the
Btrfs development workstation. The generated exact-command sudo rule passed
visudo, audit succeeded, and an actual read-only /home snapshot was accessible
as the normal user and deleted successfully. The installer copied the release helper source into the root-owned location.
This is a snapshot lifecycle test, not a full NAS backend run.
The user-unit installer left the new timer disabled. Legacy XPS status matched
the existing production adapter; the live alpha UI continues to use that backend.

CI exposed a timezone-dependent timer fixture. The adapter now requests Unix
timestamps from systemd, and a regression test checks offset-independent parsing.
