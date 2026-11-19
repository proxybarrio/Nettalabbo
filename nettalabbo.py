#!/usr/bin/env python3
"""Nettalabbo: independent, open source network diagnostics for Ubuntu-based systems.

No binary code or graphical assets from NetLab 1.4 are included.
Python 3 and tkinter are required. External ping/traceroute executables are used.
"""
from __future__ import annotations
import concurrent.futures
import datetime as dt
import errno
import ipaddress
import json
import os
import tempfile
import platform
import queue
import re
import selectors
import shutil
import socket
import stat
import struct
import sys
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk, simpledialog
from domain_rdap import lookup_domain, LookupError, normalise_domain
from remote_terminal import PtySession, TerminalScreen, connection_command
from terminal_colours import ColourTerminalScreen
from diagnose import diagnose as run_domain_diagnose
from legacy_protocols import CATALOG, SCHEMES, fetch as legacy_fetch, parse_url as parse_legacy_url, TrustRequired, LegacyError, titan_upload
from mail_inspector import inspect_address, normalise_email, test_mail_service, MailInspectionError
import time_services
import service_catalog
import dns_lookup
import updater
from historic_servers import HISTORIC_SERVERS, catalog_groups, get_entry, connection_fields, protocol_endpoint, access_label
from about_documents import load_about_document, ABOUT_DOCUMENTS
from legacy_view import segments as legacy_segments, raw_text as legacy_raw_text, distinct_links as legacy_distinct_links
from legacy_theme import THEME_NAMES as LEGACY_THEME_NAMES, palette as legacy_palette, link_legend as legacy_link_legend
from urllib.parse import urlsplit, urlunsplit, quote as url_quote
import webbrowser

VERSION = '0.5.4'
PACKAGE_VERSION = '0.5.4-1'  # must match packaging/control
APP_DIR = Path.home() / '.config' / 'nettalabbo'
ASSETS_DIR = Path(__file__).resolve().parent / 'assets'
LEGACY_SETTINGS_FILES = [
    Path.home() / '.config' / 'netlabbo' / 'settings.json',
    Path.home() / '.config' / 'network-laboratory-xubuntu' / 'settings.json',
    Path.home() / '.config' / 'netlab-xubuntu' / 'settings.json',
]
SETTINGS_FILE = APP_DIR / 'settings.json'


def _restrict_mode(path, mode):
    """chmod a path owned by the current user, never following symlinks."""
    try:
        info = path.lstat()
    except OSError:
        return
    if stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
        return
    if stat.S_IMODE(info.st_mode) & ~mode:
        try:
            path.chmod(mode)
        except OSError:
            pass


def open_tcp_ports(host, ports, timeout, stop=None, batch=32):
    """Return the ports of host that accept a TCP connection.

    Connections are attempted concurrently in batches with non-blocking
    sockets, so a silent host costs about one timeout per batch instead of
    one timeout per port. At most `batch` sockets are open per call.
    """
    try:
        family = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)[0][0]
    except OSError:
        return []
    found = []
    ports = list(ports)
    for start in range(0, len(ports), batch):
        if stop is not None and stop.is_set():
            break
        selector = selectors.DefaultSelector()
        pending = {}
        try:
            for port in ports[start:start + batch]:
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.setblocking(False)
                code = sock.connect_ex((host, port))
                if code == 0:
                    found.append(port)
                    sock.close()
                elif code in (errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EAGAIN):
                    selector.register(sock, selectors.EVENT_WRITE, port)
                    pending[sock] = port
                else:
                    sock.close()
            deadline = time.monotonic() + timeout
            while pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or (stop is not None and stop.is_set()):
                    break
                for key, _events in selector.select(min(remaining, 0.25)):
                    sock = key.fileobj
                    if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
                        found.append(key.data)
                    selector.unregister(sock)
                    sock.close()
                    del pending[sock]
        finally:
            for sock in pending:
                sock.close()
            selector.close()
    return sorted(found)


def default_printer():
    """Name of the default CUPS destination, or '' when none is set."""
    if not shutil.which('lpstat'):
        return ''
    try:
        result = subprocess.run(['lpstat', '-d'], capture_output=True, text=True, timeout=5, check=False,
                                env={**os.environ, 'LC_ALL': 'C'})
    except (OSError, subprocess.TimeoutExpired):
        return ''
    match = re.search(r'system default destination:\s*(\S+)', result.stdout)
    return match.group(1) if match else ''


def harden_private_paths(app_dir=None, legacy_files=None):
    """Tighten permissions left by releases that wrote with the default umask.

    Configuration directories become 0700 and the regular files directly
    inside them 0600, for the current directory and the legacy locations
    from which settings are still migrated. Nothing is created or deleted.
    """
    app_dir = APP_DIR if app_dir is None else app_dir
    legacy_files = LEGACY_SETTINGS_FILES if legacy_files is None else legacy_files
    directories = [app_dir, *(Path(p).parent for p in legacy_files)]
    for directory in directories:
        if directory.is_symlink() or not directory.is_dir():
            continue
        _restrict_mode(directory, 0o700)
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_symlink() and entry.is_file():
                _restrict_mode(entry, 0o600)
# Independent navigation architecture, not a recreation of the classic tab strip.
SECTIONS = {
    'Start': ['Overview'],
    'Domain research': ['Domain Inspector', 'DNS', 'WhoIs'],
    'Mail systems': ['Mail Inspector', 'Diagnose'],
    'Network checks': ['Ping', 'Trace', 'Scanner'],
    'Remote access': ['SSH', 'Telnet'],
    'Classic services': ['Finger', 'Time', 'Quote'],
    'Legacy stuff': ['Legacy Navigator'],
    'Application': ['Info', 'Options', 'About'],
}
PAGE_LABELS = {
    'Overview': 'Welcome', 'Domain Inspector': 'Domain Inspector',
    'Legacy Navigator': 'Legacy Stuff',
    'Mail Inspector': 'Mail Server Inspector', 'Diagnose': 'Domain and Mail Diagnose',
    'WhoIs': 'WhoIs', 'Trace': 'Trace',
    'Scanner': 'Port Scan', 'Info': 'Info',
    'Options': 'Options', 'About': 'About Nettalabbo',
}
PAGE_DESCRIPTIONS = {
    'Overview': 'A practical workspace for understanding networks, domains and remote hosts.',
    'Legacy Navigator': 'Browse classic networks through clickable, underlined links. Switch between rendered and raw protocol views.',
    'Mail Inspector': 'Inspect MX routing, optional single-address SMTP acceptance, and POP3/IMAP/SMTP connectivity.',
    'Diagnose': 'Inspect DNS, MX, SPF, DMARC, DKIM and opt-in DNS blacklists.',
    'Domain Inspector': 'Identify a public domain registry, then request available registration information.',
    'DNS': 'Resolve domain names and inspect addresses.',
    'WhoIs': 'Query a chosen WHOIS server directly, or use Domain Inspector for automatic discovery.',
    'Ping': 'Measure network reachability and response time.',
    'Trace': 'Trace the network route to a remote host.',
    'Scanner': 'Scan ports and discover hosts on authorised networks.',
    'SSH': 'Encrypted terminal connections using your local OpenSSH client.',
    'Telnet': 'Legacy unencrypted terminal connections.',
    'Finger': 'Look up historical Finger service information.',
    'Time': 'Inspect remote time without changing the local clock.',
    'Quote': 'Retrieve a traditional Quote of the Day message.',
    'Info': 'Inspect local system and network configuration.',
    'Options': 'Adjust application options, local preferences and saved history.',
    'About': 'Credits, independent authorship and project licence.',
}

TABS = [tab for group in SECTIONS.values() for tab in group]
SERVICE_PORTS = {'Echo': None, 'Time': 37, 'FTP': 21, 'Telnet': 23, 'HTTP': 80,
                 'DNS': 53, 'SMTP': 25, 'POP3': 110, 'NNTP': 119}

class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f'Nettalabbo {VERSION}')
        self.app_icon = self.load_image(64)
        if self.app_icon is not None:
            self.root.iconphoto(True, self.app_icon)
        self.root.geometry('1160x820')
        self.root.minsize(1020, 700)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.tasks = {}
        self.failed_tasks = set()
        self.task_outcomes = {}
        self.events = queue.Queue()
        self.pages = {}
        self.inputs = {}
        self.output = {}
        self.status = {}
        self.trees = {}
        self.history_boxes = {}
        self.remote_sessions = {}
        self.remote_consoles = {}
        self.remote_screens = {}
        self.remote_status = {}
        self.remote_buttons = {}
        self.legacy_history = []  # cached documents for Back/Forward without new network traffic
        self.legacy_history_position = -1
        self.legacy_current_result = None
        self.settings = self.read_settings()
        self.style = ttk.Style(root)
        if 'clam' in self.style.theme_names():
            self.style.theme_use('clam')
        self.style.configure('Treeview', rowheight=24)
        self.style.configure('TButton', padding=(8, 5))
        self.style.configure('TLabel', background='#ffffff', foreground='#193549')
        self.style.configure('TLabelframe', background='#ffffff')
        self.style.configure('TLabelframe.Label', background='#ffffff', foreground='#193549')
        self.style.configure('TFrame', background='#ffffff')
        self.style.configure('Accent.TButton', background='#d7f0f7', foreground='#065b77')
        root.configure(bg='#eaf3f8')
        self.active_page = 'Overview'
        self.nav_buttons = {}

        # A dashboard with a persistent left navigation rail and a dedicated work panel.
        # This is not based on NetLab95's tabbed dialogs or their layout resources.
        banner = tk.Frame(root, bg='#fafdff', padx=16, pady=10, highlightbackground='#c7dce7', highlightthickness=1)
        banner.pack(fill='x')
        self.header_icon = self.load_image(48)
        if self.header_icon is not None:
            tk.Label(banner, image=self.header_icon, bg='#fafdff').pack(side='left', padx=(0, 12))
        brand_text = tk.Frame(banner, bg='#fafdff')
        brand_text.pack(side='left', fill='x', expand=True)
        tk.Label(brand_text, text='Nettalabbo', font=('Sans', 20, 'bold'),
                 bg='#fafdff', fg='#125a7a').pack(anchor='w')
        tk.Label(brand_text, text='Network Laboratory app for Xubuntu and other Ubuntu systems',
                 font=('Sans', 10), bg='#fafdff', fg='#46667a').pack(anchor='w')
        tk.Label(banner, text='OPEN SOURCE  ·  LINUX', font=('Sans', 9, 'bold'),
                 bg='#dff6ed', fg='#17634d', padx=9, pady=6).pack(side='right')

        body = tk.Frame(root, bg='#eaf3f8')
        body.pack(fill='both', expand=True, padx=12, pady=(12, 8))
        rail = tk.Frame(body, width=224, bg='#eef7fb', highlightbackground='#c6dae4', highlightthickness=1)
        rail.pack(side='left', fill='y', padx=(0, 12))
        rail.pack_propagate(False)
        tk.Label(rail, text='WORK AREAS', anchor='w', padx=14, pady=12,
                 font=('Sans', 10, 'bold'), bg='#d7ecf5', fg='#28617c').pack(fill='x')
        rail_body = tk.Frame(rail, bg='#eef7fb')
        rail_body.pack(fill='both', expand=True)
        self.nav_canvas = tk.Canvas(rail_body, bg='#eef7fb', highlightthickness=0, width=201)
        nav_scroll = ttk.Scrollbar(rail_body, orient='vertical', command=self.nav_canvas.yview)
        self.nav_canvas.configure(yscrollcommand=nav_scroll.set)
        nav_scroll.pack(side='right', fill='y')
        self.nav_canvas.pack(side='left', fill='both', expand=True)
        nav_items = tk.Frame(self.nav_canvas, bg='#eef7fb')
        window_id = self.nav_canvas.create_window((0, 0), window=nav_items, anchor='nw')
        nav_items.bind('<Configure>', lambda event: self.nav_canvas.configure(scrollregion=self.nav_canvas.bbox('all')))
        self.nav_canvas.bind('<Configure>', lambda event: self.nav_canvas.itemconfigure(window_id, width=event.width))
        for section, names in SECTIONS.items():
            tk.Label(nav_items, text=section.upper(), bg='#eef7fb', fg='#557388',
                     font=('Sans', 9, 'bold'), anchor='w', padx=14, pady=8).pack(fill='x', pady=(4, 0))
            for page in names:
                title = PAGE_LABELS.get(page, page)
                # Amiga-era raised vertical tab treatment: original left-side arrangement.
                b = tk.Button(nav_items, text=title, anchor='w', relief='raised', borderwidth=2,
                              font=('Sans', 10), bg='#d9e7ee', fg='#24495f',
                              activebackground='#ffffff', activeforeground='#073f5d',
                              highlightthickness=0, padx=13, pady=5, cursor='hand2',
                              command=lambda p=page: self.select_page(p))
                b.pack(fill='x', padx=(7, 0), pady=1)
                self.nav_buttons[page] = b
        self.page_host = tk.Frame(body, bg='#ffffff', highlightbackground='#c6dae4', highlightthickness=1)
        self.page_host.pack(side='left', fill='both', expand=True)
        title_area = tk.Frame(self.page_host, bg='#fafdff', padx=18, pady=11)
        title_area.pack(fill='x')
        self.workspace_title = tk.Label(title_area, text='', font=('Sans', 17, 'bold'),
                                        bg='#fafdff', fg='#154f71')
        self.workspace_title.pack(anchor='w')
        self.workspace_subtitle = tk.Label(title_area, text='', font=('Sans', 10),
                                           bg='#fafdff', fg='#537284', wraplength=650, justify='left')
        self.workspace_subtitle.pack(anchor='w', pady=(3, 0))
        tk.Frame(self.page_host, height=2, bg='#d8ecf5').pack(fill='x')
        self.activity_strip = tk.Frame(self.page_host, bg='#fff8e5', padx=15, pady=6)
        self.activity_caption = tk.StringVar(value='')
        tk.Label(self.activity_strip, textvariable=self.activity_caption, bg='#fff8e5',
                 fg='#6e5215', anchor='w').pack(side='left', padx=(0, 12))
        self.activity_bar = ttk.Progressbar(self.activity_strip, orient='horizontal',
                                             mode='indeterminate', length=230)
        self.activity_bar.pack(side='left', fill='x', expand=True)
        self.activity_started = {}
        area = ttk.Frame(self.page_host)
        area.pack(fill='both', expand=True)
        area.grid_rowconfigure(0, weight=1)
        area.grid_columnconfigure(0, weight=1)
        for name in TABS:
            page = ttk.Frame(area, padding=(16, 13))
            page.grid(row=0, column=0, sticky='nsew')
            self.pages[name] = page
        self.make_overview_page()
        self.make_domain_page()
        self.make_mail_page()
        self.make_diagnose_page()
        for name in ['Finger', 'WhoIs', 'Quote', 'DNS', 'Ping', 'Trace']:
            self.make_network_page(name)
        self.make_time_page()
        self.make_legacy_page()
        self.make_scanner_page()
        self.make_remote_page('SSH')
        self.make_remote_page('Telnet')
        self.make_info_page()
        self.make_options_page()
        self.make_about_page()
        footer = tk.Frame(root, bg='#eaf3f8')
        footer.pack(fill='x', padx=13, pady=(0, 9))
        self.footer_status = tk.StringVar(value='Ready. No network operations run at startup.')
        tk.Label(footer, textvariable=self.footer_status, bg='#eaf3f8', fg='#34596c').pack(side='left', fill='x', expand=True)
        ttk.Button(footer, text='Help', command=self.show_help, width=10).pack(side='right', padx=(6, 0))
        ttk.Button(footer, text='Quit', command=self.close, width=10).pack(side='right')
        self.root.bind('<Control-s>', lambda event: self.save_output(self.current_page()))
        self.root.bind('<F1>', lambda event: self.show_help())
        chosen = self.settings.get('last_tab', 'Overview') if self.settings.get('remember_last_function', True) else 'Overview'
        if chosen not in TABS: chosen = 'Overview'
        self.select_page(chosen)
        self.root.after(75, self.pump)
        self.update_busy = False
        self.root.after(4000, self.auto_update_check)

    @staticmethod
    def load_image(size):
        """Load a resized PNG of the official Nettalabbo icon without extra dependencies."""
        path = ASSETS_DIR / f'nettalabbo_{size}.png'
        try:
            return tk.PhotoImage(file=str(path))
        except (tk.TclError, OSError):
            return None

    def read_settings(self):
        harden_private_paths()
        try:
            source = next((p for p in [SETTINGS_FILE, *LEGACY_SETTINGS_FILES] if p.exists()), SETTINGS_FILE)
            s = json.loads(source.read_text())
            return s if isinstance(s, dict) else {}
        except (FileNotFoundError, ValueError, OSError): return {}

    def persist(self):
        """Atomically write local history with user-only filesystem permissions.

        Earlier releases used Path.write_text with the user's default umask,
        which could expose browsing history to other local accounts.
        """
        temporary = None
        try:
            APP_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
            APP_DIR.chmod(0o700)
            fd, temporary = tempfile.mkstemp(prefix='.settings-', suffix='.tmp', dir=str(APP_DIR))
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(self.settings, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, SETTINGS_FILE)
            temporary = None
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def current_page(self):
        return self.active_page

    def select_page(self, page):
        if page not in self.pages:
            return
        self.active_page = page
        self.pages[page].tkraise()
        self.workspace_title.configure(text=PAGE_LABELS.get(page, page))
        self.workspace_subtitle.configure(text=PAGE_DESCRIPTIONS.get(page, ''))
        for name, button in self.nav_buttons.items():
            active = name == page
            button.configure(bg='#ffffff' if active else '#d9e7ee',
                             fg='#075477' if active else '#24495f',
                             relief='sunken' if active else 'raised',
                             borderwidth=2, font=('Sans', 10, 'bold' if active else 'normal'))
        self.settings['last_tab'] = page
        self.persist()
        if page == 'Info':
            self.refresh_info()

    def on_tab(self, event=None):
        # Retained as a compatibility hook for earlier navigation integrations.
        self.select_page(self.current_page())

    def make_overview_page(self):
        f = self.pages['Overview']
        # A task-oriented independent dashboard, with all ten historical
        # networking capabilities visible rather than hidden in several groups.
        heading = ttk.Frame(f)
        heading.pack(fill='x', pady=(2, 12))
        ttk.Label(heading, text='Your network workspace', font=('Sans', 16, 'bold')).pack(anchor='w')
        ttk.Label(heading, text='All ten classic tools are one click away. Modern tools are below.',
                  font=('Sans', 10)).pack(anchor='w', pady=(4, 0))

        panel = ttk.LabelFrame(f, text='CLASSIC NETWORK UTILITIES  ·  10 tools', padding=(10, 12))
        panel.pack(fill='x', pady=(5, 16))
        # Display names are preserved here for discoverability, while the
        # underlying code uses new architecture and independently built UI.
        classic = (
            ('Finger', 'Finger'), ('WhoIs', 'WhoIs'), ('Time', 'Time'),
            ('Quote', 'Quote'), ('Ping', 'Ping'), ('Trace', 'Trace'),
            ('DNS', 'DNS'), ('Port Scan', 'Scanner'), ('Info', 'Info'),
            ('Options', 'Options'),
        )
        for col in range(5):
            panel.columnconfigure(col, weight=1, uniform='classic')
        for i, (title, page) in enumerate(classic):
            btn = ttk.Button(panel, text=title, command=lambda p=page: self.select_page(p))
            btn.grid(row=i // 5, column=i % 5, sticky='ew', padx=5, pady=6, ipady=9)

        ttk.Label(f, text='MODERN NETTALABBO FEATURES', font=('Sans', 11, 'bold')).pack(anchor='w', pady=(6, 8))
        modern = ttk.Frame(f)
        modern.pack(fill='both', expand=True)
        for col in range(5):
            modern.columnconfigure(col, weight=1, uniform='modern')
        features = (
            ('Domain Inspector', 'Find a registry automatically using RDAP or WHOIS.', 'Domain Inspector'),
            ('SSH', 'Work in an encrypted remote terminal.', 'SSH'),
            ('Telnet', 'Access legacy remote terminals with a security warning.', 'Telnet'),
            ('Legacy Navigator', 'Explore Gopher, Gemini, NNTP, FTP, DICT and more.', 'Legacy Navigator'),
            ('Mail Inspector', 'Check MX, SMTP acceptance and IMAP/POP3 connectivity.', 'Mail Inspector'),
        )
        for i, (title, desc, page) in enumerate(features):
            tile = tk.Frame(modern, bg='#f3fbfe', highlightbackground='#bdd9e6', highlightthickness=1)
            tile.grid(row=0, column=i, sticky='nsew', padx=5, pady=6)
            tk.Label(tile, text=title, font=('Sans', 12, 'bold'), fg='#165b80', bg='#f3fbfe',
                     anchor='w').pack(fill='x', padx=11, pady=(12, 4))
            tk.Label(tile, text=desc, font=('Sans', 9), fg='#435f70', bg='#f3fbfe',
                     wraplength=145, justify='left', anchor='w').pack(fill='x', padx=11)
            ttk.Button(tile, text='Open tool', command=lambda p=page: self.select_page(p)).pack(anchor='w', padx=11, pady=12)
        ttk.Label(f, text='Network tests must be limited to systems you are authorised to access.',
                  font=('Sans', 9)).pack(anchor='w', pady=(12, 3))

    def pump(self):
        try:
            while True:
                fn, args = self.events.get_nowait()
                try: fn(*args)
                except tk.TclError: pass
        except queue.Empty: pass
        self.root.after(75, self.pump)

    def post(self, fn, *args): self.events.put((fn, args))

    def set_status(self, page, msg):
        if page in self.status: self.status[page].set(msg)
        self.footer_status.set(f'{page}: {msg}')

    def start(self, page, worker):
        if page in self.tasks:
            messagebox.showinfo('Nettalabbo', f'{page} is already running. Cancel it first.')
            return
        stop = threading.Event()
        self.failed_tasks.discard(page)
        self.task_outcomes.pop(page, None)
        self.tasks[page] = (stop, None)
        self.activity_started[page] = time.monotonic()
        self.update_activity()
        self.set_status(page, 'Working...')
        def run():
            try: worker(stop)
            except Exception as e:
                if not stop.is_set():
                    self.failed_tasks.add(page)
                    self.post(self.append, page, f'Error: {e}\n')
            finally: self.post(self.finish, page, stop)
        threading.Thread(target=run, daemon=True, name=f'Nettalabbo-{page}').start()

    def finish(self, page, stop):
        # A stopped background request must never complete a newer operation.
        if page not in self.tasks or self.tasks[page][0] is not stop:
            return
        del self.tasks[page]
        self.activity_started.pop(page, None)
        self.update_activity()
        failed = page in self.failed_tasks
        self.failed_tasks.discard(page)
        outcome = self.task_outcomes.pop(page, None)
        self.set_status(page, 'Cancelled.' if stop.is_set() else ('Lookup failed.' if failed else (outcome or 'Completed.')))

    def update_activity(self):
        """A non-blocking indicator for slow DNS, registry and network operations."""
        if not self.tasks:
            self.activity_bar.stop()
            self.activity_strip.pack_forget()
            return
        names = ', '.join(self.tasks)
        self.activity_caption.set('Working: {}   •   Cancel is available'.format(names))
        if not self.activity_strip.winfo_manager():
            self.activity_strip.pack(fill='x', before=self.page_host.winfo_children()[-1])
            self.activity_bar.start(85)

    def cancel(self, page):
        task = self.tasks.get(page)
        if task:
            task[0].set()
            proc = task[1]
            if proc and proc.poll() is None: proc.terminate()
            self.set_status(page, 'Cancelling...')

    def clear(self, page):
        if page in self.trees:
            for item in self.trees[page].get_children(): self.trees[page].delete(item)
        if page in self.output:
            self.output[page].configure(state='normal')
            self.output[page].delete('1.0', 'end')
            self.output[page].configure(state='disabled')

    def append(self, page, value):
        if page not in self.output: return
        w = self.output[page]
        w.configure(state='normal'); w.insert('end', value); w.see('end'); w.configure(state='disabled')

    def add_row(self, page, values):
        tree=self.trees.get(page)
        if tree: tree.insert('', 'end', values=values)

    def add_sorted_row(self, page, values):
        """Insert keeping rows ordered by their numeric first column."""
        tree=self.trees.get(page)
        if not tree: return
        position='end'
        for index,item in enumerate(tree.get_children()):
            try:
                if int(tree.item(item)['values'][0])>int(values[0]):
                    position=index;break
            except (ValueError,TypeError,IndexError):
                continue
        tree.insert('', position, values=values)

    def output_string(self, page):
        if page == 'Domain Inspector':
            rows = [self.domain_tree.item(x)['values'] for x in self.domain_tree.get_children()]
            return '\n'.join(f'{row[0]}: {row[1]}' for row in rows) + '\n\n' + self.output['Domain Inspector'].get('1.0','end-1c')
        if page in self.trees:
            tree=self.trees[page]
            lines=['\t'.join(tree['columns'])]
            lines.extend('\t'.join(str(v) for v in tree.item(i)['values']) for i in tree.get_children())
            return '\n'.join(lines)+'\n'
        if page in self.output: return self.output[page].get('1.0','end-1c')
        return ''

    def copy_output(self, page):
        s=self.output_string(page)
        self.root.clipboard_clear(); self.root.clipboard_append(s)
        self.set_status(page, 'Copied to clipboard.')

    def save_output(self, page):
        content = self.output_string(page)
        if not content: return
        path = filedialog.asksaveasfilename(defaultextension='.txt',
                initialfile=f'nettalabbo_{page.lower()}.txt', filetypes=[('Text files','*.txt'),('All files','*')])
        if path:
            Path(path).write_text(content, encoding='utf-8')
            self.set_status(page, f'Saved: {path}')

    def print_output(self, page):
        """Send the page output to the default CUPS printer with lp."""
        content = self.output_string(page)
        empty_table = page in self.trees and not self.trees[page].get_children()
        if empty_table or not content or not content.strip():
            messagebox.showinfo('Print output', 'There is nothing to print on this page yet.', parent=self.root)
            return
        if not shutil.which('lp'):
            messagebox.showerror('Print output', 'The lp command was not found. Install the cups-client '
                                 'package, or use Save Output instead.', parent=self.root)
            return
        printer = default_printer()
        if not printer:
            messagebox.showerror('Print output', 'No default printer is configured. Set one in the '
                                 'system Printers settings, or use Save Output instead.', parent=self.root)
            return
        lines = content.count('\n') + 1
        if not messagebox.askyesno('Print output', f'Print {lines} lines from {page} on {printer}?', parent=self.root):
            return
        self.set_status(page, f'Sending to {printer}...')
        title = f'Nettalabbo {page}'
        def worker():
            try:
                result = subprocess.run(['lp', '-t', title], input=content, text=True,
                                        capture_output=True, timeout=30, check=False)
                message = (result.stdout.strip() or f'Sent to {printer}') if result.returncode == 0 \
                    else 'Printing failed: ' + (result.stderr.strip() or f'lp exit code {result.returncode}')
            except (OSError, subprocess.TimeoutExpired) as exc:
                message = f'Printing failed: {exc}'
            self.post(self.set_status, page, message)
        threading.Thread(target=worker, daemon=True, name='Nettalabbo-print').start()

    def suggestions_for(self, key):
        """Documented servers appended after the user's own history."""
        historic = bool(getattr(self, 'time_historic', None) and self.time_historic.get())
        if key == 'Time_dayhost':
            return time_services.suggested_servers('Daytime', historic)
        if key == 'Time_server':
            protocol = self.time_proto.get() if getattr(self, 'time_proto', None) else 'SNTP'
            return time_services.suggested_servers(protocol, historic)
        if key == 'DNS_server':
            return dns_lookup.SUGGESTED_SERVERS
        return service_catalog.suggestions(key)

    def combo_values(self, key):
        values = list(self.settings.get('history', {}).get(key, []))
        values += [host for host in self.suggestions_for(key) if host not in values]
        return values

    def input_combobox(self, parent, page, key, width=36):
        v=tk.StringVar()
        combo=ttk.Combobox(parent, textvariable=v, values=self.combo_values(key), width=width)
        self.inputs[key]=v; self.history_boxes[key]=combo
        return combo

    def remember(self, key):
        value = self.inputs[key].get().strip()
        if not value: return ''
        hist=self.settings.setdefault('history', {}).setdefault(key, [])
        if value in hist: hist.remove(value)
        hist.insert(0,value)
        del hist[30:]
        self.history_boxes[key]['values']=self.combo_values(key)
        self.persist()
        return value

    def delete_history(self, key):
        v=self.inputs[key].get().strip()
        h=self.settings.setdefault('history', {}).setdefault(key, [])
        if v in h: h.remove(v)
        self.inputs[key].set('')
        self.history_boxes[key]['values']=self.combo_values(key)
        self.persist()

    def button_bar(self, parent, page, command, main_label):
        bar=ttk.Frame(parent); bar.pack(fill='x', pady=5)
        ttk.Button(bar,text=main_label,command=command,width=11).pack(side='left',padx=(0,5))
        ttk.Button(bar,text='Cancel',command=lambda:self.cancel(page),width=10).pack(side='left',padx=(0,5))
        ttk.Button(bar,text='Copy',command=lambda:self.copy_output(page),width=9).pack(side='left',padx=(0,5))
        ttk.Button(bar,text='Save Output',command=lambda:self.save_output(page),width=13).pack(side='left',padx=(0,5))
        ttk.Button(bar,text='Print',command=lambda:self.print_output(page),width=9).pack(side='left')
        return bar

    def text_output(self, parent, page):
        container=ttk.Frame(parent);container.pack(fill='both',expand=True,pady=(4,3))
        scrollbar=ttk.Scrollbar(container,orient='vertical')
        text=tk.Text(container,wrap='word',font=('Courier',10),relief='sunken',bd=2,
                 yscrollcommand=scrollbar.set,height=16,state='disabled',background='white')
        text.pack(side='left',fill='both',expand=True)
        scrollbar.configure(command=text.yview);scrollbar.pack(side='right',fill='y')
        self.output[page]=text
        text.bind('<Control-c>', lambda e, w=text: self.copy_selection_text(w))
        text.bind('<Control-C>', lambda e, w=text: self.copy_selection_text(w))
        text.bind('<Control-a>', lambda e, w=text: self.select_all_text(w))
        text.bind('<Button-3>', lambda e, w=text: self.text_context_menu(e, w))
        return text

    def tree_output(self, parent, page, cols):
        container=ttk.Frame(parent);container.pack(fill='both',expand=True,pady=(5,3))
        tree=ttk.Treeview(container,columns=cols,show='headings',selectmode='browse')
        for i,col in enumerate(cols):
            tree.heading(col,text=col)
            tree.column(col,anchor='w',width=86 if i==0 else (165 if i==2 else 120),stretch=True)
        y=ttk.Scrollbar(container,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=y.set)
        tree.pack(side='left',fill='both',expand=True);y.pack(side='right',fill='y')
        self.trees[page]=tree
        tree.bind('<Button-3>',lambda e, pg=page:self.context_menu(e,pg))
        tree.bind('<Control-c>', lambda e, pg=page: self.copy_selected_tree_row(pg))
        return tree

    def copy_selection_text(self, widget):
        try:
            value = widget.get('sel.first', 'sel.last')
        except tk.TclError:
            return 'break'
        if value:
            self.copy_value(value)
        return 'break'

    def select_all_text(self, widget):
        widget.tag_add('sel', '1.0', 'end-1c')
        widget.focus_set()
        return 'break'

    def text_context_menu(self, event, widget):
        # Snapshot the selection before displaying the menu.
        try:
            selection = widget.get('sel.first', 'sel.last')
        except tk.TclError:
            selection = ''
        menu = tk.Menu(widget, tearoff=False)
        menu.add_command(label='Copy selection', state='normal' if selection else 'disabled',
                         command=lambda: self.copy_value(selection))
        menu.add_command(label='Copy all', command=lambda: self.copy_value(widget.get('1.0','end-1c')))
        menu.tk_popup(event.x_root, event.y_root)
        menu.grab_release()
        return 'break'

    def copy_selected_tree_row(self, page):
        tree = self.trees[page]
        chosen = tree.selection()
        if chosen:
            values = tree.item(chosen[0], 'values')
            self.copy_value('\t'.join(map(str, values)))
        return 'break'

    def context_menu(self,event,page):
        tree=self.trees[page]
        iid=tree.identify_row(event.y)
        if not iid:return
        tree.selection_set(iid)
        values=tree.item(iid)['values']
        ip = str(values[1]) if len(values)>1 else ''
        host = str(values[2]) if len(values)>2 else ip
        menu=tk.Menu(self.root,tearoff=False)
        to_ip=tk.Menu(menu,tearoff=False)
        to_host=tk.Menu(menu,tearoff=False)
        for dest,key in [('Finger','Finger_host'),('WhoIs','WhoIs_query'),('Ping','Ping_host'),('Trace','Trace_host'),('DNS','DNS_host'),('SSH','SSH_host'),('Telnet','Telnet_host')]:
            to_ip.add_command(label=dest,command=lambda d=dest,k=key:self.transfer(d,k,ip))
            to_host.add_command(label=dest,command=lambda d=dest,k=key:self.transfer(d,k,host))
        menu.add_cascade(label='Send IP address to',menu=to_ip)
        try:
            domain_name = normalise_domain(host)
            to_host.add_command(label='Domain Inspector',
                command=lambda h=domain_name:self.transfer('Domain Inspector','Domain_Inspector_host',h))
        except LookupError: pass
        menu.add_cascade(label='Send host name to',menu=to_host)
        menu.add_separator()
        menu.add_command(label='Copy selected row', command=lambda: self.copy_selected_tree_row(page))
        menu.add_command(label='Copy IP address',command=lambda:self.copy_value(ip))
        menu.add_command(label='Copy host name',command=lambda:self.copy_value(host))
        menu.tk_popup(event.x_root,event.y_root)
        menu.grab_release()

    def copy_value(self,value):
        self.root.clipboard_clear();self.root.clipboard_append(value)

    def transfer(self, page,key,value):
        self.inputs[key].set(value)
        self.select_page(page)
        self.set_status(page,f'Address transferred: {value}')

    def make_domain_page(self):
        """New workflow, not a copy of the historical NetLab interface."""
        page = 'Domain Inspector'
        f = self.pages[page]
        ttk.Label(f, text='Domain Inspector', font=('Sans', 16, 'bold')).pack(anchor='w', pady=(2, 3))
        ttk.Label(f, text='Discover any public IANA TLD. Query RDAP or WHOIS automatically; add private registries.').pack(anchor='w', pady=(0, 10))
        top = ttk.Frame(f)
        top.pack(fill='x', pady=(0, 8))
        ttk.Label(top, text='Domain or website:').pack(side='left', padx=(0, 8))
        entry = self.input_combobox(top, page, 'Domain_Inspector_host', 24)
        entry.pack(side='left', fill='x', expand=True)
        entry.set('example.org')
        entry.bind('<Return>', lambda event: self.execute_domain())
        ttk.Button(top, text='Look up', command=self.execute_domain, width=13).pack(side='left', padx=(9, 0))
        ttk.Button(top, text='Cancel', command=lambda: self.cancel(page), width=9).pack(side='left', padx=(5, 0))

        explainer = ttk.Frame(f)
        explainer.pack(fill='x', pady=(0, 6))
        for title, desc in [('1  Registry', 'Identify TLD with IANA'),
                            ('2  Registrar', 'Registration provider'),
                            ('3  Registrant', 'Public holder, if disclosed')]:
            tile = ttk.LabelFrame(explainer, text=title)
            tile.pack(side='left', fill='x', expand=True, padx=(0, 6))
            ttk.Label(tile, text=desc).pack(anchor='w', padx=8, pady=7)

        ttk.Label(f, text='Registration details', font=('Sans', 10, 'bold')).pack(anchor='w', pady=(5, 2))
        holder = ttk.Frame(f)
        holder.pack(fill='both', expand=True)
        tree = ttk.Treeview(holder, columns=('Field', 'Public value'), show='headings', height=8)
        tree.heading('Field', text='Field')
        tree.heading('Public value', text='Public value')
        tree.column('Field', width=210, minwidth=160, stretch=False)
        tree.column('Public value', width=580, minwidth=250, stretch=True)
        tree.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(holder, command=tree.yview)
        sb.pack(side='right', fill='y')
        tree.configure(yscrollcommand=sb.set)
        self.trees[page] = tree
        self.domain_tree = tree

        actions = ttk.Frame(f)
        actions.pack(fill='x', pady=(8, 2))
        ttk.Button(actions, text='Copy report', command=lambda: self.copy_output(page)).pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Save report', command=lambda: self.save_output(page)).pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Raw WHOIS (manual)', command=self.open_raw_whois).pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Custom registries...', command=self.custom_registries_dialog).pack(side='left', padx=(0, 6))
        self.status[page] = tk.StringVar(value='Ready. Lookup begins only when you click Look up.')
        ttk.Label(f, textvariable=self.status[page]).pack(anchor='w', pady=(2, 0))
        self.text_output(f, page).configure(height=3)
        self.append(page, 'IANA root registry discovers public TLDs including country codes and brand TLDs.\n'
                          'RDAP is preferred; WHOIS is automatic when RDAP is unavailable.\n'
                          'Private namespaces require an explicitly configured registry.\n')

    def execute_domain(self):
        page = 'Domain Inspector'
        query = self.remember('Domain_Inspector_host')
        if not query:
            return
        try:
            normalise_domain(query)
        except LookupError as e:
            messagebox.showerror('Invalid domain', str(e))
            return
        self.clear(page)
        def worker(stop):
            if stop.is_set(): return
            try:
                rows, report, _ = lookup_domain(query, APP_DIR / 'rdap_bootstrap.json',
                                                self.settings.get('custom_registries', []))
                if not stop.is_set():
                    self.post(self.domain_render, rows, report)
            except Exception as e:
                if not stop.is_set():
                    self.failed_tasks.add(page)
                    self.post(self.append, page, f'Domain lookup failed: {e}\n\n'
                              'Check the service error, or configure a private registry in Custom registries.\n')
        self.start(page, worker)

    def custom_registries_dialog(self):
        """Manage explicit RDAP / WHOIS routes for private, non-IANA suffixes."""
        dialog = tk.Toplevel(self.root)
        dialog.title('Custom registry servers')
        dialog.transient(self.root)
        dialog.geometry('610x360')
        dialog.minsize(520, 300)
        frame = ttk.Frame(dialog, padding=12)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Private or alternative-root namespaces', font=('Sans', 12, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Public TLDs, including brand TLDs, are detected from IANA automatically.').pack(anchor='w', pady=(1, 8))
        items = list(self.settings.get('custom_registries', []))
        box = tk.Listbox(frame, height=7)
        box.pack(fill='both', expand=True)
        def redraw():
            box.delete(0, 'end')
            for x in items:
                box.insert('end', f".{x['suffix']}  |  {x['protocol'].upper()}  |  {x['endpoint']}")
        redraw()
        fields = ttk.Frame(frame)
        fields.pack(fill='x', pady=(10, 3))
        suffix = ttk.Entry(fields, width=14)
        suffix.pack(side='left', padx=(0, 7))
        suffix.insert(0, 'corp')
        protocol = ttk.Combobox(fields, values=('RDAP', 'WHOIS'), state='readonly', width=8)
        protocol.set('RDAP')
        protocol.pack(side='left', padx=(0, 7))
        endpoint = ttk.Entry(fields, width=36)
        endpoint.pack(side='left', fill='x', expand=True)
        ttk.Label(frame, text='Suffix | Protocol | HTTPS RDAP base URL or WHOIS hostname').pack(anchor='w')
        def add():
            name = suffix.get().lower().strip().lstrip('.')
            target = endpoint.get().strip()
            method = protocol.get().lower()
            if not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', name):
                messagebox.showerror('Invalid suffix', 'Enter a single DNS suffix, such as corp.', parent=dialog)
                return
            if method == 'rdap' and not target.startswith('https://'):
                messagebox.showerror('Invalid RDAP URL', 'Custom RDAP services must use HTTPS.', parent=dialog)
                return
            if method == 'whois' and not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', target):
                messagebox.showerror('Invalid WHOIS host', 'Enter a WHOIS hostname, without a port.', parent=dialog)
                return
            items[:] = [x for x in items if x.get('suffix') != name]
            items.append({'suffix': name, 'protocol': method, 'endpoint': target})
            self.settings['custom_registries'] = items
            self.persist()
            redraw()
        def remove():
            indexes = list(box.curselection())
            for idx in reversed(indexes):
                items.pop(idx)
            self.settings['custom_registries'] = items
            self.persist()
            redraw()
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=(8, 0))
        ttk.Button(buttons, text='Add / Replace', command=add).pack(side='left')
        ttk.Button(buttons, text='Remove selected', command=remove).pack(side='left', padx=(8, 0))
        ttk.Button(buttons, text='Close', command=dialog.destroy).pack(side='right')

    def open_raw_whois(self):
        value = self.inputs['Domain_Inspector_host'].get().strip()
        if value:
            try: self.inputs['WhoIs_query'].set(normalise_domain(value))
            except LookupError: pass
        self.select_page('WhoIs')

    def domain_render(self, rows, report):
        for key, val in rows:
            self.domain_tree.insert('', 'end', values=(key, str(val)))
        self.append('Domain Inspector', report)

    def make_network_page(self, page):
        frame=self.pages[page]
        row=ttk.Frame(frame);row.pack(fill='x',pady=(0,2))
        if page=='WhoIs':
            ttk.Label(row,text='Query string:').pack(side='left',padx=(0,5))
            query_entry = self.input_combobox(row,page,'WhoIs_query',41)
            query_entry.pack(side='left',fill='x',expand=True)
            query_entry.bind('<Return>', lambda e: self.execute_network('WhoIs'))
            second=ttk.Frame(frame);second.pack(fill='x',pady=(1,2))
            ttk.Label(second,text='WhoIs server:').pack(side='left',padx=(0,5))
            whois_server = self.input_combobox(second,page,'WhoIs_server',28)
            whois_server.pack(side='left',fill='x',expand=True)
            whois_server.bind('<Return>', lambda e: self.execute_network('WhoIs'))
            if not self.inputs['WhoIs_server'].get():self.inputs['WhoIs_server'].set('whois.iana.org')
            ttk.Button(second,text='Delete Server',command=lambda:self.delete_history('WhoIs_server')).pack(side='left',padx=7)
        else:
            ttk.Label(row,text='Enter user@host or host:' if page=='Finger' else 'Remote host:').pack(side='left',padx=(0,7))
            entry = self.input_combobox(row,page,f'{page}_host',37)
            entry.pack(side='left',fill='x',expand=True)
            entry.bind('<Return>', lambda e, p=page: self.execute_network(p))
            if page=='Quote' and not self.inputs['Quote_host'].get():self.inputs['Quote_host'].set('djxmmx.net')
            if page in ('DNS','Trace'):
                ttk.Label(row, text='Enter ↵ to {}'.format('resolve DNS' if page == 'DNS' else 'start Trace'),
                          foreground='#547086').pack(side='left', padx=(7,0))
            ttk.Button(row,text='Delete Host',command=lambda p=page:self.delete_history(f'{p}_host')).pack(side='left',padx=(8,0))
        if page=='DNS':
            opt=ttk.Frame(frame);opt.pack(fill='x',pady=(3,0))
            ttk.Label(opt,text='Record type:').pack(side='left',padx=(0,5))
            self.dns_type=tk.StringVar(value=dns_lookup.SYSTEM_ADDRESSES)
            ttk.Combobox(opt,textvariable=self.dns_type,values=dns_lookup.RECORD_TYPES,
                         state='readonly',width=20).pack(side='left')
            ttk.Label(opt,text='DNS server:').pack(side='left',padx=(14,5))
            server=self.input_combobox(opt,page,'DNS_server',18)
            server.pack(side='left')
            server.bind('<Return>', lambda e: self.execute_network('DNS'))
            ttk.Label(opt,text='empty = system resolver',foreground='#547086').pack(side='left',padx=(7,0))
        if page=='Finger':
            opt=ttk.Frame(frame);opt.pack(fill='x')
            self.full_finger=tk.BooleanVar(value=False)
            ttk.Checkbutton(opt,text='Full user info',variable=self.full_finger).pack(side='left')
            ttk.Button(opt,text='Addr Book',command=self.address_book).pack(side='left',padx=12)
        if page in ('Ping','Trace'):
            self.make_probe_options(frame,page)
        self.button_bar(frame,page,lambda p=page:self.execute_network(p),'Ping' if page=='Ping' else page)
        st=tk.StringVar(value='Status: Ready')
        self.status[page]=st
        ttk.Label(frame,textvariable=st).pack(anchor='w',pady=(2,0))
        if page in ('Ping','Trace'):
            self.tree_output(frame,page,('No.', 'IP address', 'Host name', 'Response time'))
        else: self.text_output(frame,page)

    def make_probe_options(self, frame, page):
        group=ttk.LabelFrame(frame,text='Ping settings' if page=='Ping' else 'Traceroute settings')
        group.pack(fill='x',pady=(5,3))
        configs = [('Number of pings',4,1,1000),('Base packet size',56,0,1400),('Timeout (s)',2,1,60),('Delay (ms)',1000,200,20000)] if page=='Ping' else [
            ('Maximum hops',30,1,64),('Delay (ms)',0,0,20000),('Data size',56,0,1400),('Timeout (s)',2,1,60),('Start from hop',1,1,64)]
        variables={}
        for i,(name,default,low,high) in enumerate(configs):
            cell=ttk.Frame(group);cell.grid(row=0 if i<4 else 1,column=i if i<4 else 0,sticky='w',padx=7,pady=5)
            ttk.Label(cell,text=name+':').pack(side='left',padx=(0,3))
            v=tk.IntVar(value=default)
            ttk.Spinbox(cell,from_=low,to=high,width=5,textvariable=v).pack(side='left')
            variables[name]=v
        self.probe_vars=getattr(self,'probe_vars',{})
        self.probe_vars[page]=variables
        opts=ttk.Frame(group);opts.grid(row=1,column=1,columnspan=3,sticky='w',padx=7,pady=(0,5))
        vars2={}
        for label in ('Resolve IP address',"Don't fragment") if page=='Ping' else ('Resolve IP address','Parallel Trace'):
            var=tk.BooleanVar(value=(label=='Resolve IP address' or label=='Parallel Trace'))
            ttk.Checkbutton(opts,text=label,variable=var).pack(side='left',padx=(2,12))
            vars2[label]=var
        self.probe_vars[page].update(vars2)
        if page == 'Trace':
            method = tk.StringVar(value='Auto')
            ttk.Label(opts, text='Probe method:').pack(side='left', padx=(0, 4))
            ttk.Combobox(opts, textvariable=method, state='readonly', width=8,
                         values=('Auto', 'ICMP', 'TCP', 'UDP')).pack(side='left')
            self.probe_vars[page]['Probe method'] = method

    def execute_network(self, page):
        if page=='WhoIs':
            query=self.remember('WhoIs_query'); server=self.remember('WhoIs_server')
            if not query or not server: return
            args=(query,server)
        else:
            host=self.remember(f'{page}_host')
            if not host:return
            args=(host,)
            if page=='DNS':
                server=self.inputs['DNS_server'].get().strip()
                if server:self.remember('DNS_server')
                args=(host,self.dns_type.get(),server)
        self.clear(page)
        if page in ('Ping','Trace'):
            cmd,resolve=self.build_probe_command(page,args[0])
            self.start(page,lambda stop:self.run_probe(page,args[0],cmd,resolve,stop))
        else:
            verbose=self.full_finger.get() if page=='Finger' else False
            self.start(page,lambda stop:self.run_text_query(page,args,stop,verbose))

    def local_ip(self):
        # Legacy compatibility hook: local host is its own system page,
        # never an action on the remote domain entered in DNS.
        self.select_page('Info')
        self.refresh_info()

    def run_text_query(self,page,args,stop,verbose=False):
        if page=='DNS' and len(args)>1 and args[1]!=dns_lookup.SYSTEM_ADDRESSES:
            host,record,server=args
            types=dns_lookup.COMMON_TYPES if record==dns_lookup.ALL_COMMON else [record]
            for rtype in types:
                if stop.is_set():break
                self.post(self.set_status,page,f'Querying {rtype} records for {host}...')
                try:
                    result=dns_lookup.query(host,rtype,server)
                    if result['status'] not in ('NOERROR',):self.failed_tasks.add(page)
                    self.post(self.append,page,dns_lookup.format_result(result)+'\n')
                    if result['status']=='NXDOMAIN':break
                except dns_lookup.DnsLookupError as e:
                    self.failed_tasks.add(page)
                    self.post(self.append,page,f'{e}\n')
                    break
            return
        if page=='DNS':
            host=args[0]
            try:
                records=socket.getaddrinfo(host,None,proto=socket.IPPROTO_TCP)
                ips=sorted({r[4][0] for r in records})
                output=f'Host: {host}\nAddresses:\n'+''.join(f'    {ip}\n' for ip in ips)
                for ip in ips:
                    try:output+=f'PTR {ip}: {socket.gethostbyaddr(ip)[0]}\n'
                    except OSError: pass
                try:
                    canon,aliases,addrs=socket.gethostbyname_ex(host)
                    output+=f'Canonical: {canon}\nAliases: {", ".join(aliases) or "none"}\n'
                except OSError: pass
            except OSError as e:
                self.failed_tasks.add(page)
                output=f'DNS lookup failed: {e}\n'
            self.post(self.append,page,output)
            return
        if page=='WhoIs': query,host=args;port=43;payload=query+'\r\n'
        elif page=='Finger':
            address=args[0]
            if '@' in address: user,host=address.rsplit('@',1)
            else:user,host='',address
            port=79;payload=('/W ' if verbose else '')+user+'\r\n'
        elif page=='Quote':host=args[0];port=17;payload=''
        else:return
        try:
            text=self.tcp_text(host,port,payload,stop)
            self.post(self.append,page,text or '[No data returned]\n')
            if page=='WhoIs' and host.lower()=='whois.iana.org':
                referral=service_catalog.whois_referral(text)
                if referral and referral!=host.lower() and not stop.is_set():
                    self.post(self.append,page,f'\n--- IANA refers to {referral}; querying it ---\n\n')
                    try:
                        self.post(self.append,page,self.tcp_text(referral,43,payload,stop) or '[No data returned]\n')
                    except OSError as e:
                        self.post(self.append,page,f'Referral to {referral} failed: {e}\n')
        except OSError as e:
            self.post(self.append,page,f'Connection failed: {e}\n')

    @staticmethod
    def tcp_text(host,port,payload,stop):
        """Send an optional request line and read the reply until close (max 1 MiB)."""
        with socket.create_connection((host,port),timeout=7) as sock:
            sock.settimeout(5)
            if payload:sock.sendall(payload.encode('utf-8','replace'))
            chunks=[]
            while not stop.is_set():
                try:chunk=sock.recv(4096)
                except socket.timeout: break
                if not chunk: break
                chunks.append(chunk)
                if sum(map(len,chunks))>1024*1024:
                    chunks.append(b'\n[Output limited to 1 MiB]');break
        return b''.join(chunks).decode('utf-8','replace')

    @staticmethod
    def traceroute_supports(flag):
        """Read the current traceroute variant's help rather than assuming -N or -z."""
        exe = shutil.which('traceroute')
        if not exe:
            return False
        try:
            helpresult = subprocess.run([exe, '--help'], capture_output=True, text=True,
                                        timeout=2, check=False)
            helptext = helpresult.stdout + helpresult.stderr
            return re.search(r'(?<![\w-]){}(?![\w-])'.format(re.escape(flag)), helptext) is not None
        except (OSError, subprocess.TimeoutExpired):
            return False

    def build_probe_command(self,page,host):
        v=self.probe_vars[page]
        resolve=bool(v['Resolve IP address'].get())
        if page=='Ping':
            delay=int(v['Delay (ms)'].get())
            cmd=['ping','-c',str(max(1,min(1000,v['Number of pings'].get()))),
                 '-s',str(max(0,min(1400,v['Base packet size'].get()))),
                 '-W',str(max(1,min(60,v['Timeout (s)'].get()))),
                 '-i',str(max(200,delay)/1000)]
            if not resolve:cmd.insert(1,'-n')
            if v["Don't fragment"].get():cmd.extend(['-M','do'])
        else:
            hops=max(1,min(64,int(v['Maximum hops'].get())))
            cmd=['traceroute','-q','1','-m',str(hops),'-f',str(max(1,min(hops,int(v['Start from hop'].get())))),
                 '-w',str(max(1,min(60,int(v['Timeout (s)'].get()))))]
            if not resolve: cmd+=['-n']
            # Use ICMP by default. Linux's traditional UDP high ports are often
            # discarded by routers/firewalls, producing only timeout asterisks.
            method = v.get('Probe method')
            method = method.get() if method is not None else 'Auto'
            if method not in ('Auto', 'ICMP', 'TCP', 'UDP'):
                method = 'Auto'
            if method in ('Auto', 'ICMP') and self.traceroute_supports('-I'):
                cmd.append('-I')
            elif method == 'TCP' and self.traceroute_supports('-T'):
                cmd.append('-T')
            # Unsupported variants fall back to standard UDP traceroute.
            if v['Parallel Trace'].get() and self.traceroute_supports('-N'):
                cmd += ['-N', str(min(16, hops))]
            delay = max(0, min(20000,int(v['Delay (ms)'].get())))
            if delay and self.traceroute_supports('-z'):
                cmd += ['-z', str(delay / 1000)]
        cmd.append(host)
        if page=='Trace':cmd.append(str(max(28,min(1400,v['Data size'].get()))))
        return cmd,resolve

    @staticmethod
    def parse_trace_hop(line):
        """Parse standard Linux traceroute IPv4/IPv6 lines, including timeouts."""
        m = re.match(r'^\s*(\d+)\s+(.+)$', line)
        if not m:
            return None
        hop, tail = m.groups()
        if not (tail.startswith('*') or re.search(r'\bms\b',tail) or '(' in tail):
            return None
        time_match = re.search(r'(< ?[\d.]+|[\d.]+)\s*ms\b', tail)
        # A resolved host often appears as: router.example (192.0.2.1).
        parenthesized = re.search(r'\(([^()\s]+)\)', tail)
        candidates = [parenthesized.group(1)] if parenthesized else []
        candidates += tail.split()
        address = '*'
        for candidate in candidates:
            try:
                address = str(ipaddress.ip_address(candidate.strip('(),')))
                break
            except ValueError:
                pass
        name = tail.split('(')[0].strip() if parenthesized else address
        if address == '*':
            name = '*'
        return (hop, address, name, time_match.group(0) if time_match else '*')

    def run_probe(self,page,host,cmd,resolve,stop):
        if not shutil.which(cmd[0]):
            self.failed_tasks.add(page)
            self.post(self.add_row,page,('!', '', '', 'Install iputils-ping or traceroute'))
            return
        # Auto retries only when NO intermediate router responded. A partial
        # trace is kept as evidence and is never falsely labelled successful.
        mode = None
        if page == 'Trace':
            option = self.probe_vars.get('Trace', {}).get('Probe method')
            mode = option.get() if option is not None else 'Auto'
        attempts = [(cmd, 'ICMP' if '-I' in cmd else 'TCP' if '-T' in cmd else 'UDP')]
        if page == 'Trace' and mode == 'Auto':
            for flag, label in (('-T','TCP'), (None,'UDP')):
                if label == attempts[0][1] or (flag and not self.traceroute_supports(flag)):
                    continue
                alternative = [arg for arg in cmd if arg != '-I' and arg != '-T']
                # Insert before the host and packet size (last two arguments).
                if flag:
                    alternative.insert(-2,flag)
                attempts.append((alternative,label))
        total_responses = 0
        reached_destination = False
        destination_ip = None
        had_error = False
        for attempt, label in attempts:
            if stop.is_set():
                break
            self.post(self.set_status,page, f'Running {page}: {label} ...')
            responses = 0
            try:
                with subprocess.Popen(attempt,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                     bufsize=1,encoding='utf-8',errors='replace') as proc:
                    # Cancellation can occur before process registration.
                    if stop.is_set():
                        proc.terminate()
                    self.tasks[page] = (stop,proc)
                    for line in proc.stdout:
                        if stop.is_set():
                            break
                        output = line.strip()
                        if page == 'Trace' and output.startswith('traceroute to '):
                            destination_match = re.search(r'\(([^()]+)\)', output)
                            if destination_match:
                                try:
                                    destination_ip = str(ipaddress.ip_address(destination_match.group(1)))
                                except ValueError:
                                    pass
                        if page == 'Ping':
                            m=re.search(r'icmp_seq=(\d+).*?time[=<]([\d.]+)\s*ms',output)
                            if m:
                                responses += 1
                                ipm=re.search(r'from\s+(?:(.+?)\s+)?\(?([0-9a-fA-F:.]+)\)?\s*:',output)
                                addr=ipm.group(2) if ipm else host
                                name=ipm.group(1) if ipm and ipm.group(1) else host
                                self.post(self.add_row,page,(m.group(1),addr,name if resolve else '',f'{m.group(2)} ms'))
                            elif output and not output.startswith(('PING ', '--- ', 'rtt ', 'round-trip ', 'packets transmitted')) and 'packets transmitted' not in output:
                                self.post(self.add_row,page,('!',host,'',output[:130]))
                        else:
                            row = self.parse_trace_hop(output)
                            if row is not None:
                                if row[1] != '*':
                                    responses += 1
                                    if row[1] == destination_ip or row[1] == host:
                                        reached_destination = True
                                self.post(self.add_row,page,(row[0],row[1],row[2] if resolve else '',row[3]))
                            elif output and not output.startswith('traceroute to'):
                                self.post(self.add_row,page,('!', '', '', output[:130]))
                    if stop.is_set() and proc.poll() is None:
                        proc.terminate()
                    try:
                        proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                        had_error=True
                    if proc.returncode and not stop.is_set():
                        had_error=True
                        self.post(self.add_row,page,('!',host,'',f'{label}: command exited with code {proc.returncode}'))
            except (OSError, subprocess.TimeoutExpired) as e:
                had_error=True
                self.post(self.add_row,page,('!',host,'',f'{label}: {e}'))
            total_responses += responses
            if page == 'Ping' or responses or mode != 'Auto':
                break
            if not stop.is_set() and (attempt,label) != attempts[-1]:
                self.post(self.add_row,page,('!', '', '', f'No responses using {label}. Trying another probe method.'))
        if not stop.is_set() and total_responses == 0:
            self.failed_tasks.add(page)
            self.post(self.add_row,page,('!',host,'',
                      'No reply received. A firewall may block probes; try another method or destination.'))
        elif not stop.is_set() and had_error:
            self.failed_tasks.add(page)
        elif not stop.is_set() and page == 'Trace' and not reached_destination:
            self.task_outcomes = getattr(self, 'task_outcomes', {})
            self.task_outcomes[page] = 'Partial trace: destination not confirmed.'

    def address_book(self):
        w=tk.Toplevel(self.root);w.title('Address Book');w.geometry('480x350');w.transient(self.root)
        form=ttk.Frame(w,padding=10);form.pack(fill='both',expand=True)
        v=tk.StringVar()
        ttk.Label(form,text='New address:').pack(anchor='w')
        ttk.Entry(form,textvariable=v).pack(fill='x',pady=(3,8))
        vals=self.settings.setdefault('address_book',[])
        lb=tk.Listbox(form);lb.pack(fill='both',expand=True)
        for name in vals:lb.insert('end',name)
        def add():
            s=v.get().strip()
            if s and s not in vals:vals.append(s);lb.insert('end',s);self.persist()
        def remove():
            if lb.curselection():
                idx=lb.curselection()[0];vals.pop(idx);lb.delete(idx);self.persist()
        def finger():
            if lb.curselection():
                val=lb.get(lb.curselection()[0]);self.inputs['Finger_host'].set(val)
                self.select_page('Finger');w.destroy();self.execute_network('Finger')
        bar=ttk.Frame(form);bar.pack(fill='x',pady=(8,0))
        for label,func in [('Add Address',add),('Delete',remove),('Finger',finger),('OK',w.destroy)]:
            ttk.Button(bar,text=label,command=func).pack(side='left',padx=(0,7))
        lb.bind('<Double-1>',lambda e:finger())

    def make_time_page(self):
        page='Time';frame=self.pages[page]
        day=ttk.LabelFrame(frame,text='Daytime');day.pack(fill='x',pady=3)
        row=ttk.Frame(day);row.pack(fill='x',padx=7,pady=5)
        ttk.Label(row,text='Remote host:').pack(side='left',padx=(0,7))
        dayhost=self.input_combobox(row,page,'Time_dayhost')
        dayhost.pack(side='left',fill='x',expand=True)
        self.time_suggestions(dayhost,'Time_dayhost','Daytime')
        if not self.inputs['Time_dayhost'].get():self.inputs['Time_dayhost'].set('time.inrim.it')
        ttk.Button(row,text='DayTime',command=self.query_daytime).pack(side='left',padx=7)
        ttk.Button(row,text='Cancel',command=lambda:self.cancel(page)).pack(side='left')
        sync=ttk.LabelFrame(frame,text='Clock Synchronization');sync.pack(fill='x',pady=(8,3))
        row=ttk.Frame(sync);row.pack(fill='x',padx=7,pady=7)
        ttk.Label(row,text='Time server:').pack(side='left',padx=(0,7))
        server=self.input_combobox(row,page,'Time_server')
        server.pack(side='left',fill='x',expand=True)
        if not self.inputs['Time_server'].get():self.inputs['Time_server'].set('time.inrim.it')
        self.time_proto=tk.StringVar(value='SNTP')
        for value in ('TCP','UDP','SNTP'):
            ttk.Radiobutton(row,text=value,value=value,variable=self.time_proto,
                            command=lambda c=server:self.time_suggestions(c,'Time_server',self.time_proto.get())
                            ).pack(side='left',padx=5)
        self.time_suggestions(server,'Time_server','SNTP')
        options=ttk.Frame(sync);options.pack(fill='x',padx=7)
        self.time_fallback=tk.BooleanVar(value=True)
        ttk.Checkbutton(options,text='If the server does not respond, try the other listed servers',
                        variable=self.time_fallback).pack(side='left')
        self.time_historic=tk.BooleanVar(value=False)
        ttk.Checkbutton(options,text='Include historic servers',variable=self.time_historic,
                        command=lambda:(self.time_suggestions(dayhost,'Time_dayhost'),
                                        self.time_suggestions(server,'Time_server'))
                        ).pack(side='left',padx=(12,0))
        self.time_note=tk.StringVar(value='')
        ttk.Label(sync,textvariable=self.time_note,foreground='#547086').pack(anchor='w',padx=7,pady=(3,0))
        for combo,key in ((dayhost,'Time_dayhost'),(server,'Time_server')):
            combo.bind('<<ComboboxSelected>>',lambda e,k=key:self.time_note.set(time_services.server_note(self.inputs[k].get())))
        bottom=ttk.Frame(sync);bottom.pack(fill='x',padx=7,pady=(4,7))
        ttk.Button(bottom,text='Check remote time',command=self.query_clock).pack(side='left')
        ttk.Button(bottom,text='Cancel',command=lambda:self.cancel(page)).pack(side='left',padx=7)
        ttk.Label(bottom,text='Read only: never changes your system clock').pack(side='left',padx=12)
        self.status[page]=tk.StringVar(value='Status: Ready')
        ttk.Label(frame,textvariable=self.status[page]).pack(anchor='w',pady=(5,0))
        self.text_output(frame,page)

    def time_suggestions(self,combo,key,protocol=None):
        combo['values']=self.combo_values(key)

    def run_time_query(self,protocol,host):
        page='Time'
        fallback=self.time_fallback.get()
        historic=self.time_historic.get()
        self.clear(page)
        def worker(stop):
            def attempt(name):
                self.post(self.set_status,page,f'Querying {name} ({protocol})...')
            try:
                if fallback:
                    result,attempts=time_services.query_with_fallback(protocol,host,stop,historic,attempt)
                    for name,error in attempts:
                        if error:self.post(self.append,page,f'{name}: no answer ({error})\n')
                    if len(attempts)>1:self.post(self.append,page,'\n')
                else:
                    attempt(host)
                    result=time_services.query(protocol,host)
                text=time_services.format_result(result)
                if protocol!='Daytime':text+='\nSystem clock was NOT modified.\n'
                self.post(self.append,page,text)
            except (time_services.TimeServiceError,OSError,ValueError,OverflowError) as e:
                self.failed_tasks.add(page)
                self.post(self.append,page,f'{protocol} query failed: {e}\n')
        self.start(page,worker)

    def query_daytime(self):
        host=self.remember('Time_dayhost')
        if host:self.run_time_query('Daytime',host)

    def query_clock(self):
        host=self.remember('Time_server')
        if host:self.run_time_query(self.time_proto.get(),host)

    def make_scanner_page(self):
        page='Scanner';f=self.pages[page]
        top=ttk.LabelFrame(f,text='IP address range');top.pack(fill='x',pady=(0,5))
        row=ttk.Frame(top);row.pack(fill='x',padx=7,pady=7)
        self.scan_start=tk.StringVar(value='127.0.0.1')
        self.scan_end=tk.StringVar(value='127.0.0.1')
        ttk.Label(row,text='From:').pack(side='left')
        ttk.Entry(row,textvariable=self.scan_start,width=20).pack(side='left',padx=(4,12))
        ttk.Label(row,text='To:').pack(side='left')
        ttk.Entry(row,textvariable=self.scan_end,width=20).pack(side='left',padx=4)
        self.scan_timeout=tk.IntVar(value=600)
        ttk.Label(row,text='Timeout (ms):').pack(side='left',padx=(14,4))
        ttk.Spinbox(row,textvariable=self.scan_timeout,from_=100,to=10000,width=7).pack(side='left')
        flags=ttk.Frame(f);flags.pack(fill='x',pady=3)
        self.scan_resolve=tk.BooleanVar(value=True)
        self.scan_ports=tk.BooleanVar(value=False)
        ttk.Checkbutton(flags,text='Resolve IP address',variable=self.scan_resolve).pack(side='left')
        ttk.Checkbutton(flags,text='Scan Ports:',variable=self.scan_ports).pack(side='left',padx=(20,4))
        self.scan_pstart=tk.IntVar(value=1);self.scan_pend=tk.IntVar(value=1024)
        ttk.Spinbox(flags,from_=1,to=65535,textvariable=self.scan_pstart,width=6).pack(side='left')
        ttk.Label(flags,text=' to ').pack(side='left')
        ttk.Spinbox(flags,from_=1,to=65535,textvariable=self.scan_pend,width=6).pack(side='left')
        ports=ttk.LabelFrame(f,text='Services');ports.pack(fill='x',pady=6)
        self.service_flags={}
        for i,name in enumerate(SERVICE_PORTS):
            v=tk.BooleanVar(value=name in ('Echo','HTTP'))
            ttk.Checkbutton(ports,text=name,variable=v).grid(row=i//5,column=i%5,padx=11,pady=4,sticky='w')
            self.service_flags[name]=v
        self.button_bar(f,page,self.execute_scan,'Scan')
        self.status[page]=tk.StringVar(value='Status: Ready')
        ttk.Label(f,textvariable=self.status[page]).pack(anchor='w')
        self.tree_output(f,page,('No.','IP address','Host name','Open services'))

    def execute_scan(self):
        page='Scanner'
        try:
            start=ipaddress.IPv4Address(self.scan_start.get().strip())
            end=ipaddress.IPv4Address(self.scan_end.get().strip())
            count=int(end)-int(start)+1
            if count<1 or count>256:raise ValueError('Range must contain 1–256 IPv4 addresses.')
            ranges=[]
            if self.scan_ports.get():
                lo,hi=self.scan_pstart.get(),self.scan_pend.get()
                if not (1<=lo<=hi<=65535) or hi-lo+1>128:
                    raise ValueError('Port range must contain 1–128 TCP ports.')
                ranges=list(range(lo,hi+1))
            svcs=[(k,p) for k,p in SERVICE_PORTS.items() if p is not None and self.service_flags[k].get()]
            ports=sorted(set(ranges+[p for _,p in svcs]))
            if not ports and not self.service_flags['Echo'].get() and not self.scan_resolve.get():
                raise ValueError('Choose at least one service, port range or DNS resolution.')
            timeout=min(10,max(.1,self.scan_timeout.get()/1000))
        except (ValueError,tk.TclError) as e:
            messagebox.showerror('Scanner settings',str(e));return
        self.clear(page)
        echo=self.service_flags['Echo'].get()
        resolve=self.scan_resolve.get()
        def worker(stop):
            hosts=[str(ipaddress.IPv4Address(int(start)+i)) for i in range(count)]
            def check(ip):
                if stop.is_set(): return None
                found=[str(port) for port in open_tcp_ports(ip,ports,timeout,stop)]
                if echo and not stop.is_set():
                    try:
                        r=subprocess.run(['ping','-n','-c','1','-W','1',ip],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
                        if r.returncode==0:found.insert(0,'Echo')
                    except (OSError,subprocess.TimeoutExpired): pass
                hostname=''
                if resolve and not stop.is_set():
                    try:hostname=socket.gethostbyaddr(ip)[0]
                    except OSError:pass
                if not hostname and not found:return None
                labels=[]
                for s in found:
                    if s=='Echo':labels.append('Echo')
                    else:
                        names=[name for name,port in svcs if str(port)==s]
                        labels.append(f'{s} ({names[0]})' if names else s)
                return(ip,hostname,', '.join(labels))
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
                futs={pool.submit(check,ip):number for number,ip in enumerate(hosts,1)}
                for done,future in enumerate(concurrent.futures.as_completed(futs),1):
                    if stop.is_set():break
                    result=future.result()
                    # Number by position in the range, insert in address order.
                    if result:self.post(self.add_sorted_row,page,(futs[future],)+result)
                    if done%8==0 or done==count:self.post(self.set_status,page,f'Checked {done}/{count} addresses')
        self.start(page,worker)

    def make_remote_page(self, page):
        """One in-app interactive SSH or Telnet connection per protocol tab."""
        f = self.pages[page]
        self.remote_sessions[page] = None
        self.remote_screens[page] = ColourTerminalScreen()
        form = ttk.Frame(f)
        form.pack(fill='x', pady=(0, 7))
        form.columnconfigure(1, weight=2)
        form.columnconfigure(3, weight=1)
        self.inputs[f'{page}_host'] = tk.StringVar()
        self.inputs[f'{page}_port'] = tk.StringVar(value='22' if page == 'SSH' else '23')
        ttk.Label(form, text='Host').grid(row=0, column=0, sticky='w', padx=(0, 6), pady=5)
        ttk.Entry(form, textvariable=self.inputs[f'{page}_host']).grid(row=0, column=1, sticky='ew', padx=(0, 16), pady=5)
        ttk.Label(form, text='Port').grid(row=0, column=2, sticky='w', padx=(0, 6), pady=5)
        ttk.Entry(form, textvariable=self.inputs[f'{page}_port'], width=8).grid(row=0, column=3, sticky='w', pady=5)
        if page == 'SSH':
            self.inputs['SSH_user'] = tk.StringVar()
            self.inputs['SSH_key'] = tk.StringVar()
            ttk.Label(form, text='Username').grid(row=1, column=0, sticky='w', padx=(0, 6), pady=5)
            ttk.Entry(form, textvariable=self.inputs['SSH_user']).grid(row=1, column=1, sticky='ew', padx=(0, 16), pady=5)
            ttk.Label(form, text='Private key').grid(row=2, column=0, sticky='w', padx=(0, 6), pady=5)
            ttk.Entry(form, textvariable=self.inputs['SSH_key']).grid(row=2, column=1, columnspan=2, sticky='ew', padx=(0, 6), pady=5)
            ttk.Button(form, text='Browse…', command=self.choose_ssh_key).grid(row=2, column=3, sticky='w')
            ttk.Label(f, text='OpenSSH verifies host keys using your normal SSH configuration. Passwords are entered in the terminal and are never stored by Nettalabbo.').pack(anchor='w', pady=(0, 7))
        else:
            ttk.Label(f, text='WARNING: Telnet does not encrypt credentials or network traffic. Use only on trusted networks and legacy equipment.',
                      foreground='#a02020', wraplength=890).pack(anchor='w', pady=(2, 7))
        actions = ttk.Frame(f)
        actions.pack(fill='x', pady=(0, 8))
        connect = ttk.Button(actions, text='Connect', width=14, command=lambda p=page: self.connect_remote(p))
        connect.pack(side='left', padx=(0, 6))
        disconnect = ttk.Button(actions, text='Disconnect', width=14, state='disabled', command=lambda p=page: self.disconnect_remote(p))
        disconnect.pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Historic servers...', command=lambda p=page: self.historic_servers_dialog(p)).pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Clear screen', command=lambda p=page: self.remote_clear(p)).pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Copy selection', command=lambda p=page: self.remote_copy(p)).pack(side='left', padx=(0, 6))
        ttk.Button(actions, text='Paste', command=lambda p=page: self.remote_paste(p)).pack(side='left', padx=(0, 6))
        self.remote_buttons[page] = (connect, disconnect)
        panel = ttk.Frame(f)
        panel.pack(fill='both', expand=True)
        scroll = ttk.Scrollbar(panel)
        text = tk.Text(panel, background='#15202b', foreground='#e9eef5', insertbackground='white',
                       selectbackground='#425b79', font=('DejaVu Sans Mono', 10), wrap='none',
                       yscrollcommand=scroll.set, undo=False, state='disabled', takefocus=True,
                       padx=8, pady=8)
        text.pack(side='left', fill='both', expand=True)
        scroll.configure(command=text.yview)
        scroll.pack(side='right', fill='y')
        self.remote_consoles[page] = text
        text.bind('<KeyPress>', lambda e, p=page: self.remote_key(p, e))
        text.bind('<Button-3>', lambda e, p=page: self.remote_context_menu(e, p))
        text.bind('<Button-1>', lambda e: None)
        label = tk.StringVar(value='Disconnected. Connect manually to start a session.')
        ttk.Label(f, textvariable=label).pack(anchor='w', pady=(6, 0))
        self.remote_status[page] = label
        self.remote_write(page, f'Nettalabbo {VERSION}  •  {page} terminal\nConnect to a remote host using the controls above.\n')
        if page == 'SSH':
            self.remote_write(page, 'Authentication and host-key verification are handled by OpenSSH.\n')
        else:
            self.remote_write(page, 'Unencrypted protocol: avoid transmitting passwords or private information.\n')

    def make_diagnose_page(self):
        """Read-only domain/mail diagnostics; optional DNSBL is opt-in."""
        page = 'Diagnose'
        frame = self.pages[page]
        ttk.Label(frame, text='Domain and Mail Diagnose',
                  font=('Sans', 14, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='DNS, MX, SPF, DMARC, optional DKIM and DNS blacklists. '
                  'Results are diagnostic, not deliverability guarantees.',
                  wraplength=750).pack(anchor='w', pady=(3, 9))
        form = ttk.Frame(frame)
        form.pack(fill='x', pady=(0, 8))
        ttk.Label(form, text='Domain:').pack(side='left', padx=(0, 5))
        domain = tk.StringVar()
        self.inputs['Diagnose_domain'] = domain
        ttk.Entry(form, textvariable=domain, width=34).pack(side='left', padx=(0, 12))
        ttk.Label(form, text='DKIM selector:').pack(side='left')
        self.diagnose_selector = tk.StringVar()
        ttk.Entry(form, textvariable=self.diagnose_selector, width=15).pack(side='left', padx=(6, 0))
        self.diagnose_dnsbl = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text='Query third-party DNS blacklists (discloses domain and public IPs)',
                        variable=self.diagnose_dnsbl).pack(anchor='w', pady=(0, 6))
        self.diagnose_smtp = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text='Test SMTP on first MX server (connects to external host)',
                        variable=self.diagnose_smtp).pack(anchor='w', pady=(0, 6))
        ttk.Label(frame, text='DNSBL policy and resolver limits can make results inconclusive. '
                  'No SMTP recipient verification is performed.',
                  wraplength=750).pack(anchor='w', pady=(0, 8))
        ttk.Button(frame, text='Run Diagnose', command=self.execute_diagnose).pack(anchor='w')
        self.status[page] = tk.StringVar(value='Ready. No queries run automatically.')
        ttk.Label(frame, textvariable=self.status[page]).pack(anchor='w', pady=(7, 0))
        self.text_output(frame, page)

    def execute_diagnose(self):
        page = 'Diagnose'
        domain = self.inputs['Diagnose_domain'].get().strip()
        selector = self.diagnose_selector.get().strip()
        reputation = bool(self.diagnose_dnsbl.get())
        smtp = bool(self.diagnose_smtp.get())
        if reputation and not messagebox.askyesno(
                'External DNS blacklist queries',
                'DNSBL operators will receive queries containing the domain '
                'and public mail server IP addresses. Continue?', parent=self.root):
            return
        self.clear(page)
        def worker(stop):
            if stop.is_set():
                return
            try:
                report = run_domain_diagnose(domain, check_blacklists=reputation,
                                             dkim_selector=selector, check_smtp=smtp)
                if not stop.is_set():
                    self.post(self.append, page, report.as_text() + '\n')
                    self.post(self.set_status, page, 'Diagnostic checks completed.')
            except Exception as exc:
                if not stop.is_set():
                    self.post(self.append, page, 'Diagnose failed: ' + str(exc) + '\n')
                    self.post(self.set_status, page, 'Diagnostic checks failed.')
        self.start(page, worker)

    def historic_servers_dialog(self, initial_page='Telnet'):
        """Present SSH and Telnet independently for every historic catalog item.

        A documented protocol uses its published host/port. An alternative
        requires an explicit acknowledgement before a connection attempt.
        These catalog references are not live availability guarantees.
        """
        import webbrowser
        win = tk.Toplevel(self.root)
        win.title('Historic Servers | Nettalabbo')
        win.geometry('980x585')
        win.minsize(780, 490)
        win.transient(self.root)
        main = ttk.Frame(win, padding=12)
        main.pack(fill='both', expand=True)
        ttk.Label(main, text='Historic Servers', font=('Sans', 14, 'bold')).pack(anchor='w')
        ttk.Label(main, text=('Select a historic service, then choose SSH or Telnet. '
                     'The list is informational; network availability has not been confirmed. '
                     'Accounts may be required.'), wraplength=920).pack(anchor='w', pady=(3, 8))
        notebook = ttk.Notebook(main)
        notebook.pack(fill='both', expand=True)
        tree_by_group = {}
        group_names = {'telnet':'Telnet & BBS', 'ssh':'UNIX / SSH',
                       'reference':'Web / TLS references'}
        detail_var = tk.StringVar(value='Select a service to view available access methods.')
        for group in ('telnet', 'ssh', 'reference'):
            frame = ttk.Frame(notebook, padding=5)
            notebook.add(frame, text=group_names[group])
            tree = ttk.Treeview(frame, columns=('name','address','port','type'), show='headings', selectmode='browse')
            for col,label,width in [('name','Service',230),('address','Host / website',300),
                                    ('port','Port',65),('type','Documented',135)]:
                tree.heading(col,text=label)
                tree.column(col,width=width, stretch=col in ('name','address'),
                            anchor='center' if col=='port' else 'w')
            tree.pack(side='left',fill='both',expand=True)
            scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview)
            scroll.pack(side='right',fill='y')
            tree.configure(yscrollcommand=scroll.set)
            for entry in catalog_groups(group):
                tree.insert('', 'end', iid=entry['id'], values=(entry['name'],entry['host'],
                    str(entry['port']) if entry['port'] else '—',access_label(entry)))
            tree_by_group[group]=tree

        def current():
            group=('telnet','ssh','reference')[notebook.index('current')]
            selected=tree_by_group[group].selection()
            return get_entry(selected[0]) if selected else None

        def picked(event=None):
            entry=current()
            if not entry:
                detail_var.set('Select a service to see access requirements.')
                return
            status = ('Documented: SSH; Telnet: unconfirmed.' if entry['access']=='ssh'
                else 'Documented: Telnet; SSH: unconfirmed.' if entry['access']=='telnet'
                else 'No verified SSH or Telnet endpoint. Both methods require manual confirmation.')
            detail_var.set('{}\n{}\n{}'.format(entry['description'], entry['note'], status))

        for tree in tree_by_group.values():
            tree.bind('<<TreeviewSelect>>',picked)
        notebook.bind('<<NotebookTabChanged>>',picked)
        ttk.Label(main, textvariable=detail_var, wraplength=900, justify='left').pack(
            fill='x', anchor='w', pady=(8, 6))
        bar=ttk.Frame(main)
        bar.pack(fill='x')

        def attempt_protocol(page):
            entry=current()
            if not entry:
                messagebox.showinfo('Historic Servers', 'Select a service first.', parent=win)
                return
            destination=protocol_endpoint(entry,page)
            host, port, username, documented=destination
            if not documented:
                label=('SSH' if page=='SSH' else 'Telnet')
                if not messagebox.askyesno('Undocumented connection method',
                    '{} is not a documented {} endpoint.\n'
                    'This attempt may fail, connect to an unrelated service, or be refused.\n'
                    'The proposed port is {}. Continue anyway?'.format(entry['name'],label,port),
                    parent=win):
                    return
            if self.remote_sessions.get(page) is not None:
                messagebox.showwarning('Active terminal session',
                    'A {} session is already running. Disconnect it before opening another.'.format(page),
                    parent=win)
                return
            if page=='SSH' and not username:
                username=simpledialog.askstring('SSH username',
                    'Enter the account name for {}.\n'
                    '(A validated account may be required.)'.format(host),
                    parent=win)
                if username is None:
                    return
                username=username.strip()
                if not username:
                    messagebox.showinfo('SSH account required',
                        'Enter an account name to start SSH. You can also use the SSH panel manually.',parent=win)
                    return
            self.inputs[page+'_host'].set(host)
            self.inputs[page+'_port'].set(str(port))
            if page=='SSH':
                self.inputs['SSH_user'].set(username)
                self.inputs['SSH_key'].set('')  # Do not reuse a private key selected for a different server.
            win.destroy()
            self.select_page(page)
            self.set_status(page, '{} selected: {} on port {}.'.format(page,host,port))
            self.connect_remote(page)  # Explicit Connect via SSH/Telnet click initiated this attempt.

        def open_website():
            entry=current()
            if entry and entry['url'].startswith('https://'):
                webbrowser.open(entry['url'])

        def copy_address():
            entry=current()
            if not entry:
                return
            destination=connection_fields(entry)
            if destination:
                page,host,port,user=destination
                cmd=('ssh -p {} {}{}'.format(port,(user+'@') if user else '',host)
                     if page=='SSH' else 'telnet {} {}'.format(host,port))
            else:
                cmd=entry['url']
            self.copy_value(cmd)

        ttk.Button(bar,text='Connect via SSH', command=lambda:attempt_protocol('SSH')).pack(side='left',padx=(0,6))
        ttk.Button(bar,text='Connect via Telnet',command=lambda:attempt_protocol('Telnet')).pack(side='left',padx=(0,10))
        ttk.Button(bar,text='Copy command / URL',command=copy_address).pack(side='left',padx=(0,6))
        ttk.Button(bar,text='Official website / instructions',command=open_website).pack(side='left')
        ttk.Button(bar,text='Close',command=win.destroy).pack(side='right')
        default='telnet' if initial_page=='Telnet' else 'ssh'
        notebook.select(0 if default=='telnet' else 1)
        nodes=tree_by_group[default].get_children()
        if nodes:
            tree_by_group[default].selection_set(nodes[0])
            picked()
        # Double click only selects the entry: never guess the user's preferred protocol.

    def choose_ssh_key(self):
        path = filedialog.askopenfilename(title='Select your SSH private key', initialdir=str(Path.home() / '.ssh'))
        if path:
            self.inputs['SSH_key'].set(path)

    def remote_write(self, page, string):
        console = self.remote_consoles[page]
        content = self.remote_screens[page].feed(string)
        # Preserve selection and viewport as live output arrives during copying.
        had_selection = bool(console.tag_ranges('sel'))
        try:
            first, last = console.index('sel.first'), console.index('sel.last')
        except tk.TclError:
            first = last = None
        yview = console.yview()
        console.configure(state='normal')
        console.delete('1.0', 'end')
        console.insert('1.0', content)
        # Remote SGR modifies presentation only, not executable UI commands.
        for name in console.tag_names():
            if name.startswith('ansi_style_'):
                console.tag_delete(name)
        tags = {}
        for line, start, end, style in self.remote_screens[page].styled_runs():
            fg, bg, bold, underline, reverse = style
            if reverse:
                fg, bg = bg or '#15202b', fg or '#e9eef5'
            if style not in tags:
                if len(tags) >= 256:
                    continue
                name = 'ansi_style_' + str(len(tags))
                opts = {}
                if fg: opts['foreground'] = fg
                if bg: opts['background'] = bg
                if underline: opts['underline'] = 1
                if bold: opts['font'] = ('DejaVu Sans Mono', 10, 'bold')
                console.tag_configure(name, **opts)
                tags[style] = name
            console.tag_add(tags[style], f'{line}.{start}', f'{line}.{end}')
        if first and last:
            try: console.tag_add('sel', first, last)
            except tk.TclError: pass
        if had_selection and yview:
            console.yview_moveto(yview[0])
        else:
            console.see('end')
        console.configure(state='disabled')

    def remote_clear(self, page):
        self.remote_screens[page].clear()
        self.remote_write(page, '')
        self.remote_consoles[page].focus_set()

    def remote_context_menu(self, event, page):
        console = self.remote_consoles[page]
        try:
            selected_text = console.get('sel.first', 'sel.last')
        except tk.TclError:
            selected_text = ''
        menu = tk.Menu(console, tearoff=False)
        menu.add_command(label='Copy selection', state='normal' if selected_text else 'disabled',
                         command=lambda: self.copy_value(selected_text))
        menu.add_command(label='Copy visible terminal text',
                         command=lambda: self.copy_value(console.get('1.0', 'end-1c')))
        menu.add_separator()
        menu.add_command(label='Paste into terminal (sends to remote host)',
                         state='normal' if self.remote_sessions.get(page) else 'disabled',
                         command=lambda: self.remote_paste(page))
        menu.tk_popup(event.x_root, event.y_root)
        menu.grab_release()
        return 'break'

    def remote_copy(self, page):
        try:
            selection = self.remote_consoles[page].selection_get()
        except tk.TclError:
            self.set_status(page, 'Select text to copy.')
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(selection)

    def remote_paste(self, page):
        session = self.remote_sessions.get(page)
        if not session:
            return
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            return
        # Explicit user paste; never store pasted data or authentication secrets.
        session.send(text.replace('\r\n', '\r').replace('\n', '\r'))

    def remote_key(self, page, event):
        session = self.remote_sessions.get(page)
        key = event.keysym
        ctrl = bool(event.state & 0x4)
        shift = bool(event.state & 0x1)
        if ctrl and shift and key.lower() == 'c':
            self.remote_copy(page)
            return 'break'
        if ctrl and shift and key.lower() == 'v':
            self.remote_paste(page)
            return 'break'
        if ctrl and key.lower() == 'c':
            # Always interrupt: a selection never changes ^C semantics in a terminal.
            if session:
                session.send('\x03')
            return 'break'
        if not session:
            return 'break'
        sequence = {'Return':'\r', 'KP_Enter':'\r', 'BackSpace':'\x7f',
                    'Delete':'\x1b[3~', 'Up':'\x1b[A', 'Down':'\x1b[B',
                    'Left':'\x1b[D', 'Right':'\x1b[C', 'Home':'\x1b[H',
                    'End':'\x1b[F', 'Tab':'\t', 'Escape':'\x1b',
                    'Prior':'\x1b[5~', 'Next':'\x1b[6~'}.get(key)
        if sequence is None and ctrl and len(key) == 1 and key.isalpha():
            sequence = chr(ord(key.lower()) - ord('a') + 1)
        if sequence is None and event.char and event.char.isprintable():
            sequence = event.char
        if sequence:
            session.send(sequence)
        return 'break'

    def connect_remote(self, page):
        if self.remote_sessions.get(page) is not None:
            self.set_status(page, 'Disconnect the current session first.')
            return
        try:
            cmd = connection_command(page, self.inputs[f'{page}_host'].get(),
                self.inputs[f'{page}_port'].get(),
                self.inputs['SSH_user'].get() if page == 'SSH' else '',
                self.inputs['SSH_key'].get() if page == 'SSH' else '')
        except (ValueError, FileNotFoundError) as exc:
            messagebox.showerror(f'{page} connection', str(exc))
            return
        if page == 'Telnet':
            if not messagebox.askokcancel('Unencrypted Telnet',
                'Telnet sends all data, including passwords, without encryption.\n\nConnect anyway?'):
                return
        session = PtySession(
            on_text=lambda text: self.post(self.remote_write, page, text),
            on_exit=lambda code: self.post(self.remote_finished, page, session, code))
        self.remote_sessions[page] = session
        self.remote_clear(page)
        self.remote_write(page, f'Connecting to {self.inputs[f"{page}_host"].get().strip()} ({page})…\r\n')
        self.remote_buttons[page][0].configure(state='disabled')
        self.remote_buttons[page][1].configure(state='normal')
        self.remote_status[page].set('Connecting / connected. The session stays open when you switch tabs.')
        self.set_status(page, 'Connecting…')
        session.start(cmd)
        self.remote_consoles[page].focus_set()

    def remote_finished(self, page, session, code):
        if self.remote_sessions.get(page) is not session:
            return
        self.remote_sessions[page] = None
        self.remote_buttons[page][0].configure(state='normal')
        self.remote_buttons[page][1].configure(state='disabled')
        reason = f'exit code {code}' if code is not None else 'session could not start'
        self.remote_write(page, f'\r\n[Disconnected: {reason}]\r\n')
        self.remote_status[page].set('Disconnected.')
        self.set_status(page, 'Disconnected.')

    def disconnect_remote(self, page):
        session = self.remote_sessions.get(page)
        if session:
            session.close()
            self.remote_status[page].set('Disconnecting…')

    def make_legacy_page(self):
        """A browser-like navigator, keeping protocol diagnostics one click away."""
        page = 'Legacy Navigator'
        f = self.pages[page]
        ttk.Label(f, text='Legacy & Alternative Networks', font=('Sans', 14, 'bold')).pack(anchor='w')
        ttk.Label(f, text='Coloured, underlined links include URLs in plain text. Raw shows the server response.',
                  wraplength=760).pack(anchor='w', pady=(3, 8))
        nav = ttk.Frame(f)
        nav.pack(fill='x', pady=(0, 6))
        self.legacy_back_button = ttk.Button(nav, text='◀ Back', command=self.legacy_back, width=8)
        self.legacy_back_button.pack(side='left', padx=(0, 3))
        self.legacy_forward_button = ttk.Button(nav, text='Forward ▶', command=self.legacy_forward, width=10)
        self.legacy_forward_button.pack(side='left', padx=(0, 3))
        ttk.Button(nav, text='⌂ Home', command=self.legacy_home, width=8).pack(side='left', padx=(0, 7))
        self.legacy_url = self.input_combobox(nav, page, 'legacy_url', width=43)
        self.legacy_url.pack(side='left', fill='x', expand=True, padx=(0, 5))
        self.legacy_url.bind('<Return>', lambda e: self.execute_legacy())
        ttk.Button(nav, text='Go', command=self.execute_legacy, width=5).pack(side='left', padx=(0, 5))
        ttk.Button(nav, text='Stop', command=self.legacy_stop, width=6).pack(side='left')
        action = ttk.Frame(f)
        action.pack(fill='x', pady=(0, 6))
        self.legacy_display_mode = tk.StringVar(value='Rendered')
        ttk.Radiobutton(action, text='Rendered', value='Rendered', variable=self.legacy_display_mode,
                        command=self.legacy_redraw).pack(side='left')
        ttk.Radiobutton(action, text='Raw', value='Raw', variable=self.legacy_display_mode,
                        command=self.legacy_redraw).pack(side='left', padx=(6, 10))
        ttk.Label(action, text='Colours:').pack(side='left', padx=(2, 4))
        saved_theme = self.settings.get('legacy_theme', 'Classic')
        if saved_theme not in LEGACY_THEME_NAMES:
            saved_theme = 'Classic'
        self.legacy_theme = tk.StringVar(value=saved_theme)
        ttk.Combobox(action, textvariable=self.legacy_theme, values=LEGACY_THEME_NAMES,
                     state='readonly', width=12).pack(side='left', padx=(0, 8))
        self.legacy_theme.trace_add('write', lambda *_: self.legacy_colour_changed())
        ttk.Button(action, text='Sample servers...', command=self.legacy_example_dialog).pack(side='left', padx=(0, 5))
        ttk.Button(action, text='Copy', command=lambda: self.copy_output(page)).pack(side='left', padx=5)
        ttk.Button(action, text='Save', command=lambda: self.save_output(page)).pack(side='left')
        self.legacy_links_menu = tk.Menu(self.root, tearoff=False)
        self.legacy_links_button = ttk.Menubutton(action, text='Links (0) ▾', direction='below', menu=self.legacy_links_menu)
        self.legacy_links_button.pack(side='right')
        self.legacy_links_button.configure(state='disabled')
        ttk.Button(action, text='Titan upload...', command=self.legacy_titan_dialog).pack(side='right', padx=(4, 8))
        ttk.Button(action, text='SSH / Telnet', command=self.open_legacy_remote).pack(side='right', padx=4)
        catalog_box = ttk.Frame(f)
        catalog_box.pack(fill='x', pady=(0, 5))
        self.legacy_catalog_visible = tk.BooleanVar(value=False)
        ttk.Checkbutton(catalog_box, text='Protocol directory', variable=self.legacy_catalog_visible,
                        command=self.legacy_toggle_catalog).pack(anchor='w')
        self.legacy_catalog_frame = ttk.LabelFrame(catalog_box, text='Available and experimental protocols', padding=5)
        self.legacy_catalog = ttk.Treeview(self.legacy_catalog_frame,
                       columns=('protocol','scheme','port','capability'), show='headings', height=4)
        for key, title, width in [('protocol','Protocol',115),('scheme','URI schemes',145),('port','Port',58),('capability','Capability',140)]:
            self.legacy_catalog.heading(key, text=title)
            self.legacy_catalog.column(key, width=width, stretch=(key in ('protocol', 'scheme')))
        for title, schemes, port, mode, description in CATALOG:
            capability = {'read':'Read client','remote':'In-app terminal','upload':'Upload client','reference':'Future release'}[mode]
            self.legacy_catalog.insert('', 'end', values=(title, ', '.join(x+'://' for x in schemes),
                                                             str(port or 'varies'), capability))
        catalog_scroll = ttk.Scrollbar(self.legacy_catalog_frame, orient='vertical', command=self.legacy_catalog.yview)
        self.legacy_catalog.configure(yscrollcommand=catalog_scroll.set)
        catalog_scroll.pack(side='right', fill='y')
        self.legacy_catalog.pack(side='left', fill='x', expand=True)
        self.legacy_catalog.bind('<<TreeviewSelect>>', self.legacy_catalog_selected)
        self.legacy_detail = tk.StringVar(value='Choose a protocol or enter its URL above.')
        ttk.Label(f, textvariable=self.legacy_detail, wraplength=760).pack(anchor='w', pady=(0, 5))
        self.status[page] = tk.StringVar(value='Ready. Press Go or Enter to navigate.')
        ttk.Label(f, textvariable=self.status[page]).pack(anchor='w', pady=(0, 3))
        self.legacy_status_detail = tk.StringVar(value=legacy_link_legend(self.legacy_theme.get()))
        ttk.Label(f, textvariable=self.legacy_status_detail, foreground='#537284').pack(anchor='w', pady=(0, 3))
        self.text_output(f, page)
        self.legacy_update_navigation()

    def legacy_toggle_catalog(self):
        if self.legacy_catalog_visible.get():
            self.legacy_catalog_frame.pack(fill='x', pady=(0, 5))
        else:
            self.legacy_catalog_frame.pack_forget()

    def legacy_update_navigation(self):
        self.legacy_back_button.configure(state=('normal' if self.legacy_history_position > 0 else 'disabled'))
        self.legacy_forward_button.configure(state=('normal' if self.legacy_history_position + 1 < len(self.legacy_history) else 'disabled'))

    def legacy_back(self):
        if self.legacy_history_position > 0:
            self.legacy_history_position -= 1
            self.legacy_restore_history()

    def legacy_forward(self):
        if self.legacy_history_position + 1 < len(self.legacy_history):
            self.legacy_history_position += 1
            self.legacy_restore_history()

    def legacy_restore_history(self):
        self.legacy_stop(silent=True)
        address, result = self.legacy_history[self.legacy_history_position]
        self.inputs['legacy_url'].set(address)
        self.legacy_show_result(result)
        self.legacy_update_navigation()
        self.set_status('Legacy Navigator', 'Restored from browsing history (no network request).')

    def legacy_home(self):
        address = self.inputs['legacy_url'].get().strip()
        try:
            parsed, scheme, port = parse_legacy_url(address)
        except LegacyError:
            self.legacy_example_dialog()
            return
        # Use the selected protocol's root. Gopher root is menu selector /1.
        home_path = '/1' if scheme in ('gopher', 'gophers') else '/'
        self.legacy_navigate(urlunsplit((scheme, parsed.netloc, home_path, '', '')))

    def legacy_stop(self, silent=False):
        page = 'Legacy Navigator'
        task = self.tasks.pop(page, None)
        if task:
            task[0].set()
            self.activity_started.pop(page, None)
            self.update_activity()
            if not silent:
                self.set_status(page, 'Stopped. Late responses are discarded; socket timeout is bounded.')
        elif not silent:
            self.set_status(page, 'No active request to stop.')

    def legacy_navigate(self, address):
        """Open internal protocol links; external destinations require confirmation."""
        scheme = urlsplit(address).scheme.lower()
        if scheme in ('http', 'https'):
            if messagebox.askyesno('Open external link?',
                    'Open this address in your default web browser?\n\n'+address):
                webbrowser.open(address)
            return
        if scheme not in SCHEMES:
            messagebox.showwarning('Unsupported destination',
                'Nettalabbo cannot open this protocol directly:\n'+address)
            return
        if scheme in ('ssh', 'telnet'):
            self.inputs['legacy_url'].set(address)
            self.open_legacy_remote()
            return
        if scheme == 'titan':
            messagebox.showinfo('Titan', 'Titan uploads need an explicitly selected file and the Upload button.')
            self.inputs['legacy_url'].set(address)
            return
        if scheme in ('gopher', 'gophers') and urlsplit(address).path.startswith('/7') and not urlsplit(address).query:
            term = simpledialog.askstring('Gopher search', 'Search term:', parent=self.root)
            if term is None:
                return
            address = address + '?' + url_quote(term, safe='')
        self.inputs['legacy_url'].set(address)
        self.execute_legacy()

    def legacy_open_links_dialog(self):
        if not self.legacy_current_result:
            return
        links = list(getattr(self, 'legacy_current_links', []))
        win = tk.Toplevel(self.root)
        win.title('Document links')
        win.geometry('750x400')
        listing = tk.Listbox(win, font=('DejaVu Sans Mono', 10))
        listing.pack(fill='both', expand=True, padx=12, pady=12)
        for title, url in links:
            listing.insert('end', '{}  →  {}'.format(title, url))
        def go(event=None):
            selection = listing.curselection()
            if selection:
                win.destroy()
                self.legacy_navigate(links[selection[0]][1])
        listing.bind('<Double-Button-1>', go)
        ttk.Button(win, text='Open selected', command=go).pack(anchor='e', padx=12, pady=(0, 10))

    def legacy_colour_changed(self):
        """Save only the appearance preference; never mutate protocol results."""
        name = self.legacy_theme.get()
        if name not in LEGACY_THEME_NAMES:
            return
        self.settings['legacy_theme'] = name
        self.persist()
        self.legacy_redraw()

    def legacy_redraw(self):
        if self.legacy_current_result:
            self.legacy_show_result(self.legacy_current_result)

    def legacy_show_result(self, result):
        """Render coloured, always-underlined links into a read-only Tk Text widget."""
        page = 'Legacy Navigator'
        self.legacy_current_result = result
        w = self.output[page]
        w.configure(state='normal')
        w.delete('1.0', 'end')
        colours = legacy_palette(self.legacy_theme.get())
        # Raw remains unstyled and shows exactly the available server response.
        if self.legacy_display_mode.get() == 'Raw':
            w.configure(background='white', foreground='#292b30', insertbackground='#292b30')
            w.insert('end', legacy_raw_text(result))
        else:
            w.configure(background=colours['background'], foreground=colours['foreground'],
                        insertbackground=colours['foreground'])
            w.tag_configure('legacy_heading', font=('Sans', 12, 'bold'), foreground=colours['heading'], spacing1=8)
            w.tag_configure('legacy_info', foreground=colours['info'])
            w.insert('end', '{}  ·  {}  ·  {} bytes\n\n'.format(result.protocol.upper(), result.status, result.bytes_received), 'legacy_info')
            for index, (kind, label, destination) in enumerate(legacy_segments(result)):
                if not destination:
                    w.insert('end', label, 'legacy_heading' if kind == 'heading' else 'legacy_info' if kind == 'info' else ())
                    continue
                tag = 'legacy_hyperlink_{}'.format(index)
                w.tag_configure(tag, foreground=colours[kind], underline=1)
                w.insert('end', label, tag)
                w.tag_bind(tag, '<Button-1>', lambda e, url=destination: self.legacy_navigate(url))
                w.tag_bind(tag, '<Enter>', lambda e, url=destination, widget=w: (
                    widget.configure(cursor='hand2'), self.legacy_status_detail.set(url)))
                w.tag_bind(tag, '<Leave>', lambda e, widget=w: (
                    widget.configure(cursor='xterm'),
                    self.legacy_status_detail.set(legacy_link_legend(self.legacy_theme.get()))))
        w.configure(state='disabled')
        self.legacy_links_menu.delete(0, 'end')
        links = legacy_distinct_links(legacy_segments(result))
        self.legacy_current_links = links
        for title, url in links[:40]:
            short = title[:65] + ('…' if len(title) > 65 else '')
            self.legacy_links_menu.add_command(label=short, command=lambda target=url:self.legacy_navigate(target))
        if len(links) > 40:
            self.legacy_links_menu.add_separator()
            self.legacy_links_menu.add_command(label='Show all {} links…'.format(len(links)),
                                               command=self.legacy_open_links_dialog)
        self.legacy_links_button.configure(text='Links ({}) ▾'.format(len(links)),
                                           state=('normal' if links else 'disabled'))
        self.legacy_detail.set('Click underlined links, including URLs in text documents.  {} link(s) found.'.format(len(links)))
        self.legacy_status_detail.set(legacy_link_legend(self.legacy_theme.get()))

    def legacy_example_dialog(self):
        # Public reference endpoints only; individual services may change or become unavailable.
        examples = [
            ('Gopher · Floodgap', 'gopher://gopher.floodgap.com/1'),
            ('Gemini · Gemini Protocol', 'gemini://geminiprotocol.net/'),
            ('Gemini · CircumLunar', 'gemini://gemini.circumlunar.space/'),
            ('DICT · dict.org', 'dict://dict.org:2628/hello'),
            ('NNTP · Eternal September (registration required)', 'nntp://news.eternal-september.org/'),
        ]
        win = tk.Toplevel(self.root)
        win.title('Known public legacy services')
        win.geometry('690x310')
        win.transient(self.root)
        panel = ttk.Frame(win, padding=12)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Public examples for manual testing',
                  font=('Sans', 12, 'bold')).pack(anchor='w', pady=(0, 8))
        ttk.Label(panel, text='Reference hosts, not a live availability guarantee. Some may require registration or block automated clients.',
                  wraplength=620).pack(anchor='w', pady=(0, 8))
        listing = tk.Listbox(panel, height=8, font=('DejaVu Sans Mono', 10))
        listing.pack(fill='both', expand=True)
        for label, address in examples:
            listing.insert('end', '{}  —  {}'.format(label, address))
        def use_selected():
            selection = listing.curselection()
            if selection:
                self.inputs['legacy_url'].set(examples[selection[0]][1])
                win.destroy()
                self.select_page('Legacy Navigator')
        listing.bind('<Double-Button-1>', lambda e: use_selected())
        ttk.Button(panel, text='Use selected address', command=use_selected).pack(anchor='e', pady=(9,0))

    def legacy_catalog_selected(self,event=None):
        selected=self.legacy_catalog.selection()
        if not selected:return
        values=self.legacy_catalog.item(selected[0],'values')
        title=values[0]
        entry=next((item for item in CATALOG if item[0]==title),None)
        if not entry:return
        self.legacy_detail.set('{}: {}  |  {}'.format(title,values[3],entry[4]))
        if not self.inputs['legacy_url'].get().strip():
            self.inputs['legacy_url'].set(entry[1][0]+'://')

    def legacy_deliver(self, result, stop):
        task = self.tasks.get('Legacy Navigator')
        if task and task[0] is stop and not stop.is_set():
            self.legacy_render(result)

    def legacy_render(self, result):
        page = 'Legacy Navigator'
        # Only called for a non-cancelled operation on the GUI thread.
        if self.legacy_history_position < len(self.legacy_history)-1:
            self.legacy_history = self.legacy_history[:self.legacy_history_position+1]
        address = result.address
        self.legacy_history.append((address, result))
        if len(self.legacy_history) > 60:
            self.legacy_history = self.legacy_history[-60:]
        self.legacy_history_position = len(self.legacy_history)-1
        self.inputs['legacy_url'].set(address)
        self.legacy_show_result(result)
        self.legacy_update_navigation()

    def legacy_trust_guarded(self, error, address, stop):
        task = self.tasks.get('Legacy Navigator')
        if task and task[0] is stop and not stop.is_set():
            self.legacy_trust_prompt(error, address)

    def legacy_trust_prompt(self,error,address):
        msg=('The server uses a TLS certificate that could not be verified by the system.\n\n'
             '{}\nSHA256: {}\n\n'
             'Trust this fingerprint for this server? It will be checked on subsequent visits. '
             'Only approve if you recognise the server; the first connection may be intercepted.').format(
             error.origin,error.fingerprint)
        if messagebox.askyesno('Trust this alternative-network certificate?',msg):
            self.settings.setdefault('legacy_tls_pins',{})[error.origin]=error.fingerprint
            self.persist()
            self.root.after(250, self.execute_legacy)
        else:
            self.set_status('Legacy Navigator','Certificate not trusted. No content retrieved.')

    def execute_legacy(self):
        page = 'Legacy Navigator'
        address = self.inputs['legacy_url'].get().strip()
        try:
            p, scheme, port = parse_legacy_url(address)
        except LegacyError as exc:
            messagebox.showerror('Legacy Navigator', str(exc))
            return
        if scheme in ('ssh', 'telnet'):
            self.open_legacy_remote()
            return
        self.remember('legacy_url')
        # Restart instead of blocking on the previous request. A stopped worker
        # may still need to finish its bounded socket timeout in the background.
        self.legacy_stop(silent=True)
        self.set_status(page, 'Connecting to {}…'.format(address))
        pins = dict(self.settings.get('legacy_tls_pins', {}))
        def worker(stop):
            if stop.is_set():
                return
            try:
                result = legacy_fetch(address, pins, stop)
            except TrustRequired as exc:
                if not stop.is_set():
                    self.post(self.legacy_trust_guarded, exc, address, stop)
                return
            if not stop.is_set():
                self.post(self.legacy_deliver, result, stop)
        self.start(page, worker)

    def follow_legacy_link(self):
        self.legacy_open_links_dialog()

    def open_legacy_remote(self):
        address=self.inputs['legacy_url'].get().strip()
        try:
            p,scheme,port=parse_legacy_url(address)
        except LegacyError:
            self.select_page('SSH');return
        if scheme not in ('ssh','telnet'):
            self.select_page('SSH');return
        page=scheme.upper() if scheme=='ssh' else 'Telnet'
        self.inputs[page+'_host'].set(p.hostname)
        self.inputs[page+'_port'].set(str(port))
        if scheme=='ssh' and p.username:self.inputs['SSH_user'].set(p.username)
        self.select_page(page)
        self.set_status(page,'Address transferred. Press Connect when ready.')


    def make_mail_page(self):
        """Mailbox uncertainty is prominent: SMTP transactions do not prove delivery."""
        page = 'Mail Inspector'
        f = self.pages[page]
        ttk.Label(f, text='MX records describe routing, not individual mailbox existence. '
                  'Recipient testing sends an SMTP envelope only; never a message.',
                  wraplength=730).pack(anchor='w', pady=(4, 9))
        block = ttk.LabelFrame(f, text='Check one email address', padding=12)
        block.pack(fill='x', pady=(0, 9))
        row = ttk.Frame(block); row.pack(fill='x')
        ttk.Label(row, text='Email address').pack(side='left', padx=(0, 7))
        self.mail_address = tk.StringVar()
        entry = ttk.Entry(row, textvariable=self.mail_address, width=39)
        entry.pack(side='left', fill='x', expand=True, padx=(0, 10))
        entry.bind('<Return>', lambda e: self.execute_mail_address())
        ttk.Button(row, text='Inspect address', command=self.execute_mail_address).pack(side='left')
        self.mail_probe = tk.BooleanVar(value=False)
        ttk.Checkbutton(block, text='Also ask the receiving SMTP server about this ONE recipient '
                        '(may be blocked; not proof of existence)',
                        variable=self.mail_probe).pack(anchor='w', pady=(7, 1))
        ttk.Label(block, text='Only check addresses you have a legitimate reason to verify. '
                  'No bulk lists, guessed addresses or automatic catch-all probes.',
                  wraplength=720).pack(anchor='w', pady=(2, 0))
        services = ttk.LabelFrame(f, text='Mail protocol connectivity (no login credentials)', padding=12)
        services.pack(fill='x', pady=(0, 9))
        svc = ttk.Frame(services); svc.pack(fill='x')
        ttk.Label(svc, text='Protocol').pack(side='left', padx=(0, 6))
        self.mail_service_type = tk.StringVar(value='IMAP')
        protocols = ttk.Combobox(svc, textvariable=self.mail_service_type, values=['IMAP','POP3','SMTP'],
                                 width=7, state='readonly')
        protocols.pack(side='left', padx=(0, 8))
        protocols.bind('<<ComboboxSelected>>', self.mail_port_changed)
        ttk.Label(svc, text='Server').pack(side='left', padx=(0, 6))
        self.mail_service_host = tk.StringVar()
        ttk.Entry(svc, textvariable=self.mail_service_host, width=24).pack(side='left',fill='x',expand=True,padx=(0,8))
        ttk.Label(svc, text='Port').pack(side='left', padx=(0, 5))
        self.mail_service_port = tk.StringVar(value='993')
        ttk.Entry(svc, textvariable=self.mail_service_port, width=6).pack(side='left', padx=(0, 9))
        ttk.Button(svc, text='Test server', command=self.execute_mail_service).pack(side='left')
        ttk.Label(services, text='Default secure ports: IMAP 993, POP3 995, SMTP 465. The IMAP/POP3 host may differ from the MX host. '
                  'Tests only the service handshake, not whether an inbox exists.',
                  wraplength=720).pack(anchor='w', pady=(6, 0))
        actions = ttk.Frame(f); actions.pack(fill='x', pady=(1, 7))
        ttk.Button(actions, text='Copy report', command=lambda: self.copy_output(page)).pack(side='left',padx=(0,7))
        ttk.Button(actions, text='Save report', command=lambda: self.save_output(page)).pack(side='left')
        ttk.Button(actions, text='Cancel', command=lambda: self.cancel(page)).pack(side='right')
        self.status[page] = tk.StringVar(value='Ready. No network request made.')
        ttk.Label(f,textvariable=self.status[page]).pack(anchor='w',pady=(0,4))
        self.text_output(f,page)
        self.append(page, 'A positive SMTP response is NOT proof of an existing mailbox.\n'
                    'A negative response can reflect policy, privacy or temporary restrictions.\n'
                    'IMAP/POP3 require authentication for mailbox inspection.\n')

    def mail_port_changed(self, event=None):
        self.mail_service_port.set({'IMAP':'993','POP3':'995','SMTP':'465'}[
            self.mail_service_type.get()])

    def execute_mail_address(self):
        page='Mail Inspector'
        try:
            address, domain = normalise_email(self.mail_address.get())
        except MailInspectionError as exc:
            messagebox.showerror('Mail Server Inspector', str(exc));return
        opted = bool(self.mail_probe.get())
        if opted and not messagebox.askyesno('Authorise single SMTP recipient check?',
                'Nettalabbo will contact the receiving server and submit a single RCPT TO for:\n\n'
                + address + '\n\nIt will NOT send a message, but the server may log this query. '
                'Responses are not conclusive and repeated probing may violate service policies. Continue?'):
            return
        self.clear(page)
        self.append(page, 'Inspecting mail routing for {}...\n'.format(domain))
        def worker(stop):
            if stop.is_set():return
            result=inspect_address(address, recipient_probe=opted)
            if not stop.is_set():self.post(self.mail_render, result)
        self.start(page,worker)

    def mail_render(self, result):
        self.clear('Mail Inspector')
        self.append('Mail Inspector',result.text())
        # MX hosts usually differ from IMAP/POP3 service hosts; never infer those endpoints.

    def execute_mail_service(self):
        page='Mail Inspector'
        kind=self.mail_service_type.get()
        host=self.mail_service_host.get()
        port=self.mail_service_port.get()
        self.append(page, '\nChecking {} service on {}:{} ...\n'.format(kind,host,port))
        def worker(stop):
            if stop.is_set():return
            result=test_mail_service(kind,host,port)
            if not stop.is_set():self.post(self.append,page,result+'\n')
        self.start(page,worker)

    def legacy_titan_dialog(self):
        """An upload never occurs as a side-effect of visiting a Titan link."""
        address=self.inputs['legacy_url'].get().strip()
        try:
            _,scheme,_=parse_legacy_url(address)
            if scheme!='titan':
                raise LegacyError('Enter a titan:// address before choosing Titan upload.')
        except LegacyError as exc:
            messagebox.showerror('Titan upload',str(exc));return
        path=filedialog.askopenfilename(title='Select a file for Titan upload (max 256 KiB)')
        if not path:return
        try:
            if Path(path).stat().st_size > 262144 or Path(path).stat().st_size == 0:
                raise LegacyError('Choose a nonempty file smaller than 256 KiB. Zero-byte uploads can delete content.')
        except OSError as exc:
            messagebox.showerror('Titan upload',str(exc));return
        if not messagebox.askyesno('Confirm Titan upload',
                'UPLOAD a file to a remote server?\n\n{}\n\n{}\n\n'
                'This can change content at the remote destination. Proceed only if authorised.'.format(path,address)):
            return
        pins=dict(self.settings.get('legacy_tls_pins',{}))
        self.clear('Legacy Navigator')
        self.append('Legacy Navigator','Uploading explicitly selected file...\n')
        def worker(stop):
            if stop.is_set():return
            try:
                result=titan_upload(address,Path(path).read_bytes(),pins=pins)
            except TrustRequired as error:
                self.post(self.legacy_titan_trust_prompt,error,address,path)
                return
            if not stop.is_set():self.post(self.legacy_render,result)
        self.start('Legacy Navigator',worker)

    def legacy_titan_trust_prompt(self,error,address,path):
        if messagebox.askyesno('Unverified Titan TLS certificate',
                'Certificate is not trusted by system CA. Verify independently:\n\n'
                '{}\nSHA256: {}\n\nTrust and retry this upload?'.format(error.origin,error.fingerprint)):
            self.settings.setdefault('legacy_tls_pins',{})[error.origin]=error.fingerprint
            self.persist()
            self.root.after(200,self.legacy_titan_dialog)
        else:self.set_status('Legacy Navigator','Titan upload cancelled. Certificate not trusted.')

    def make_info_page(self):
        f=self.pages['Info']
        ttk.Label(f,text='Linux network information',font=('Sans',12,'bold')).pack(anchor='w',pady=(3,10))
        self.info_text=tk.Text(f,wrap='word',font=('Courier',10),height=17,relief='sunken',bd=2)
        self.info_text.pack(fill='both',expand=True)
        self.info_text.bind('<Control-c>', lambda e: self.copy_selection_text(self.info_text))
        self.info_text.bind('<Button-3>', lambda e: self.text_context_menu(e, self.info_text))
        ttk.Button(f,text='Refresh local host & interfaces',command=self.refresh_info).pack(anchor='w',pady=8)
        ttk.Label(f, text='Local Host belongs here: it does not query the remote domain in DNS.',
                  foreground='#506d7c').pack(anchor='w', pady=(0,4))
        self.refresh_info()

    def refresh_info(self):
        host=socket.gethostname()
        try:addresses=sorted({e[4][0] for e in socket.getaddrinfo(host,None)})
        except OSError:addresses=[]
        lines=['Computer name:         '+host,'Operating system:       '+platform.platform(),
            'System:                 '+platform.system(),'Python version:         '+platform.python_version(),
            'Local IP addresses:     '+(', '.join(addresses) if addresses else 'not available'),
            'Network stack:          Linux TCP/IP sockets',
            'Winsock Info:           Replaced by native Linux sockets',
            '']
        resolv=Path('/etc/resolv.conf')
        if resolv.exists():
            try:
                lines+=['Resolver configuration:','\n'.join(resolv.read_text().splitlines()[:12])]
            except OSError:pass
        self.info_text.config(state='normal');self.info_text.delete('1.0','end')
        self.info_text.insert('1.0','\n'.join(lines));self.info_text.config(state='disabled')

    def make_options_page(self):
        f=self.pages['Options']
        ttk.Label(f,text='General options',font=('Sans',11,'bold')).pack(anchor='w',pady=(3,10))
        self.option_vars={}
        for key,label,default in [
            ('tips','Tips',True),('remember_last_function','Remember last function',True),
            ('minimize_to_tray','Minimize to Tray (future)',False),
            ('start_minimized','Start minimized (future)',False)]:
            v=tk.BooleanVar(value=self.settings.get(key,default))
            c=ttk.Checkbutton(f,text=label,variable=v,command=lambda k=key,v=v:self.set_option(k,v.get()))
            c.pack(anchor='w',pady=6)
            if key in ('minimize_to_tray','start_minimized'):c.configure(state='disabled')
            self.option_vars[key]=v
        ttk.Separator(f,orient='horizontal').pack(fill='x',pady=18)
        ttk.Label(f,text='History is saved locally in ~/.config/nettalabbo/settings.json').pack(anchor='w')
        ttk.Label(f,text='No automatic network connections or clock changes.').pack(anchor='w',pady=8)
        ttk.Button(f,text='Clear saved host history',command=self.clear_history).pack(anchor='w',pady=8)

    def set_option(self,key,value): self.settings[key]=value;self.persist()

    def clear_history(self):
        self.settings['history']={}
        for key,combo in self.history_boxes.items():combo['values']=[]
        self.persist()

    def make_about_page(self):
        """Local, clickable, complete project notices (no network required)."""
        f = self.pages['About']
        header = ttk.Frame(f)
        header.pack(anchor='center', pady=(0, 10))
        self.about_icon = self.load_image(128)
        if self.about_icon is not None:
            ttk.Label(header, image=self.about_icon).pack(side='left', padx=(0, 18))
        identity = ttk.Frame(header)
        identity.pack(side='left', fill='y')
        ttk.Label(identity, text='Nettalabbo', font=('Sans', 19, 'bold')).pack(anchor='w', pady=(8, 4))
        ttk.Label(identity, text='Network Laboratory app for Xubuntu and other Ubuntu systems',
                  font=('Sans', 10)).pack(anchor='w', pady=(0, 6))
        ttk.Label(identity, text=f'Version {VERSION} (package {PACKAGE_VERSION})  ·  MIT License',
                  font=('Sans', 10)).pack(anchor='w', pady=(0, 6))
        ttk.Label(identity, text='Created by Proxybarrio, with AI-assisted development.',
                  font=('Sans', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        ttk.Separator(f, orient='horizontal').pack(fill='x', padx=30, pady=(0, 12))
        ttk.Label(f, text='Read the full story and legal information',
                  font=('Sans', 12, 'bold')).pack(anchor='center', pady=(0, 5))
        ttk.Label(f, text='Click any topic to open its complete text. All documents work offline.',
                  justify='center').pack(anchor='center', pady=(0, 12))
        for key in ('why', 'credits', 'warning'):
            label = ABOUT_DOCUMENTS[key][0]
            ttk.Button(f, text=label, width=43,
                       command=lambda item=key: self.show_about_document(item)).pack(anchor='center', pady=5)
        ttk.Button(f, text='Read full MIT License', width=43,
                   command=lambda: self.show_about_document('licence')).pack(anchor='center', pady=(5, 13))
        updates = ttk.Frame(f)
        updates.pack(anchor='center', pady=(0, 10))
        ttk.Button(updates, text='Check for updates', width=20,
                   command=lambda: self.check_for_updates(manual=True)).pack(side='left')
        prefs = self.settings.get('updates', {})
        self.update_auto = tk.BooleanVar(value=bool(prefs.get('auto')))
        ttk.Checkbutton(updates, text='Check automatically once a day', variable=self.update_auto,
                        command=self.set_update_auto).pack(side='left', padx=(12, 0))
        self.update_status = tk.StringVar(value='')
        ttk.Label(f, textvariable=self.update_status, foreground='#547086').pack(anchor='center', pady=(0, 8))
        ttk.Separator(f, orient='horizontal').pack(fill='x', padx=30, pady=(0, 11))
        ttk.Label(f, text='TEST RELEASE  •  ACTIVE DEVELOPMENT',
                  font=('Sans', 11, 'bold'), foreground='#975319').pack(anchor='center', pady=(0, 5))
        ttk.Label(f, text='This application contains known and unknown bugs. Use at your own risk.\n'
                          'Only access or test networks where you have permission.\n'
                          'Feedback: proxybar@gmail.com',
                  justify='center').pack(anchor='center', pady=(0, 5))
        # Historic acknowledgement: NetLab95 was developed by Alexander Danileiko.
        # Nettalabbo is not a port or an official continuation of that software.

    # --- Updates from GitHub Releases ---

    def update_prefs(self):
        return self.settings.setdefault('updates', {})

    def set_update_auto(self):
        self.update_prefs()['auto'] = bool(self.update_auto.get())
        self.persist()

    def auto_update_check(self):
        if not updater.running_from_package(__file__):
            return  # source checkout: updates come from git, not from packages
        prefs = self.update_prefs()
        if prefs.get('auto') is None:
            allowed = messagebox.askyesno(
                'Nettalabbo updates',
                'Allow Nettalabbo to check GitHub once a day for a new version?\n\n'
                'Only the GitHub release page is contacted. A new version is downloaded '
                'and verified automatically; it is installed only after you confirm '
                'and enter your password.\n\nYou can change this later in About.',
                parent=self.root)
            prefs['auto'] = allowed
            if hasattr(self, 'update_auto'): self.update_auto.set(allowed)
            self.persist()
        if prefs.get('auto') and time.time() - prefs.get('last_check', 0) > updater.CHECK_INTERVAL:
            self.check_for_updates(manual=False)

    def report_update(self, text, manual):
        if hasattr(self, 'update_status'): self.update_status.set(text)
        self.footer_status.set(text)
        if manual: messagebox.showinfo('Nettalabbo updates', text, parent=self.root)

    def check_for_updates(self, manual=False):
        if self.update_busy:
            if manual: messagebox.showinfo('Nettalabbo updates', 'An update check is already running.', parent=self.root)
            return
        self.update_busy = True
        current = updater.installed_version(PACKAGE_VERSION)
        from_package = updater.running_from_package(__file__)
        skipped = self.update_prefs().get('skipped')
        if hasattr(self, 'update_status'): self.update_status.set('Checking GitHub for updates...')
        def worker():
            try:
                release = updater.check(current)
                self.post(lambda: self.update_prefs().__setitem__('last_check', time.time()))
                if release is None:
                    self.post(self.report_update, f'Nettalabbo {current} is up to date.', manual)
                elif not from_package:
                    self.post(self.report_update, f'Version {release["version"]} is available. This copy runs from '
                              'source: update it with git pull, or install the .deb from GitHub.', manual)
                elif release['version'] == skipped and not manual:
                    self.post(self.report_update, f'Version {release["version"]} skipped at your request.', False)
                else:
                    self.post(self.footer_status.set, f'Downloading Nettalabbo {release["version"]}...')
                    path = updater.download(release)
                    self.post(self.offer_update, release, path)
            except updater.UpdateError as exc:
                self.post(self.report_update, f'Update check: {exc}', manual)
            except Exception as exc:
                self.post(self.report_update, f'Update check failed: {exc}', manual)
            finally:
                self.post(setattr, self, 'update_busy', False)
                self.post(self.persist)
        threading.Thread(target=worker, daemon=True, name='Nettalabbo-update').start()

    def offer_update(self, release, path):
        window = tk.Toplevel(self.root)
        window.title('Nettalabbo update')
        window.transient(self.root)
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=f'Nettalabbo {release["version"]} is ready to install',
                  font=('Sans', 13, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='Downloaded from GitHub and verified (SHA-256 checksum and package data).\n'
                              'Installing asks for your password; Nettalabbo then restarts.',
                  justify='left').pack(anchor='w', pady=(6, 8))
        if release.get('notes'):
            notes = tk.Text(frame, height=10, width=72, wrap='word', relief='flat', background='#f7fbfe')
            notes.insert('1.0', release['notes'])
            notes.configure(state='disabled')
            notes.pack(fill='both', expand=True, pady=(0, 8))
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        def later():
            window.destroy()
        def skip():
            self.update_prefs()['skipped'] = release['version']
            self.persist()
            updater.discard(path)
            window.destroy()
        def install():
            window.destroy()
            self.install_update(release, path)
        ttk.Button(buttons, text='Install now', command=install).pack(side='left')
        ttk.Button(buttons, text='Later', command=later).pack(side='left', padx=7)
        ttk.Button(buttons, text='Skip this version', command=skip).pack(side='left')

    def install_update(self, release, path):
        self.footer_status.set(f'Installing Nettalabbo {release["version"]}...')
        def worker():
            try:
                updater.install(path)
                self.post(self.update_installed, release)
            except (updater.UpdateError, OSError, subprocess.TimeoutExpired) as exc:
                self.post(self.report_update, f'Update not installed: {exc}', True)
        threading.Thread(target=worker, daemon=True, name='Nettalabbo-install').start()

    def update_installed(self, release):
        self.update_prefs().pop('skipped', None)
        self.persist()
        if messagebox.askyesno('Nettalabbo updated',
                               f'Nettalabbo {release["version"]} is installed. Restart now?',
                               parent=self.root):
            self.close()
            script = updater.INSTALL_DIR / 'nettalabbo.py'
            os.execv(sys.executable, [sys.executable, str(script)])
        else:
            self.report_update(f'Nettalabbo {release["version"]} installed; it starts next time.', False)

    def show_about_document(self, key):
        """Display complete offline notices in a read-only, non-selectable viewer."""
        try:
            heading, text = load_about_document(key)
        except (KeyError, OSError) as exc:
            messagebox.showerror('About Nettalabbo', str(exc), parent=self.root)
            return
        window = tk.Toplevel(self.root)
        window.title(f'{heading} — Nettalabbo')
        window.geometry('790x620')
        window.minsize(500, 360)
        window.transient(self.root)
        window.configure(bg='#f7fbfe')
        top = tk.Frame(window, bg='#e3f0f7', padx=16, pady=12)
        top.pack(fill='x')
        tk.Label(top, text=heading, font=('Sans', 15, 'bold'),
                 fg='#174f70', bg='#e3f0f7').pack(anchor='w')
        tk.Label(top, text='Bundled locally with Nettalabbo. Read-only document.',
                 font=('Sans', 9), fg='#45677a', bg='#e3f0f7').pack(anchor='w', pady=(5, 0))
        actions = tk.Frame(window, bg='#f7fbfe', padx=14, pady=11)
        actions.pack(side='bottom', fill='x')
        panel = tk.Frame(window, bg='#f7fbfe', padx=13, pady=13)
        panel.pack(fill='both', expand=True)
        scrollbar = ttk.Scrollbar(panel)
        scrollbar.pack(side='right', fill='y')
        viewer = tk.Text(panel, wrap='word', font=('Sans', 10), spacing1=1, spacing3=7,
                         padx=14, pady=13, undo=False, relief='flat',
                         background='#ffffff', foreground='#253946',
                         yscrollcommand=scrollbar.set)
        viewer.pack(side='left', fill='both', expand=True)
        scrollbar.configure(command=viewer.yview)
        viewer.tag_configure('heading1', font=('Sans', 14, 'bold'),
                             foreground='#125a7a', spacing1=6, spacing3=10)
        viewer.tag_configure('heading2', font=('Sans', 11, 'bold'),
                             foreground='#125a7a', spacing1=8, spacing3=6)
        # Render headings legibly while preserving the full wording of each file.
        for line in text.splitlines(keepends=True):
            if line.startswith('# '):
                viewer.insert('end', line[2:], 'heading1')
            elif line.startswith('## '):
                viewer.insert('end', line[3:], 'heading2')
            else:
                viewer.insert('end', line)
        viewer.configure(state='disabled')
        # Do not install the Text class event bindings in About documents:
        # those would otherwise enable selecting, copying and context-menu
        # shortcuts even on a read-only widget. Keep scroll controls usable.
        viewer.bindtags((str(viewer), str(window), 'all'))
        viewer.bind('<MouseWheel>', lambda e: (viewer.yview_scroll(-int(e.delta / 120), 'units'), 'break')[1])
        viewer.bind('<Button-4>', lambda e: (viewer.yview_scroll(-3, 'units'), 'break')[1])
        viewer.bind('<Button-5>', lambda e: (viewer.yview_scroll(3, 'units'), 'break')[1])
        viewer.bind('<Prior>', lambda e: (viewer.yview_scroll(-1, 'pages'), 'break')[1])
        viewer.bind('<Next>', lambda e: (viewer.yview_scroll(1, 'pages'), 'break')[1])
        viewer.bind('<Up>', lambda e: (viewer.yview_scroll(-1, 'units'), 'break')[1])
        viewer.bind('<Down>', lambda e: (viewer.yview_scroll(1, 'units'), 'break')[1])
        ttk.Button(actions, text='Close', command=window.destroy).pack(side='right')
        window.bind('<Escape>', lambda event: window.destroy())
        viewer.focus_set()
        viewer.see('1.0')

    def show_help(self):
        messagebox.showinfo('Nettalabbo help',
            'Choose a tool from the left navigation rail, or start from the Overview dashboard.\n'
            'Domain Inspector automatically selects the registry RDAP endpoint from IANA.\n'
            'Enter a domain, then press Look up to request public registration data.\n'
            'Press the operation button to start; Cancel interrupts the current task.\n'
            'Right click a Ping, Trace or Scanner result to send an address to another tool.\n'
            'Alternative Networks accepts URLs such as gopher://, gemini://, nntp://, ftp:// and dict://.\n'
            'Click coloured, underlined links. Go/Enter navigates, Back and Forward revisit cached pages.\n'
            'Stop cancels the pending request. Rendered displays links; Raw shows available transport bytes.\n'
            'The directory labels available clients and reference-only protocols. TLS may require explicit certificate approval.\n'
            'Connections has independent SSH and Telnet sessions with embedded terminals.\n'
            'Use SSH for encrypted logins. Telnet is unencrypted and intended for legacy use.\n'
            'Switching work areas does not disconnect a session. Basic terminal emulation only.\n'
            'Terminal: right-click to copy selection; Ctrl+C interrupts the remote process.\n'
            'Output panels: select text and press Ctrl+C, or right-click to copy.\n'
            'Save Output writes a text file for diagnostics. F1 opens this help.\n\n'
            'Only scan networks or hosts that you own or are authorised to assess.\n'
            'Some old services (Finger, Quote, Daytime) may no longer be available.')

    def close(self):
        for session in list(self.remote_sessions.values()):
            if session: session.close()
        for stop,proc in list(self.tasks.values()):
            stop.set()
            if proc and proc.poll() is None:proc.terminate()
        self.persist()
        self.root.destroy()

def main():
    root=tk.Tk()
    App(root)
    root.mainloop()

if __name__=='__main__': main()
