# Install and upgrade Nettalabbo on Xubuntu and Ubuntu

## One-command package installation

From the directory containing the downloaded package:

```bash
sudo apt update
sudo apt install ./nettalabbo_0.5.3-7_all.deb
```

APT uses the mandatory `Depends` in the `.deb` to resolve and install required packages before Nettalabbo can be configured. Internet access and compatible configured Ubuntu repositories may be necessary. The package does not download arbitrary tools from third-party websites.

Required runtime packages: Python 3 (3.8+), Python Tkinter, Ping, Traceroute, OpenSSH client, Telnet client, CA certificates, and `bind9-dnsutils` or `dnsutils` for DNS tools. Python modules in Nettalabbo rely on the standard library; no separate `pip` command is required.

If the graphical package installer shows a spinning loading indicator forever, close that installer and use the APT command above. On some versions of Ubuntu, the graphical installer can fail to load local packages despite valid `.deb` files. The command-line APT result provides the actual dependency or packaging error, if any. Do not use `dpkg -i` as a first attempt because it does not resolve dependencies automatically.

If the APT command fails, save its full error output to report the problem (without sharing usernames or private home paths). If a graphical package installer reports unmet dependencies, use APT and read its specific error. An installed package cannot force repository availability or resolve externally held APT locks.

## Existing installations

New releases keep the Debian package name `nettalabbo`. When upgrading, APT replaces its prior version automatically. The package also declares `Conflicts`/`Replaces` with older names: `netlabbo`, `netlab-xubuntu` and `network-laboratory-xubuntu`. User preferences are preserved; previously saved settings can be migrated on first run. Do not purge old configuration directories unless you explicitly want to delete them.

## Version compatibility

The package is designed for Xubuntu and Ubuntu systems with Python 3.8 or newer. Compatibility across all Ubuntu releases has not been exhaustively tested; older Ubuntu 20.04 is outside standard security support. Network tools may vary with installed distribution packages, system permissions and the remote server.

## Run

Open Nettalabbo from the application menu or run:

```bash
nettalabbo
```

## Metadata and icon

The package ships an AppStream application description, the MIT licence, a `.desktop` launcher, and desktop icons. The appearance of the **pre-installation** icon and licence label depends on the local graphical package installer; they cannot be guaranteed solely by the `.deb` metadata. The application icon is available after installation on systems that honour the desktop specification.