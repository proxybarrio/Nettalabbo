# Security and privacy

Nettalabbo is an experimental network utility and is not a substitute for a security audit.

- Only inspect domains, devices and services where you have authority or a legitimate reason.
- SSH protects the connection when keys are verified; Telnet does not encrypt traffic or credentials.
- Mail recipient tests may be logged or restricted by remote mail servers; results are not proof of mailbox existence.
- Protocol clients contacting unfamiliar servers may encounter hostile or malformed data. Do not rely on experimental support for sensitive workflows.
- The project does not claim to have completed a formal security assessment.

The code is hosted at https://github.com/proxybarrio/Nettalabbo. The repository is currently private. Report sensitive findings privately through the project contact rather than a public issue; maintainers should establish a dedicated confidential reporting route before public distribution.

## Local privacy and diagnostics in 0.5.4

Configuration and local browsing history in `~/.config/nettalabbo/settings.json`
are now saved with permissions `0600` in a directory with permissions `0700`.
The application may retain past domains, addresses and protocol URLs in local
history. Do not place access tokens or passwords in URLs. Previously saved
files under the former application names are not automatically erased.

In Diagnose, DNS queries are made only when the user explicitly runs the check. Optional SMTP and DNSBL probes are disabled by default. Enabling DNSBL submits the selected domain and public MX server addresses to external DNS blacklist providers, which may log queries or reject unsupported resolver networks. A DNSBL response, including an empty response, does not guarantee a clean reputation; access and policy errors are reported as unknown. SPF, DKIM, DMARC and TLS results are limited diagnostics rather than proof of email delivery.

Network and protocol inputs originate from remote peers and are untrusted. The
legacy clients are experimental, not formally audited. The included SSH console
is a basic terminal emulator rather than a full VT implementation. Do not use
this testing release for privileged or sensitive remote administration.

A report of successful contact with a server never proves that the service or
mailbox exists or that the remote system is trustworthy. Never disable SSH
host key verification as a workaround for a connection error.
