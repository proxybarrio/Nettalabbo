# Outstanding inputs and verification tasks before a public GitHub release

1. **Maintainer contact (RESOLVED in 0.5.3-4):** `proxybar@gmail.com` was explicitly provided as the public project contact and is used in the Debian package. Do not add further personal details.
2. **Live trademark clearance:** consult the UK, EU, international and any target-market national trademark registers for similar names, especially NETLAB+.
3. **Real GitHub destination:** confirm actual repository path and security reporting procedure before adding issue URLs to the application. The authenticated account is proxybarrio; the proposed repository name is nettalabbo. Confirm the repository after creation.
4. **Linux compatibility:** installation and use have been tested on Xubuntu 20.04; repeat the test on the current Xubuntu release for each new build.
5. **Security:** validate SSH and Telnet authentication, hostile legacy responses and confidential-data handling.

This is a limited audit package, not a certificate that distribution is risk-free.

- **In-app updates:** they require public GitHub Releases (`v<version>` tag with the .deb and SHA256SUMS). Test the full update path on Xubuntu, including the pkexec password prompt, before relying on it.
