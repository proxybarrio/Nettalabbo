**Addendum (revision 0.5.3-4, 19 November 2026):** Approved project contact now installed; About includes full offline credits, disclaimer, story and MIT licence. Other outstanding legal and security checks below are unchanged.

# Nettalabbo 0.5.3: intellectual property, licensing and security prepublication review

**Review date:** 19 November 2026  
**Scope:** Supplied `nettalabbo-source-0.5.3-rev2.zip`, `nettalabbo_0.5.3-2_all.deb`, historical `netlab14.zip`, related project documents, and public legal/trademark sources.  
**Conclusion:** Suitable for continued private testing; **not certified as legally cleared or security-audited for public distribution**. No project has been created or modified on GitLab.

## Checklist (the five agreed actions)

| Item | Status | Work carried out | Residual dependency |
| --- | --- | --- | --- |
| 1. Trademark review | PARTIAL | Web checks for Nettalabbo, NetLab95, NETLAB and NETLAB+. NETLAB+ is an asserted registered mark in software/networking education; no immediately indexed exact Nettalabbo result surfaced. | Check actual live UKIPO, EUIPO/TMview, WIPO, relevant US register records, similarity, class and status before launch. |
| 2. Code / asset provenance | SOURCE FILE CHECK COMPLETED | Listed and hashed 62 delivered source files against 18 original archive entries; no identical files. Historic Windows binaries and help files absent. Approved AI icon SHA-256 matched. | A binary/file-level audit cannot establish complete non-infringement or prove independent creation of every expressive detail. |
| 3. Credits / attribution | REVIEWED AND CLARIFIED | MIT licence, author attribution and legal independence statements checked; notes about AI authorship and limits added. | Do not claim Danileiko's approval without written permission; obtain further review for public release. |
| 4. Network security | PRELIMINARY STATIC REVIEW; ONE FIX | Inspected SSH, Telnet, mail, scanners and experimental protocol adapters. Tightened permissions on local config/history and added regression test. | Fuzzing, live-server tests, threat modelling and dependency security scan remain undone. |
| 5. Distribution metadata | PARTIAL | Verified Debian metadata, AppStream, launcher and package version; improved release review documentation. | Historical audit snapshot: the earlier package used a placeholder address. **Resolved in Debian revision 0.5.3-4:** the approved contact `proxybar@gmail.com` is now included. |

## High-priority practical follow-up

* Carry out actual registry searches and review NETLAB+ before widespread public launch.
* Maintainer contact: resolved in revision 0.5.3-4, using the explicitly approved address `proxybar@gmail.com`.
* Create or confirm the public GitLab repository under the requested `proxybarrio` account, update valid issue and security reporting links, then publish the source and release.
* Run the full package and interface on Xubuntu 20.04 and a currently supported Xubuntu version. Confirm mail, WHOIS, TLS and SSH behavior.
* Before calling this a stable security utility, test with deliberately malformed legacy protocol responses and review the TLS fingerprint trust flow.

## Legal note

In *SAS Institute v World Programming* (CJEU C-406/10) the court distinguished software functionality from protected source and object code and other original expression, while allowing that parts of manuals may receive separate protection. The historical name and original software are acknowledged only as inspiration and not repackaged or claimed as endorsed. This review does **not** promise zero infringement risk and is not a trademark clearance opinion or personalised legal advice.

## Reference sources

- UKIPO official search: https://www.gov.uk/search-for-trademark
- EUIPO TMview: https://www.euipo.europa.eu/en/search-ip
- WIPO Global Brand Database: https://www.wipo.int/en/web/global-brand-database/index
- NETLAB+ owner statement: https://www.netdevgroup.com/support/trademark_usage.html
- NETLAB US trademark application abandoned: https://trademarks.justia.com/780/46/netlab-78046583.html (secondary source, recheck official status)
- CJEU SAS v World Programming, 2 May 2012: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A62010CJ0406
- UK government on AI and copyright: https://www.gov.uk/government/consultations/copyright-and-artificial-intelligence/copyright-and-artificial-intelligence