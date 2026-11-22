# Historic Servers reference catalog

These addresses were cross-checked against official/public documentation on
18 November 2026, and the additional Telnet services against the telnet.org list
updated on 11 November 2026. They have **not** all been verified by live network
connection.

**Third-party services.** Every service below is run independently by its own
operator. Nettalabbo only provides the address and opens a connection when asked;
it does not host or control these services and does not guarantee that their
operators hold the licences or rights for the games, software or content they
offer. That responsibility stays with each operator. See DISCLAIMER.md.

## Telnet / BBS

| Name | Host | Port | Source |
| --- | --- | --- | --- |
| ISCABBS | bbs.iscabbs.com | 23 | https://iscabbs.rocks/connect-to-iscabbs.html |
| Telehack | telehack.com | 23 | https://telehack.com/telehack.html |
| FICS | freechess.org | 5000 | https://freechess.org/ |
| Aardwolf | aardmud.org | 4000 | https://www.aardwolf.com/play/index.htm |
| BatMUD | batmud.bat.org | 23 | https://www.bat.org/client-plugins |
| MapSCII | mapscii.me | 23 | https://github.com/rastapasta/mapscii |
| Star Wars ASCII (IPv6 only) | towel.blinkenlights.nl | 23 | https://telnet.org/htm/places.htm |
| Wikipedia over Telnet | telnet.wiki.gd | 23 | https://telnet.org/htm/places.htm |
| Doom in the terminal | doom.w-graj.net | 666 | https://telnet.org/htm/places.htm |
| Classic Mac desktop demo | www.vintagecomputing.com | 1984 | https://telnet.org/htm/places.htm |
| NyanCat alternative | halite.md.vc | 23 | https://telnet.org/htm/places.htm |
| Galacticomm BBS | gcomm.com | 23 | https://telnet.org/htm/places.htm |
| Archaic Binary BBS | bbs.archaicbinary.net | 23 | https://telnet.org/htm/places.htm |
| Legend of the Red Dragon | lord.stabs.org | 23 | https://telnet.org/htm/places.htm |
| Achaea | achaea.com | 23 | https://www.achaea.com/ |
| Avalon | avalon-rpg.com | 23 | https://telnet.org/htm/places.htm |
| ZombieMUD | zombiemud.org | 23 | https://telnet.org/htm/places.htm |
| Igor MUD | igormud.org | 1701 | https://telnet.org/htm/places.htm |
| Forgotten Kingdoms | forgottenkingdoms.org | 4000 | https://telnet.org/htm/places.htm |

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
