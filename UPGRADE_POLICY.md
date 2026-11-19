# Nettalabbo: upgrade and migration policy

- Current Debian package identity: `nettalabbo`. Use the same name for all following versions.
- First renamed release: 0.5.0-3; migration checks strengthened in revision 0.5.0-4. Future release numbers must advance monotonically.
- `Conflicts` and `Replaces` explicitly include `netlabbo`, `netlab-xubuntu`, and `network-laboratory-xubuntu`.
- APT removes the historical package when installing Nettalabbo, so no duplicate application remains.
- All requirements remain mandatory `Depends` in the `.deb` metadata.
- Keep automatic dependency preflight in `install-nettalabbo.sh`.
- Preserve user preferences by reading `~/.config/netlabbo/settings.json` as a migration source and writing to `~/.config/nettalabbo/settings.json` on first launch.
- Do not modify or delete the prior settings directory.
- The old binary is removed as part of the old Debian package. The new launcher is `nettalabbo`.
- Do not add destructive maintainer scripts to remove configurations.

- Installer detects legacy packages before running APT, checks the simulated transaction includes removal (`Remv`) of each installed legacy identity, and verifies that none remains installed after installation.
- Removal is an APT conflict resolution step in the same transaction, not an earlier `apt remove` / `apt purge`. Failed dependency resolution must not remove the old app.