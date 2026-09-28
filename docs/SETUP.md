# Borg backend setup

Do this in a clone of the alpha repository. Keep existing backups and schedules
until you complete the restore acceptance step. No installer silently migrates
credentials or archives.

1. Install Borg 1.4.x, Python 3, Btrfs tools and OpenSSH using your distribution's
   package tools. The SSH server needs a compatible Borg 1.4.x binary too.
2. Create a separate repository directory and dedicated SSH key. Pin the NAS
   host key using a fingerprint verified through trusted administration; do not
   accept an unverified `ssh-keyscan` result as proof of identity.
3. On the server, use a fixed root/admin-owned wrapper, for example:

   ```sh
   #!/bin/sh
   exec /usr/bin/borg serve --append-only --restrict-to-repository /srv/backups/home
   ```

   Authorize only the new public key with a forced command and restrictions:

   ```text
   restrict,no-agent-forwarding,no-port-forwarding,no-X11-forwarding,no-pty,no-user-rc,command="/usr/local/libexec/home-backup-serve" ssh-ed25519 PUBLIC_KEY backup-client
   ```

   Add a `from=` restriction if you have stable, verified source addresses.
   Do not reuse an unrestricted administration key. Some NAS portable Borg
   builds require a private executable TMPDIR in the wrapper. Test the exact
   server, not just local Borg. Never weaken SSH forwarding policy to make it work.
4. Generate a strong repository password in a private file, outside this repo.
   Set private key and password file to mode 0600; parent directories should be
   0700. Keep the password out of shell command arguments and terminal output.
   Copy `config.example.json` to `~/.config/omarchy-backup/config.json` and edit
   paths, repository, power policy and daily due hour. The config contains paths,
   never key/password contents. Its presence selects Borg in the panel.
5. Install inactive user files: `python3 install.py`. Review and install the
   privileged helper: `sudo /usr/bin/python3 -I install-root.py --user "$USER"`.
   Root setup refuses existing installations. It installs only a root-owned
   helper/config and exact sudo commands `create`, `delete`, `audit`. No broad
   sudo permission and no root execution of user-owned backup code is granted.
6. Run `omarchy-backup doctor`. It checks local readiness, not NAS connectivity.
   Then `omarchy-backup init` initializes a **new** encrypted repository. Export
   its key with `omarchy-backup export-key --destination /new/private/key-export`.
   Store and retrieve the exported key and password off this laptop before
   relying on the repository. Keep maintenance credentials separate.
7. Run `omarchy-backup run`, then `omarchy-backup check`. Inspect private logs in
   `~/.local/state/omarchy-backup/`. Warnings count as failure; previous successful
   receipts survive later errors. Restore the archive named in `last-success.json`
   to a fresh location. Verify real content, metadata and application recovery.
8. Only after acceptance, enable `systemctl --user enable --now omarchy-backup.timer`.
   It checks hourly/startup and backs up once the configured daily slot is due.
   It needs the user's service manager; this alpha does not enable lingering.
   Coordinate retirement of your previous schedule yourself; preserve its archives.

Power/network interruption can fail a run; there is no automatic lock breaking.
A later eligible timer check retries. An orphan snapshot after SIGKILL/power loss
requires explicit cleanup per RECOVERY.md. No automatic retention deletion.

Changing repository or scope invalidates the previous profile's UI evidence.
Changes apply on the next run; do not edit configuration during an operation.
Borg capture freezes the selection configuration for that invocation.

See upstream [Borg server restrictions](https://borgbackup.readthedocs.io/en/stable/usage/serve.html)
and [append-only behavior](https://borgbackup.readthedocs.io/en/stable/usage/notes.html#append-only-mode-forbid-compaction).
Append-only preserves old committed data, but a compromised client can hide
archives logically. Recovery and eventual compaction need separate trusted admin
procedures; this alpha intentionally provides no prune/delete action.
