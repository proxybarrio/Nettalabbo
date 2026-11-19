# Preliminary security review: Nettalabbo 0.5.3

Review date: 19 November 2026. Source archive `nettalabbo-source-0.5.3-rev2.zip` and updated revision 3. **Static inspection and offline regression tests only, not a security penetration test.**

## Positive controls already present

* The port scanner is manually initiated, bound to an explicit IPv4 address range (maximum 256 addresses) and limits a user-specified consecutive TCP port range to 128 ports. It is not a stealth scanning tool.
* The SMTP recipient check is optional, one address at a time, confirms before making a network request, and does not issue the SMTP DATA command. Its response is explicitly nonconclusive.
* The Titan upload prompts for an explicit file and confirmation, disallows empty uploads, and limits payload size to 256 KiB.
* OpenSSH host key checking remains enabled via `StrictHostKeyChecking=ask`. SSH and Telnet invoke installed system clients with argument arrays, not shell command strings.
* TLS clients use certificate checking where possible. The protocol adapter can offer trust on first use for a certificate that cannot be PKI validated, subject to an explicit user decision and stored fingerprint. This is weaker than ordinary certificate validation and should be clearly explained.
* Simple TCP client reads have timeouts and a 300,000-byte response bound. Users choose legacy destinations explicitly.

## Corrected in package revision 3

The application formerly wrote `~/.config/nettalabbo/settings.json` with the default filesystem umask. A permissive umask could make local network browsing history readable by other accounts. Revision 3 creates a directory with mode 0700 and atomically saves settings with mode 0600. Added `test_local_privacy.py`.

## Unresolved risks / release blockers

1. Experimental legacy protocol parsers consume untrusted responses, with no fuzzing or comprehensive hostile-input coverage. The GUI and third-party protocol servers must be treated as untrusted.
2. Some clients (FTP and NNTP) perform per-operation reads that may wait for timeout or lack the same precise cancellation behavior as the bounded shared TCP client. Test under disconnection and malicious-server scenarios before recommending use on sensitive networks.
3. The built-in SSH/Telnet console is not a full terminal emulator. Prior user screenshots showed an `ssh_askpass` error on SSH; end-to-end interactive authentication still needs verification. Do not advise disabling SSH host key checking to work around failures.
4. Telnet and most legacy plaintext protocols are inherently unencrypted. Never enter credentials on insecure networks.
5. The configuration may preserve previously entered hosts and URLs; users should avoid pasting secrets into URLs or sharing unredacted logs. Earlier `netlabbo` settings files may still exist and were not removed.
6. No real live server interoperability suite, dependency vulnerability scan, or automated security regression pipeline has been completed on Ubuntu 20.04 and newer releases.
7. A verified private security contact and issue tracker are not yet available. Avoid public disclosure of confidential bug details until they are in place.

No real network targets were scanned as part of this audit, and no mailboxes were probed.