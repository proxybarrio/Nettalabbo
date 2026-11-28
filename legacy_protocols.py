"""Independently written, bounded, read-only small-network protocol adapters.

No code or assets from historical NetLab95. Python 3.8+ stdlib only.
No network requests at application startup; each fetch requires explicit action.
Titan uploads require a separate explicit user action; never upload while browsing.
"""
import ftplib
import hashlib
import posixpath
import re
import socket
import ssl
import threading
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit, quote, unquote

TIMEOUT=8
_fetch_state=threading.local()  # per-worker cancellation; never share between requests
MAX_BYTES=300_000
# Files (images, archives, PDFs) may be larger than text pages; they are only
# kept in memory and written to disk when the user chooses Save file.
MAX_FILE_BYTES=20_000_000
# Gopher item types that carry files rather than text (RFC 1436 and common use).
GOPHER_FILE_TYPES={'5','9','g','I','s',';','d','p','P','<'}
MAX_LINES=350

# mode: read, remote, upload, reference. A reference entry must not claim to work.
CATALOG=[
    ('Gopher',          ('gopher', 'gophers'), 70, 'read', 'Gopher menus and plain text; TLS for gophers.'),
    ('Gemini',          ('gemini',), 1965, 'read', 'TLS documents and Gemtext links. Certificate verification or explicit TOFU.'),
    ('Spartan',         ('spartan',), 300, 'read', 'Basic document retrieval; write requests not enabled.'),
    ('Nex',             ('nex',), 1900, 'read', 'Simple selector-based TCP retrieval.'),
    ('Titan',           ('titan',), 1965, 'upload', 'Explicit, confirmed TLS file upload (max 256 KiB). Never initiated by Browse.'),
    ('Scroll',          ('scroll',), 5699, 'read', 'TLS document retrieval and Scroll metadata (experimental).'),
    ('Finger',          ('finger',), 79, 'read', 'Read Finger information over TCP.'),
    ('Usenet / NNTP',   ('news', 'nntp'), 119, 'read', 'Quick read-only look at a group; the Newsgroups page reads, replies and posts.'),
    ('Telnet / SSH',    ('telnet', 'ssh'), 23, 'remote', 'Open the existing remote terminal in Nettalabbo.'),
    ('Anonymous FTP',  ('ftp',), 21, 'read', 'Anonymous directory listing; no uploads or downloads.'),
    ('DICT',            ('dict',), 2628, 'read', 'Dictionary definition lookup (RFC 2229).'),
    ('Scorpion',        ('scorpion', 'scorpions'), 1517, 'read', 'Experimental read-only R-subprotocol; plaintext Scorpion or TLS Scorpions.'),
    ('Guppy',           ('guppy',), 6775, 'read', 'UDP datagram request with acknowledgement (experimental).'),
    ('Text / SuperText',('text',), 1961, 'read', 'TEXT:// read on TCP 1961; SuperTXT is a document format.'),
    ('Molerat',         ('molerat',), 2693, 'read', 'Experimental TLS read-only GET adapter for Molerat 0.1 alpha.'),
    ('Mercury',         ('mercury',), 1958, 'read', 'Server-initiated plain text (port 1958).'),
    ('Terse',           ('terse',), None, 'reference', 'Under research: no verified interoperable terse:// transport specification; future release.'),
]
SCHEMES={scheme:dict(name=name, port=port, mode=mode, details=desc)
    for name,schemes,port,mode,desc in CATALOG for scheme in schemes}

class LegacyError(Exception):
    pass

class TrustRequired(LegacyError):
    def __init__(self, origin, fingerprint):
        self.origin=origin
        self.fingerprint=fingerprint
        super().__init__('Unverified TLS certificate at '+origin+'; SHA256 fingerprint: '+fingerprint)

@dataclass
class LegacyResult:
    address: str
    protocol: str
    status: str
    content: str
    links: list=field(default_factory=list)
    bytes_received: int=0
    raw_response: bytes=b''
    # File downloads: content holds a description, raw_response the file bytes.
    is_file: bool=False
    media_type: str=''
    truncated: bool=False
    # Gemini input request (status 10/11): prompt text and whether it is sensitive.
    input_prompt: str=''
    input_sensitive: bool=False


def parse_url(address):
    value=address.strip()
    if len(value)>2048 or any(c in value for c in '\r\n\x00'):
        raise LegacyError('URL is invalid or too long.')
    parsed=urlsplit(value)
    scheme=parsed.scheme.lower()
    if scheme not in SCHEMES: raise LegacyError('Unsupported URL scheme: '+scheme)
    if not parsed.hostname: raise LegacyError('A hostname is required.')
    try: port=parsed.port or SCHEMES[scheme]['port']
    except ValueError: raise LegacyError('Invalid port number.')
    if port is None: raise LegacyError('No verified default port for this experimental protocol.')
    if parsed.username and scheme not in ('finger','ssh'):
        raise LegacyError('Embedded credentials are not accepted. Use the dedicated SSH or Telnet page.')
    if parsed.password: raise LegacyError('Passwords in URLs are not supported.')
    return parsed, scheme, port


def safe_text(raw, char='utf-8'):
    return raw.decode(char, errors='replace')


def read_limited(sock, limit=MAX_BYTES):
    chunks=[]; size=0
    while size < limit:
        buf=sock.recv(min(8192, limit-size))
        if not buf: break
        chunks.append(buf); size+=len(buf)
    return b''.join(chunks)


def tcp_fetch(host, port, request=None, tls=False, pins=None, scheme='', limit=MAX_BYTES):
    """Close sockets promptly, preserve TLS checks, permit request cancellation."""
    stop = getattr(_fetch_state, 'stop', None)
    done = threading.Event()
    sockets = []
    if stop is not None:
        def interrupt_on_stop():
            while not done.wait(0.08):
                if stop.is_set():
                    for sock in list(sockets):
                        try: sock.shutdown(socket.SHUT_RDWR)
                        except OSError: pass
                        try: sock.close()
                        except OSError: pass
                    return
        threading.Thread(target=interrupt_on_stop, daemon=True).start()
    def open_socket(verified):
        sock=socket.create_connection((host,port),timeout=TIMEOUT)
        sockets.append(sock)
        sock.settimeout(TIMEOUT)
        if stop is not None and stop.is_set():
            sock.close()
            raise LegacyError('Request cancelled.')
        if tls:
            context=ssl.create_default_context() if verified else ssl._create_unverified_context()
            try:
                wrapped = context.wrap_socket(sock,server_hostname=host)
                sockets.append(wrapped)
                return wrapped
            except Exception:
                sock.close(); raise
        return sock
    try:
        if not tls:
            with open_socket(True) as sock:
                if request is not None: sock.sendall(request)
                return read_limited(sock, limit)
        try: sock=open_socket(True)
        except ssl.SSLCertVerificationError:
            # TOFU is an explicit consent step, never silently trusted. Existing pins are rechecked.
            sock=open_socket(False)
            digest=hashlib.sha256(sock.getpeercert(binary_form=True)).hexdigest()
            origin='{}://{}:{}'.format(scheme,host,port)
            stored=(pins or {}).get(origin)
            if stored is None:
                sock.close(); raise TrustRequired(origin,digest)
            if stored != digest:
                sock.close(); raise LegacyError('TLS certificate CHANGED for {}! Disconnecting.'.format(origin))
        with sock:
            if request is not None: sock.sendall(request)
            return read_limited(sock, limit)
    finally:
        done.set()


def relative_link(base, target):
    if any(c in target for c in '\r\n\x00'): return ''
    original=urlsplit(base); new=urlsplit(target)
    if new.scheme: return target
    if target.startswith('//'): return original.scheme+':'+target
    if target.startswith('/'): path=target
    elif target.startswith('?'): path=original.path or '/'
    else:
        parent=posixpath.dirname(original.path or '/')
        path=posixpath.normpath(posixpath.join(parent,target))
        if not path.startswith('/'): path='/'+path
    if target.startswith('?'):
        return urlunsplit((original.scheme, original.netloc, path, new.query, new.fragment))
    return urlunsplit((original.scheme, original.netloc, path, new.query, new.fragment))


def parse_gem_links(content, address):
    links=[]
    for line in content.splitlines():
        if line.lstrip().startswith('=>'):
            tokens=line.lstrip()[2:].strip().split(None,1)
            if tokens:
                destination=relative_link(address,tokens[0]);
                if destination: links.append((tokens[1] if len(tokens)>1 else tokens[0],destination))
    return links[:MAX_LINES]


def status_response(raw,address,scheme,scroll=False):
    header,sep,body=raw.partition(b'\r\n')
    if not sep:
        raise LegacyError('Missing protocol response header.')
    info=safe_text(header)
    match=re.match(r'^(\d\d)\s(.*)$',info)
    if not match: raise LegacyError('Malformed response header: '+info[:90])
    code, meta=match.groups()
    if code.startswith('1'):
        result=LegacyResult(address,scheme,code+' '+meta,'',[],len(raw),raw)
        result.input_prompt=meta.strip() or 'Input requested'
        result.input_sensitive=(code=='11')
        return result
    mime=meta.split(';',1)[0].strip().lower()
    if code.startswith('2') and mime and not mime.startswith('text/') and not scroll:
        return file_result(address,scheme,code+' '+meta,body,mime,len(raw),
                           limit=MAX_FILE_BYTES-len(header)-2)
    if len(body)>MAX_BYTES:
        body=body[:MAX_BYTES]
        meta+=' (shown up to {:,} bytes)'.format(MAX_BYTES)
    if scroll and code.startswith('2'):
        lines=body.split(b'\r\n',3)
        if len(lines)>=4:
            body=lines[3]
            meta+=' | metadata: '+', '.join(safe_text(x) for x in lines[:3])
    content=safe_text(body)
    links=parse_gem_links(content,address)
    if code.startswith('3') and '://' in meta: links.insert(0,('Redirect (not followed automatically)',meta))
    return LegacyResult(address,scheme,code+' '+meta,content,links,len(raw),raw)


def sniff_media_type(data):
    """Recognise common file signatures (used for previews and file names)."""
    signatures=((b'GIF87a','image/gif'),(b'GIF89a','image/gif'),(b'\x89PNG\r\n\x1a\n','image/png'),
                (b'\xff\xd8\xff','image/jpeg'),(b'%PDF-','application/pdf'),(b'PK\x03\x04','application/zip'),
                (b'\x1f\x8b','application/gzip'),(b'ID3','audio/mpeg'),(b'RIFF','audio/x-wav'),
                (b'OggS','audio/ogg'),(b'BM','image/bmp'))
    for magic,media in signatures:
        if data.startswith(magic):
            return media
    return 'application/octet-stream'


def file_result(address,scheme,status,data,media_type='',received=None,limit=None):
    media=media_type or sniff_media_type(data)
    if media=='application/octet-stream':
        media=sniff_media_type(data)
    truncated=len(data)>=(MAX_FILE_BYTES if limit is None else limit)
    size=len(data)
    note=('File: {} ({:,} bytes){}.\nUse Save file to store it on your computer.'
          .format(media,size,'; download stopped at the size limit, the file is incomplete' if truncated else ''))
    result=LegacyResult(address,scheme,status,note,[],received if received is not None else size,data)
    result.is_file=True
    result.media_type=media
    result.truncated=truncated
    return result


def gopher_fetch(p,scheme,port,pins):
    # RFC 1436: /<item-type><selector>, with a CRLF-terminated selector request.
    path=unquote(p.path)
    itemtype=path[1] if len(path)>1 else '1'
    selector=path[2:] if len(path)>1 else ''
    if '\r' in selector or '\n' in selector: raise LegacyError('Invalid Gopher selector.')
    if p.query: selector+='\t'+unquote(p.query)
    is_file_type=itemtype in GOPHER_FILE_TYPES
    limit=MAX_FILE_BYTES if is_file_type else MAX_BYTES
    raw=tcp_fetch(p.hostname,port,(selector+'\r\n').encode('utf-8'),scheme=='gophers',pins,scheme,limit)
    if is_file_type or (itemtype not in ('1','7') and b'\x00' in raw[:4096]):
        return file_result(p.geturl(),scheme,'Gopher file (item type {})'.format(itemtype),raw,limit=limit)
    if itemtype not in ('1','7'):
        return LegacyResult(p.geturl(),scheme,'Document',safe_text(raw),[],len(raw),raw)
    links=[]
    for line in safe_text(raw).splitlines():
        if not line or line=='.': continue
        fields=line[1:].split('\t')
        if len(fields)>=4 and line[0] not in ('i','3'):
            name,sel,host,port_str=fields[:4]
            try: gp=int(port_str)
            except ValueError: continue
            if gp<1 or gp>65535: continue
            if line[0] == 'h' and sel.startswith('URL:'):
                url = sel[4:]
            elif line[0] == '8':
                url = 'telnet://{}:{}'.format(host, gp)
            else:
                url='{}://{}:{}/{}{}'.format(scheme,host,gp,line[0],quote(sel,safe='/'))
            links.append((name,url))
    return LegacyResult(p.geturl(),scheme,'Gopher menu' if itemtype=='1' else 'Gopher search',safe_text(raw),links[:MAX_LINES],len(raw),raw)


def nntp_read(p,port):
    # Conservative, read-only wire implementation: limit article headlines.
    group=unquote(p.path.lstrip('/')).replace('/', '.')
    if '\r' in group or '\n' in group or ' ' in group: raise LegacyError('Invalid NNTP group.')
    out=[]
    with socket.create_connection((p.hostname,port),timeout=TIMEOUT) as sock:
        sock.settimeout(TIMEOUT)
        file=sock.makefile('rb')
        try:
            greeting=file.readline(2048)
            out.append(safe_text(greeting).strip())
            if not greeting.startswith((b'200',b'201')): raise LegacyError('NNTP server rejected connection.')
            if group:
                sock.sendall(('GROUP '+group+'\r\n').encode('ascii'))
                answer=safe_text(file.readline(2048)).strip(); out.append(answer)
                m=re.match(r'^211\s+\d+\s+(\d+)\s+(\d+)',answer)
                if m:
                    first,last=int(m.group(1)),int(m.group(2))
                    if last>=first and last>0:
                        sock.sendall(('OVER {}-{}\r\n'.format(max(first,last-9),last)).encode('ascii'))
                        header=safe_text(file.readline(2048)).strip(); out.append(header)
                        if header.startswith('224'):
                            for _ in range(50):
                                line=file.readline(4096)
                                if not line or line==b'.\r\n': break
                                out.append(safe_text(line).rstrip())
            sock.sendall(b'QUIT\r\n')
        finally: file.close()
    body='\n'.join(out)
    return LegacyResult(p.geturl(),'nntp','Read-only group summary',body,[],len(body.encode()))


def ftp_listing(p,port):
    directory=unquote(p.path or '/')
    if any(c in directory for c in '\r\n\x00'): raise LegacyError('Invalid FTP path.')
    lines=[]
    with ftplib.FTP() as ftp:
        ftp.connect(p.hostname,port,timeout=TIMEOUT)
        ftp.login('anonymous','anonymous@')
        ftp.retrlines('LIST '+directory,lambda s: lines.append(s) if len(lines)<MAX_LINES else None)
    return LegacyResult(p.geturl(),'ftp','Anonymous directory listing (read only)','\n'.join(lines),[],len('\n'.join(lines).encode()))


def dict_query(p,port):
    word=unquote(p.path.lstrip('/'))
    if not word: raise LegacyError('Use dict://server/word to request a definition.')
    if any(c in word for c in '\r\n\x00"'): raise LegacyError('Invalid dictionary word.')
    word=word[:128].replace('\\','\\\\')
    req=('CLIENT Nettalabbo 0.4\r\nDEFINE * "{}"\r\nQUIT\r\n'.format(word)).encode('utf-8')
    raw=tcp_fetch(p.hostname,port,req)
    return LegacyResult(p.geturl(),'dict','DICT definition',safe_text(raw),[],len(raw))


def guppy_fetch(p,port):
    # v0.4.4, bounded stop-and-wait acknowledgment; do not amplify datagrams.
    addr=p.geturl().encode('utf-8')+b'\r\n'
    if len(addr)>2048: raise LegacyError('Guppy address is too long.')
    chunks=[]; total=0; expected=None; mime='text/plain'
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(2.5)
        sock.connect((p.hostname,port))
        sock.send(addr)
        attempts=0
        while attempts<6 and total<MAX_BYTES:
            try: dat=sock.recv(64*1024)
            except socket.timeout:
                attempts+=1
                if expected is None: sock.send(addr)
                else: sock.send(str(expected-1).encode('ascii')+b'\r\n')
                continue
            attempts=0
            head,sep,data=dat.partition(b'\r\n')
            if not sep:
                plain=safe_text(dat)
                return LegacyResult(p.geturl(),'guppy','Response '+plain[:160],plain,[],len(dat))
            first=head.split(b' ',1)
            try: seq=int(first[0])
            except ValueError: raise LegacyError('Invalid Guppy packet sequence.')
            if seq < 6: raise LegacyError('Invalid Guppy sequence number.')
            if expected is None:
                expected=seq
                if len(first)>1: mime=safe_text(first[1])
            if seq==expected:
                sock.send(str(seq).encode('ascii')+b'\r\n')
                if not data: break
                chunks.append(data); total+=len(data);expected+=1
            elif seq==expected-1:
                sock.send(str(seq).encode('ascii')+b'\r\n')
            else:
                raise LegacyError('Unexpected Guppy sequence number.')
    raw=b''.join(chunks)
    text=safe_text(raw)
    return LegacyResult(p.geturl(),'guppy','Guppy '+mime,text,parse_gem_links(text,p.geturl()),len(raw))


def fetch(address,pins=None,stop=None):
    """Use a request-local stop event to close active simple TCP connections."""
    _fetch_state.stop = stop
    try:
        return _fetch_dispatch(address, pins)
    finally:
        _fetch_state.stop = None


def _fetch_dispatch(address, pins=None):
    p,scheme,port=parse_url(address)
    mode=SCHEMES[scheme]['mode']
    if mode=='remote':
        raise LegacyError('Open '+scheme.upper()+' in Remote access; interactive sessions are managed there.')
    if mode=='upload':
        raise LegacyError('Titan is upload-only. Use the separate Titan upload button and confirm your action.')
    if mode=='reference':
        raise LegacyError('Experimental protocol '+scheme+' is listed for reference but not implemented.')
    if scheme=='molerat':
        # molerat 0.1 alpha: GET authority/path + CRLF CRLF, TLS with explicit TOFU.
        target = p.netloc + (p.path or '/')
        if p.query: target += '?' + p.query
        if p.fragment: target += '#' + p.fragment  # alpha spec includes fragment
        raw=tcp_fetch(p.hostname,port,('get '+target+'\r\n\r\n').encode('utf-8'),True,pins,scheme)
        header,separator,body=raw.partition(b'\r\n\r\n')
        if not separator: raise LegacyError('Malformed Molerat headers.')
        lines=safe_text(header).split('\r\n')
        if not re.fullmatch(r'\d{2}',lines[0]): raise LegacyError('Invalid Molerat status code.')
        metadata={}
        for line in lines[1:]:
            if ':' in line:
                k,v=line.split(':',1)
                metadata[k.lower().strip()]=v.strip().strip('\t')
        if len(body)>MAX_BYTES: body=body[:MAX_BYTES]
        content=safe_text(body)
        links=parse_gem_links(content,address)
        if lines[0].startswith('2') and metadata.get('message','').startswith('molerat://'):
            links.insert(0,('Redirect (not followed)',metadata['message']))
        status='{} {} {}'.format(lines[0],metadata.get('type',''),metadata.get('message',''))
        return LegacyResult(address,scheme,status,content,links,len(raw),raw)
    if scheme in ('scorpion','scorpions'):
        # Scorpion R subprotocol, a single read-only request with explicit scheme.
        # Unencrypted Scorpion is the mandatory transport. TLS variant is optional.
        without_fragment=address.partition('#')[0]
        raw=tcp_fetch(p.hostname,port,('R '+without_fragment+'\r\n').encode('utf-8'),
                      scheme=='scorpions',pins,scheme)
        head,sep,body=raw.partition(b'\r\n')
        if not sep: raise LegacyError('Malformed Scorpion status line.')
        status=safe_text(head)
        if not re.match(r'^\d\d(?:\s|$)',status):
            raise LegacyError('Invalid Scorpion status.')
        content=safe_text(body)
        return LegacyResult(address,scheme,status,content,parse_gem_links(content,address),len(raw),raw)
    if scheme in ('gopher','gophers'): return gopher_fetch(p,scheme,port,pins)
    if scheme=='ftp': return ftp_listing(p,port)
    if scheme in ('news','nntp'): return nntp_read(p,port)
    if scheme=='dict': return dict_query(p,port)
    if scheme=='guppy': return guppy_fetch(p,port)
    if scheme=='mercury':
        if p.path not in ('','/'): raise LegacyError('Mercury addresses designate a server and port, not a path.')
        raw=tcp_fetch(p.hostname,port)
        return LegacyResult(address,scheme,'Mercury plain text',safe_text(raw),[],len(raw),raw)
    if scheme=='finger':
        name=unquote(p.username or p.path.lstrip('/'))
        if any(c in name for c in '\r\n\x00'): raise LegacyError('Invalid Finger name.')
        raw=tcp_fetch(p.hostname,port,(name+'\r\n').encode('utf-8'))
        return LegacyResult(address,scheme,'Finger response',safe_text(raw),[],len(raw),raw)
    if scheme=='nex':
        path=unquote(p.path or '/')
        if any(c in path for c in '\r\n'): raise LegacyError('Invalid Nex path.')
        raw=tcp_fetch(p.hostname,port,(path+'\r\n').encode('utf-8'))
        text=safe_text(raw)
        links=parse_gem_links(text,address)
        return LegacyResult(address,scheme,'Nex document',text,links,len(raw),raw)
    if scheme=='spartan':
        path=p.path or '/'
        if p.query: path+='?'+p.query
        if ' ' in p.hostname or any(c in path for c in '\r\n'): raise LegacyError('Invalid Spartan address.')
        raw=tcp_fetch(p.hostname,port,('{} {} 0\r\n'.format(p.hostname,path)).encode('utf-8'))
        # Spartan response: <single digit> <meta> CRLF + body
        first,sep,body=raw.partition(b'\r\n')
        if not sep: raise LegacyError('Spartan response has no header.')
        info=safe_text(first)
        if not re.match(r'^\d\s',info): raise LegacyError('Invalid Spartan status header.')
        text=safe_text(body)
        return LegacyResult(address,scheme,info,text,parse_gem_links(text,address),len(raw),raw)
    if scheme in ('gemini','scroll','text'):
        if scheme=='scroll': req=(address+' en\r\n').encode('utf-8')
        else: req=(address+'\r\n').encode('utf-8')
        use_tls=scheme in ('gemini','scroll')
        raw=tcp_fetch(p.hostname,port,req,use_tls,pins,scheme,MAX_FILE_BYTES)
        return status_response(raw,address,scheme,scroll=scheme=='scroll')
    raise LegacyError('No compatible adapter for '+scheme)


def titan_upload(address, data, pins=None, mime='application/octet-stream'):
    """Explicit Titan upload; never called by fetch(). Zero-byte uploads forbidden."""
    p, scheme, port = parse_url(address)
    if scheme != 'titan': raise LegacyError('Titan upload requires titan:// URL.')
    if not isinstance(data, bytes) or not 0 < len(data) <= 262144:
        raise LegacyError('Upload requires 1 to 262144 bytes; zero-byte may mean DELETE.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.+/-]{0,80}', mime):
        raise LegacyError('Invalid Titan MIME type.')
    if p.fragment: raise LegacyError('Fragments are not valid for Titan upload.')
    # Parameters belong at the end of the path, before CRLF, per Titan spec.
    upload_url=address+';size={};mime={}'.format(len(data),mime)
    if len(upload_url)>2048: raise LegacyError('Titan address is too long.')
    request=upload_url.encode('utf-8')+b'\r\n'+data
    raw=tcp_fetch(p.hostname,port,request,True,pins,scheme)
    return status_response(raw,address,scheme)
