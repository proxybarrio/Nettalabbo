"""Conservative review of public mail authentication DNS TXT records.

These checks do not prove message authentication or email delivery.
"""
import re

def txt_value(value):
    """Join quoted character strings within one TXT resource record."""
    if '"' not in value:
        return value.strip()  # already a single unquoted string
    parts = re.findall(r'"(?:[^"\\]|\\.)*"|\S+', value)
    return ''.join(part[1:-1].replace('\\\"', '"') if part.startswith('"') and part.endswith('"') else part for part in parts)

def spf_review(records):
    policies = [txt_value(x) for x in records if txt_value(x).lower().startswith('v=spf1')]
    if not policies: return ('warn', 'No SPF policy published')
    if len(policies) > 1: return ('fail', 'Multiple SPF policies cause permerror')
    terms = policies[0].split()
    if not terms or terms[0].lower() != 'v=spf1':
        return ('fail', 'Invalid SPF version')
    lookups = 0
    redirects = 0
    all_terms = 0
    for token in terms[1:]:
        base = token.lstrip('+-~?').lower()
        if '=' in base.split(':', 1)[0]:
            key = base.split('=', 1)[0]
            if key not in ('redirect', 'exp'):
                # RFC 7208 section 6: unknown modifiers MUST be ignored.
                if re.fullmatch(r'[a-z][a-z0-9_.-]*', key):
                    continue
                return ('warn', 'Malformed SPF modifier: ' + token[:50])
        else:
            # Mechanism name ends at ':' (domain) or '/' (CIDR length), e.g. a/24, mx:host/24.
            key = re.split(r'[:/]', base, 1)[0]
        if key == 'redirect':
            redirects += 1
            lookups += 1
        elif key == 'all':
            all_terms += 1
        elif key in ('include', 'a', 'mx', 'ptr', 'exists'):
            lookups += 1
        elif key in ('ip4', 'ip6', 'exp'):
            pass
        else:
            return ('warn', 'Unrecognised SPF mechanism or modifier: ' + token[:50])
    if redirects > 1: return ('fail', 'Multiple redirect modifiers')
    if lookups > 10: return ('fail', 'More than ten DNS-dependent SPF terms')
    if all_terms > 1: return ('warn', 'Multiple all mechanisms')
    if not all_terms and not redirects: return ('warn', 'No all or redirect mechanism')
    return ('pass', 'SPF policy present; recursive lookup expansion not verified')

def dmarc_review(records):
    policies = [txt_value(x) for x in records if txt_value(x).lower().startswith('v=dmarc1')]
    if not policies: return ('warn', 'No DMARC policy published')
    if len(policies) > 1: return ('fail', 'Multiple DMARC policies')
    tags = {}
    for part in policies[0].split(';'):
        part = part.strip()
        if not part: continue
        if '=' not in part: return ('fail', 'Malformed DMARC tag')
        key, val = part.split('=', 1)
        key, val = key.strip().lower(), val.strip()
        if not re.fullmatch(r'[a-z][a-z0-9]*', key) or key in tags:
            return ('fail', 'Invalid or duplicate DMARC tag: ' + key[:25])
        tags[key] = val
    if tags.get('v', '').upper() != 'DMARC1':
        return ('fail', 'Invalid DMARC version')
    if tags.get('p', '').lower() not in ('none', 'quarantine', 'reject'):
        return ('fail', 'Missing or invalid DMARC p= policy')
    if tags.get('sp', 'none').lower() not in ('none', 'quarantine', 'reject'):
        return ('fail', 'Invalid subdomain policy sp=')
    if tags.get('adkim', 'r').lower() not in ('r', 's') or tags.get('aspf', 'r').lower() not in ('r', 's'):
        return ('fail', 'Invalid alignment mode')
    if 'pct' in tags and (not tags['pct'].isdigit() or not 0 <= int(tags['pct']) <= 100):
        return ('fail', 'Invalid pct percentage')
    return ('pass' if tags['p'].lower() in ('reject', 'quarantine') else 'warn',
            'DMARC p=' + tags['p'] + '; actual messages not tested')

def dkim_review(records):
    if not records: return ('warn', 'No DKIM key at selected selector')
    if len(records) != 1: return ('fail', 'Multiple DKIM TXT records')
    tags = {}
    for part in txt_value(records[0]).split(';'):
        if '=' in part:
            k,v = part.split('=',1)
            k = k.strip().lower()
            if k in tags: return ('fail', 'Duplicate DKIM tag')
            tags[k] = v.strip()
    if tags.get('v', 'DKIM1').upper() != 'DKIM1':
        return ('fail', 'Unsupported DKIM version')
    if not tags.get('p'):
        return ('warn', 'DKIM key empty or revoked')
    return ('pass', 'DKIM public key present; no signature tested')
