# Security boundaries

The QML plugin runs unsandboxed inside Omarchy. Its helper reads bounded local
status and queries systemd; a click takes a fresh preflight and starts one of
two fixed user units. No server commands, paths or units come from UI text.

The optional runner runs as the user. It uses argument arrays, a private
password file, pinned host keys, a dedicated SSH identity, process-group cleanup,
and a nonblocking operation lock. Private logs, manifests and restore copies
are not release artifacts. Never attach them to public issues without review.

The only root helper has fixed source/target paths and three exact actions. It
checks ownership/modes, identifies the /home subvolume, creates read-only
snapshots under a trusted parent, and checks stored UUID before deletion.
It does not read user configuration or execute user-owned code. Installer code
needs explicit root execution once; installed root code must not be writable
by the user. One account per host is supported. Privileged upgrades/removal are
manual in this alpha; do not overwrite an active helper or its snapshot state.

The snapshot contains /home; existing Unix access controls still govern other
users' files. Only the configured user's subtree is selected for backup. This
is not a sandbox protecting a user from their own processes. Review filesystem
permissions and encrypted disk/storage requirements for your environment.

No automatic pruning, compaction, credential upload, telemetry or public log
submission. A compromised append-only client can hide archive references;
independent admin recovery and key custody remain necessary.

For a security issue, use GitHub's private vulnerability reporting when enabled.
Do not post credentials, private logs or exploit details in a public issue.
