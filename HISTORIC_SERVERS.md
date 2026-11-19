# Historic Servers reference catalog

These addresses were cross-checked against official/public documentation on
18 November 2026. They have **not** all been verified by live network connection.

## Telnet / BBS

| Name | Host | Port | Source |
| --- | --- | --- | --- |
| ISCABBS | bbs.iscabbs.com | 23 | https://iscabbs.rocks/connect-to-iscabbs.html |
| Telehack | telehack.com | 23 | https://telehack.com/telehack.html |
| FICS | freechess.org | 5000 | https://freechess.org/ |
| Aardwolf | aardmud.org | 4000 | https://www.aardwolf.com/play/index.htm |
| BatMUD | batmud.bat.org | 23 | https://www.bat.org/client-plugins |

## UNIX / SSH

| Name | Host | Port | Source |
| --- | --- | --- | --- |
| Nyx | nyx.nyx.net | 22 | https://www.nyx.net/ |
| SDF | tty.sdf.org | 22 | https://wiki.sdf.org/doku.php?id=logging_in_to_sdf_servers |
| Panix | shell.panix.com | 22 | https://www.panix.com/help/serverinfo.html |
| Eskimo North | eskimo.com | 22 | https://www.eskimo.com/services/shells/servers/ |

## Web references and protocol transition

* The WELL: https://www.well.com/
* Tildeverse: https://tildeverse.org/
* NASA Horizons: https://ssd.jpl.nasa.gov/horizons/horizons_tls_access.html
  As of October 2026, use the NASA-documented TLS bridge, not unsecured direct Telnet.

The directory deliberately does not start sessions or test remote hosts without
user action. No guarantee is made that an endpoint is reachable at any given time.

## Two connection choices

Historic Servers always displays **Connect via SSH** and **Connect via Telnet**.
The documented access method uses its published port. An unconfirmed method
triggers an explicit warning before the connection is attempted (using default
port 22 for SSH and 23 for Telnet).

Not every listed service accepts both protocols. SSH may require a registered
account. Telnet does not encrypt passwords or network traffic.