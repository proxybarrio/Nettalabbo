# Security and privacy

Nettalabbo is an experimental network utility and is not a substitute for a security audit.

- Only inspect domains, devices and services where you have authority or a legitimate reason.
- SSH protects the connection when keys are verified; Telnet does not encrypt traffic or credentials.
- Mail recipient tests may be logged or restricted by remote mail servers; results are not proof of mailbox existence.
- Protocol clients contacting unfamiliar servers may encounter hostile or malformed data. Do not rely on experimental support for sensitive workflows.
- The project does not claim to have completed a formal security assessment.

The public GitHub repository and its private security reporting channel have not yet been provided in this conversation. Do not post exploit details or confidential material in a public issue. A verified private contact route should be added before large-scale publication.

## Local privacy in release 0.5.3 package revision 3

Configuration and local browsing history in `~/.config/nettalabbo/settings.json`
are now saved with permissions `0600` in a directory with permissions `0700`.
The application may retain past domains, addresses and protocol URLs in local
history. Do not place access tokens or passwords in URLs. Previously saved
files under the former application names are not automatically erased.

Network and protocol inputs originate from remote peers and are untrusted. The
legacy clients are experimental, not formally audited. The included SSH console
is a basic terminal emulator rather than a full VT implementation. Do not use
this testing release for privileged or sensitive remote administration.

A report of successful contact with a server never proves that the service or
mailbox exists or that the remote system is trustworthy. Never disable SSH
host key verification as a workaround for a connection error.