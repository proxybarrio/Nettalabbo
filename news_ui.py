"""Newsgroups page: a three-pane Usenet reader and poster.

Groups on the left, threads on the top right, the message below, in the
tradition of the Netscape and SeaMonkey news readers. Network work runs in
background threads; every widget is touched only from the Tk thread.
"""

import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import nntp_client
from nntp_client import NNTPError

PAGE = 'Newsgroups'
MAX_GROUP_ROWS = 3000
READ_MEMORY = 3000          # remembered read messages per group
ARTICLE_CACHE = 200
FONT = 'DejaVu Sans Mono'


class NewsPage:
    def __init__(self, app, frame, user_agent='Nettalabbo'):
        self.app = app
        self.frame = frame
        self.user_agent = user_agent
        self.groups = []                 # (name, first, last, status)
        self.groups_server = None
        self.group = None                # open group name
        self.group_first = None          # first article number on the server
        self.loaded_first = None         # oldest article number loaded
        self.records = {}                # number -> overview record
        self.article = None              # parsed article shown
        self.article_number = None
        self.article_cache = {}
        self.article_generation = 0
        self.session_passwords = {}
        self.plaintext_accepted = set()
        self.compose_window = None
        settings = app.settings
        settings.setdefault('news_accounts', {})
        settings.setdefault('news_custom_servers', [])
        settings.setdefault('news_subscribed', {})
        settings.setdefault('news_read', {})
        self.build()

    # -- settings ---------------------------------------------------------
    def servers(self):
        result = []
        for name, host, port, tls, account, note in nntp_client.PUBLIC_SERVERS:
            result.append({'name': name, 'host': host, 'port': port, 'tls': tls,
                           'account': account, 'note': note, 'custom': False})
        for item in self.app.settings.get('news_custom_servers', []):
            if isinstance(item, dict) and item.get('name') and item.get('host'):
                result.append({'name': item['name'], 'host': item['host'],
                               'port': int(item.get('port') or 119), 'tls': bool(item.get('tls')),
                               'account': 'optional', 'note': 'A server you added.', 'custom': True})
        accounts = self.app.settings.get('news_accounts', {})
        for server in result:
            account = accounts.get(server['name'], {})
            if not server['custom'] and account.get('port'):
                server['port'] = int(account['port'])
                server['tls'] = bool(account.get('tls'))
        return result

    def server(self, name=None):
        name = name or self.server_var.get()
        for item in self.servers():
            if item['name'] == name:
                return item
        return self.servers()[0]

    def account(self, name=None):
        return self.app.settings['news_accounts'].get(name or self.server()['name'], {})

    def subscribed(self, name=None):
        return set(self.app.settings['news_subscribed'].get(name or self.server()['name'], []))

    def read_set(self, server, group):
        return set(self.app.settings['news_read'].get(server, {}).get(group, []))

    def mark_read(self, server, group, number):
        groups = self.app.settings['news_read'].setdefault(server, {})
        numbers = groups.setdefault(group, [])
        if number not in numbers:
            numbers.append(number)
            del numbers[:-READ_MEMORY]
            self.app.persist()

    # -- layout -----------------------------------------------------------
    def build(self):
        f = self.frame
        top = ttk.Frame(f)
        top.pack(fill='x')
        ttk.Label(top, text='Server:').pack(side='left', padx=(0, 6))
        names = [s['name'] for s in self.servers()]
        chosen = self.app.settings.get('news_server')
        self.server_var = tk.StringVar(value=chosen if chosen in names else names[0])
        self.server_box = ttk.Combobox(top, textvariable=self.server_var, values=names,
                                       state='readonly', width=34)
        self.server_box.pack(side='left')
        self.server_box.bind('<<ComboboxSelected>>', lambda e: self.server_changed())
        ttk.Button(top, text='Get groups', command=self.load_groups).pack(side='left', padx=(7, 0))
        ttk.Button(top, text='Account…', command=lambda: self.server_dialog(self.server())
                   ).pack(side='left', padx=(7, 0))
        ttk.Button(top, text='Add server…', command=lambda: self.server_dialog(None)
                   ).pack(side='left', padx=(7, 0))
        ttk.Button(top, text='Cancel', command=lambda: self.app.cancel(PAGE)).pack(side='left', padx=(7, 0))
        self.server_info = tk.StringVar()
        ttk.Label(f, textvariable=self.server_info, foreground='#547086', wraplength=820,
                  justify='left').pack(anchor='w', pady=(5, 0))
        self.app.status[PAGE] = tk.StringVar(value='Choose a server and press Get groups.')
        ttk.Label(f, textvariable=self.app.status[PAGE]).pack(anchor='w', pady=(2, 4))

        panes = ttk.PanedWindow(f, orient='horizontal')
        panes.pack(fill='both', expand=True)

        def first_layout(event):
            panes.unbind('<Map>')
            panes.after_idle(lambda: panes.sashpos(0, 290))
        panes.bind('<Map>', first_layout)
        left = ttk.Frame(panes)
        panes.add(left, weight=1)
        search_row = ttk.Frame(left)
        search_row.pack(fill='x')
        ttk.Label(search_row, text='Find:').pack(side='left')
        self.search_var = tk.StringVar()
        search = ttk.Entry(search_row, textvariable=self.search_var, width=16)
        search.pack(side='left', fill='x', expand=True, padx=(4, 0))
        self.search_var.trace_add('write', lambda *a: self.show_groups())
        self.only_subscribed = tk.BooleanVar(value=False)
        ttk.Checkbutton(left, text='Subscribed only', variable=self.only_subscribed,
                        command=self.show_groups).pack(anchor='w', pady=(3, 2))
        box = ttk.Frame(left)
        box.pack(fill='both', expand=True)
        self.group_tree = ttk.Treeview(box, columns=('count',), selectmode='browse', height=12)
        self.group_tree.heading('#0', text='Group')
        self.group_tree.heading('count', text='Msgs')
        self.group_tree.column('#0', width=190, stretch=True)
        self.group_tree.column('count', width=60, anchor='e', stretch=False)
        bar = ttk.Scrollbar(box, orient='vertical', command=self.group_tree.yview)
        self.group_tree.configure(yscrollcommand=bar.set)
        self.group_tree.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        self.group_tree.bind('<Double-1>', lambda e: self.open_selected_group())
        self.group_tree.bind('<Return>', lambda e: self.open_selected_group())
        buttons = ttk.Frame(left)
        buttons.pack(fill='x', pady=(3, 0))
        ttk.Button(buttons, text='Open', command=self.open_selected_group).pack(side='left')
        ttk.Button(buttons, text='★ Subscribe', command=self.toggle_subscription).pack(side='left', padx=4)

        right = ttk.PanedWindow(panes, orient='vertical')
        panes.add(right, weight=3)
        upper = ttk.Frame(right)
        right.add(upper, weight=2)
        tools = ttk.Frame(upper)
        tools.pack(fill='x')
        self.group_title = tk.StringVar(value='No group open')
        ttk.Label(tools, textvariable=self.group_title, font=('Sans', 10, 'bold')).pack(side='left')
        for text, command in (('Reply', self.reply), ('New message', self.new_message),
                              ('Older', lambda: self.open_group(self.group, older=True)),
                              ('Refresh', lambda: self.open_group(self.group))):
            ttk.Button(tools, text=text, command=command).pack(side='right', padx=(4, 0))
        box = ttk.Frame(upper)
        box.pack(fill='both', expand=True, pady=(3, 0))
        self.message_tree = ttk.Treeview(box, columns=('from', 'date', 'lines'),
                                         selectmode='browse', height=8)
        for column, title, width, stretch in (('#0', 'Subject', 240, True), ('from', 'From', 130, False),
                                              ('date', 'Date', 132, False), ('lines', 'Lines', 48, False)):
            self.message_tree.heading(column, text=title)
            self.message_tree.column(column, width=width, stretch=stretch,
                                     anchor='e' if column == 'lines' else 'w')
        self.message_tree.tag_configure('unread', font=('Sans', 10, 'bold'))
        bar = ttk.Scrollbar(box, orient='vertical', command=self.message_tree.yview)
        self.message_tree.configure(yscrollcommand=bar.set)
        self.message_tree.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        self.message_tree.bind('<<TreeviewSelect>>', lambda e: self.message_selected())

        lower = ttk.Frame(right)
        right.add(lower, weight=3)
        tools = ttk.Frame(lower)
        tools.pack(fill='x', pady=(4, 2))
        self.all_headers = tk.BooleanVar(value=False)
        ttk.Checkbutton(tools, text='All headers', variable=self.all_headers,
                        command=self.show_article).pack(side='left')
        ttk.Button(tools, text='Save…', command=self.save_article).pack(side='right')
        box = ttk.Frame(lower)
        box.pack(fill='both', expand=True)
        bar = ttk.Scrollbar(box, orient='vertical')
        self.text = tk.Text(box, wrap='word', font=(FONT, 11), relief='sunken', bd=2, height=10,
                            state='disabled', background='white', yscrollcommand=bar.set,
                            padx=6, pady=4)
        bar.configure(command=self.text.yview)
        self.text.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        self.text.tag_configure('header_name', foreground='#4a6b80')
        self.text.tag_configure('header_value', font=(FONT, 11, 'bold'))
        self.text.tag_configure('quote1', foreground='#2f6f9f')
        self.text.tag_configure('quote2', foreground='#7a5a9a')
        self.text.tag_configure('signature', foreground='#888888')
        self.text.tag_configure('note', foreground='#8a5a00')
        for sequence in ('<Control-c>', '<Control-C>'):
            self.text.bind(sequence, lambda e: self.app.copy_selection_text(self.text))
        self.text.bind('<Control-a>', lambda e: self.app.select_all_text(self.text))
        self.text.bind('<Button-3>', lambda e: self.app.text_context_menu(e, self.text))
        self.server_changed(first=True)

    # -- small UI helpers -------------------------------------------------
    def set_text(self, chunks):
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        for value, tags in chunks:
            self.text.insert('end', value, tags)
        self.text.configure(state='disabled')
        self.text.yview_moveto(0)

    def status(self, message):
        self.app.set_status(PAGE, message)

    def server_changed(self, first=False):
        server = self.server()
        account = self.account(server['name'])
        if not first:
            self.app.settings['news_server'] = server['name']
            self.app.persist()
        login = account.get('username')
        parts = ['{}:{}{}'.format(server['host'], server['port'], ' TLS' if server['tls'] else ''),
                 server['note'],
                 'Logged in as {}.'.format(login) if login else
                 'Anonymous ({}).'.format(nntp_client.ACCOUNT_NOTES[server['account']])]
        if login and not server['tls']:
            parts.append('Warning: the password travels unencrypted.')
        self.server_info.set('   '.join(parts))
        if self.groups_server != server['name']:
            self.groups = []
            self.groups_server = None
            self.show_groups()
            self.group = None
            self.records = {}
            self.message_tree.delete(*self.message_tree.get_children())
            self.group_title.set('No group open')
            self.set_text([('Press Get groups to list the newsgroups of {}.\n'.format(server['name']), 'note')])
            if self.subscribed(server['name']):
                self.only_subscribed.set(True)
                self.show_groups()

    def show_groups(self):
        tree = self.group_tree
        tree.delete(*tree.get_children())
        name = self.server_var.get()
        subscribed = self.subscribed(name)
        query = self.search_var.get().strip().lower()
        known = {g[0]: g for g in self.groups} if self.groups_server == name else {}
        rows = [g for g in known.values() if g[0] in subscribed]
        rows += [(g, 0, -1, '') for g in sorted(subscribed) if g not in known]
        if not self.only_subscribed.get():
            rows += [g for g in self.groups if g[0] not in subscribed] if known else []
        shown = 0
        for group in rows:
            if query and query not in group[0].lower():
                continue
            if shown >= MAX_GROUP_ROWS:
                tree.insert('', 'end', iid='__more__', text='… more groups: type in Find to narrow the list')
                break
            count = max(0, group[2] - group[1] + 1) if group[2] >= group[1] else ''
            star = '★ ' if group[0] in subscribed else ''
            tree.insert('', 'end', iid='g:' + group[0], text=star + group[0], values=(count,))
            shown += 1

    def selected_group(self):
        selection = self.group_tree.selection()
        if selection and selection[0].startswith('g:'):
            return selection[0][2:]
        return None

    def toggle_subscription(self):
        group = self.selected_group()
        if not group:
            return
        name = self.server()['name']
        groups = self.app.settings['news_subscribed'].setdefault(name, [])
        if group in groups:
            groups.remove(group)
        else:
            groups.append(group)
            groups.sort()
        self.app.persist()
        self.show_groups()
        if self.group_tree.exists('g:' + group):
            self.group_tree.selection_set('g:' + group)
            self.group_tree.see('g:' + group)

    # -- connection settings (main thread) --------------------------------
    def connection(self, server=None):
        """Parameters for nntp_client.Connection, asking for a password if needed."""
        server = server or self.server()
        account = self.account(server['name'])
        username = account.get('username', '')
        password = account.get('password') or self.session_passwords.get(server['name'], '')
        if username and not password:
            password = simpledialog.askstring('Nettalabbo', 'Password for {} on {}:'.format(
                username, server['name']), show='*', parent=self.frame)
            if password is None:
                return None
            self.session_passwords[server['name']] = password
        if username and not server['tls'] and server['name'] not in self.plaintext_accepted:
            if not messagebox.askyesno('Nettalabbo', 'The connection to {} is not encrypted, so your '
                                       'password can be read on the network.\n\nUse TLS (port 563) in '
                                       'Account… if the server offers it.\n\nContinue anyway?'.format(
                                           server['host']), parent=self.frame):
                return None
            self.plaintext_accepted.add(server['name'])
        return {'host': server['host'], 'port': server['port'], 'tls': server['tls'],
                'username': username, 'password': password}

    def run(self, describe, job):
        """Run job(connection) in the background; errors appear in the status line."""
        server = self.server()
        params = self.connection(server)
        if params is None:
            return
        app = self.app

        def worker(stop):
            app.post(self.status, '{} on {}…'.format(describe, server['name']))
            try:
                with nntp_client.Connection(stop=stop, **params) as nntp:
                    job(nntp, server['name'])
            except nntp_client.Cancelled:
                pass
            except NNTPError as error:
                app.task_outcomes[PAGE] = 'Error: {}'.format(error)
                if error.code == 481:
                    self.session_passwords.pop(server['name'], None)
        app.start(PAGE, worker)

    # -- groups -----------------------------------------------------------
    def load_groups(self):
        def job(nntp, server_name):
            groups, truncated = nntp.list_groups()
            self.app.post(self.groups_loaded, server_name, groups, truncated, nntp.posting_allowed)
            self.app.task_outcomes[PAGE] = '{} groups{}. Double-click a group to read it.'.format(
                len(groups), ' (list cut: too long)' if truncated else '')
        self.run('Reading the group list', job)

    def groups_loaded(self, server_name, groups, truncated, posting):
        if server_name != self.server_var.get():
            return
        self.groups = groups
        self.groups_server = server_name
        if not self.subscribed(server_name):
            self.only_subscribed.set(False)
        self.show_groups()
        self.set_text([('{} groups on {}. Posting {}.\n\nFind narrows the list; ★ Subscribe keeps a group '
                        'at the top and in Subscribed only.\n'.format(
                            len(groups), server_name, 'allowed' if posting else
                            'not offered without an account'), 'note')])

    def open_selected_group(self):
        group = self.selected_group()
        if group:
            self.open_group(group)

    def open_group(self, group, older=False):
        if not group:
            return
        if older and (self.loaded_first is None or self.group_first is None
                      or self.loaded_first <= self.group_first):
            self.status('No older messages on the server.')
            return
        until = self.loaded_first - 1 if older else None

        def job(nntp, server_name):
            count, first, last = nntp.group(group)
            end = until if until is not None else last
            start = max(first, end - nntp_client.DEFAULT_BATCH + 1)
            records = nntp.overview(start, end) if last >= first and end >= start else []
            self.app.post(self.messages_loaded, server_name, group, first, start, records, older)
            self.app.task_outcomes[PAGE] = '{}: {} {}messages loaded, about {} on the server.'.format(
                group, len(records), 'older ' if older else '', count)
        self.run('Opening ' + group, job)

    def messages_loaded(self, server_name, group, first, start, records, older):
        if server_name != self.server_var.get():
            return
        if not older or group != self.group:
            self.records = {}
            self.article_cache = {}
        self.group = group
        self.group_first = first
        self.loaded_first = start
        for record in records:
            self.records[record['number']] = record
        self.group_title.set(group)
        self.fill_messages(server_name)
        if not older:
            self.set_text([('{}\n\n'.format(group), 'header_value'),
                           ('Select a message to read it. Bold messages are unread; Older loads '
                            'earlier messages, Refresh checks for new ones.\n'
                            if self.records else 'No messages in this group.\n', 'note')])

    def fill_messages(self, server_name):
        tree = self.message_tree
        tree.delete(*tree.get_children())
        read = self.read_set(server_name, self.group)
        ids = {}
        for parent_id, record in nntp_client.build_threads(list(self.records.values())):
            item = str(record['number'])
            parent = ids.get(parent_id, '')
            tree.insert(parent, 'end', iid=item, text=record['subject'],
                        values=(record['from'], nntp_client.short_date(record['date']), record['lines']),
                        open=True, tags=() if record['number'] in read else ('unread',))
            if record['message_id']:
                ids[record['message_id']] = item

    # -- reading ----------------------------------------------------------
    def message_selected(self):
        selection = self.message_tree.selection()
        if not selection or not self.group:
            return
        number = int(selection[0])
        server_name = self.server()['name']
        group = self.group
        self.article_number = number
        self.mark_read(server_name, group, number)
        self.message_tree.item(selection[0], tags=())
        if number in self.article_cache:
            self.article = self.article_cache[number]
            self.show_article()
            return
        params = self.connection()
        if params is None:
            return
        self.article_generation += 1
        generation = self.article_generation
        self.set_text([('Loading message…\n', 'note')])

        def fetch():
            try:
                with nntp_client.Connection(**params) as nntp:
                    nntp.group(group)
                    raw, truncated = nntp.article(number)
                result = nntp_client.parse_article(raw, truncated)
            except NNTPError as error:
                result = error
            self.app.post(self.article_loaded, generation, number, result)
        threading.Thread(target=fetch, daemon=True, name='Nettalabbo-news-article').start()

    def article_loaded(self, generation, number, result):
        if generation != self.article_generation:
            return
        if isinstance(result, Exception):
            self.article = None
            self.set_text([('Cannot read this message: {}\n'.format(result), 'note')])
            return
        if len(self.article_cache) >= ARTICLE_CACHE:
            self.article_cache.pop(next(iter(self.article_cache)))
        self.article_cache[number] = result
        self.article = result
        self.show_article()

    def show_article(self):
        article = self.article
        if not article:
            return
        chunks = []
        if self.all_headers.get():
            head = article['raw'].split(b'\r\n\r\n', 1)[0].decode('utf-8', 'replace')
            chunks.append((head.replace('\r\n', '\n') + '\n\n', 'header_name'))
        else:
            for key in ('Subject', 'From', 'Date', 'Newsgroups', 'Followup-To'):
                if key in article['headers']:
                    chunks.append(('{}: '.format(key), 'header_name'))
                    chunks.append((article['headers'][key] + '\n', 'header_value'))
            chunks.append(('\n', ()))
        signature = False
        for line in article['body'].split('\n'):
            if line == '-- ':
                signature = True
            if signature:
                tag = 'signature'
            elif line.startswith(('>>', '> >')):
                tag = 'quote2'
            elif line.startswith('>'):
                tag = 'quote1'
            else:
                tag = ()
            chunks.append((line + '\n', tag))
        if article['attachments']:
            chunks.append(('\nAttachments not downloaded: {}\n'.format(', '.join(article['attachments'])), 'note'))
        if article['truncated']:
            chunks.append(('\nThis message is very long and is shown only in part.\n', 'note'))
        self.set_text(chunks)

    def save_article(self):
        article = self.article
        if not article:
            return
        subject = article['headers'].get('Subject', 'message')
        safe = ''.join(c if c.isalnum() or c in ' -_' else '_' for c in subject)[:60].strip() or 'message'
        path = filedialog.asksaveasfilename(parent=self.frame, initialfile=safe + '.txt',
                                            defaultextension='.txt',
                                            filetypes=[('Text', '*.txt'), ('Original message', '*.eml')])
        if not path:
            return
        try:
            if path.lower().endswith('.eml'):
                with open(path, 'wb') as stream:
                    stream.write(article['raw'])
            else:
                with open(path, 'w', encoding='utf-8') as stream:
                    stream.write(self.text.get('1.0', 'end-1c'))
            self.status('Saved {}'.format(path))
        except OSError as error:
            messagebox.showerror('Nettalabbo', 'Cannot save: {}'.format(error), parent=self.frame)

    # -- writing ----------------------------------------------------------
    def new_message(self):
        self.compose(self.group or '', '', '', ())

    def reply(self):
        article = self.article
        if not article:
            messagebox.showinfo('Nettalabbo', 'Select the message you want to answer first.', parent=self.frame)
            return
        headers = article['headers']
        groups = headers.get('Followup-To') or headers.get('Newsgroups') or self.group or ''
        if groups.strip().lower() == 'poster':
            messagebox.showinfo('Nettalabbo', 'The author asked for answers by e-mail, not in the group.',
                                parent=self.frame)
            groups = self.group or ''
        references = headers.get('References', '').split()
        if headers.get('Message-ID'):
            references.append(headers['Message-ID'])
        self.compose(groups, nntp_client.reply_subject(headers.get('Subject', '')),
                     nntp_client.quote_body(article), references)

    def compose(self, groups, subject, body, references):
        if self.compose_window is not None and self.compose_window.winfo_exists():
            if not messagebox.askyesno('Nettalabbo', 'Discard the message you are writing?', parent=self.frame):
                self.compose_window.lift()
                return
            self.compose_window.destroy()
        server = self.server()
        account = self.account(server['name'])
        window = tk.Toplevel(self.frame)
        self.compose_window = window
        window.title('New message | Nettalabbo')
        window.transient(self.frame.winfo_toplevel())
        window.geometry('720x560')
        grid = ttk.Frame(window, padding=10)
        grid.pack(fill='both', expand=True)
        grid.columnconfigure(1, weight=1)
        fields = {}
        values = (('From', account.get('sender') or self.app.settings.get('news_sender', '')),
                  ('Newsgroups', groups), ('Subject', subject))
        for row, (label, value) in enumerate(values):
            ttk.Label(grid, text=label + ':').grid(row=row, column=0, sticky='w', pady=2)
            var = tk.StringVar(value=value)
            ttk.Entry(grid, textvariable=var).grid(row=row, column=1, sticky='ew', pady=2)
            fields[label] = var
        ttk.Label(grid, text='Sent to {} {}. Usenet messages are public and usually cannot be deleted.'.format(
            server['name'], 'as ' + account['username'] if account.get('username') else 'without an account'),
            foreground='#547086').grid(row=3, column=0, columnspan=2, sticky='w', pady=(4, 4))
        box = ttk.Frame(grid)
        box.grid(row=4, column=0, columnspan=2, sticky='nsew')
        grid.rowconfigure(4, weight=1)
        bar = ttk.Scrollbar(box, orient='vertical')
        editor = tk.Text(box, wrap='word', font=(FONT, 11), undo=True, yscrollcommand=bar.set)
        bar.configure(command=editor.yview)
        editor.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        editor.insert('1.0', body)
        editor.mark_set('insert', 'end')
        buttons = ttk.Frame(grid)
        buttons.grid(row=5, column=0, columnspan=2, sticky='e', pady=(8, 0))
        ttk.Button(buttons, text='Cancel', command=window.destroy).pack(side='right')
        send = ttk.Button(buttons, text='Send', command=lambda: self.send(
            window, fields, editor, references, send))
        send.pack(side='right', padx=(0, 6))
        (editor if fields['From'].get() and groups and subject else window).focus_set()

    def send(self, window, fields, editor, references, button):
        server = self.server()
        try:
            article = nntp_client.build_article(fields['From'].get(), fields['Newsgroups'].get(),
                                                fields['Subject'].get(), editor.get('1.0', 'end-1c'),
                                                references, self.user_agent)
        except NNTPError as error:
            messagebox.showerror('Nettalabbo', str(error), parent=window)
            return
        groups = fields['Newsgroups'].get().strip()
        if not messagebox.askyesno('Nettalabbo', 'Send this message to {} on {}?\n\nIt will be public.'.format(
                groups, server['name']), parent=window):
            return
        params = self.connection(server)
        if params is None:
            return
        if PAGE in self.app.tasks:
            messagebox.showinfo('Nettalabbo', 'Wait for the current operation to finish, or press Cancel.',
                                parent=window)
            return
        sender = fields['From'].get().strip()
        button.configure(state='disabled')
        app = self.app

        def worker(stop):
            app.post(self.status, 'Sending to {}…'.format(server['name']))
            try:
                with nntp_client.Connection(stop=stop, **params) as nntp:
                    answer = nntp.post(article)
                app.task_outcomes[PAGE] = 'Message sent. The server said: {}'.format(answer)
                app.post(self.sent, window, server['name'], sender)
            except nntp_client.Cancelled:
                app.post(button.configure, state='normal')
            except NNTPError as error:
                app.task_outcomes[PAGE] = 'Not sent: {}'.format(error)
                app.post(self.send_failed, window, button, str(error))
        app.start(PAGE, worker)

    def sent(self, window, server_name, sender):
        self.app.settings['news_sender'] = sender
        self.app.settings['news_accounts'].setdefault(server_name, {})['sender'] = sender
        self.app.persist()
        if window.winfo_exists():
            window.destroy()

    def send_failed(self, window, button, message):
        if window.winfo_exists():
            button.configure(state='normal')
            messagebox.showerror('Nettalabbo', 'The message was not sent.\n\n' + message, parent=window)

    # -- servers and accounts ---------------------------------------------
    def server_dialog(self, server):
        new = server is None
        custom = new or server['custom']
        account = {} if new else dict(self.account(server['name']))
        window = tk.Toplevel(self.frame)
        window.title(('Add news server' if new else server['name']) + ' | Nettalabbo')
        window.transient(self.frame.winfo_toplevel())
        grid = ttk.Frame(window, padding=12)
        grid.pack(fill='both', expand=True)
        grid.columnconfigure(1, weight=1)
        v = {
            'name': tk.StringVar(value='' if new else server['name']),
            'host': tk.StringVar(value='' if new else server['host']),
            'port': tk.StringVar(value='119' if new else str(server['port'])),
            'tls': tk.BooleanVar(value=False if new else server['tls']),
            'login': tk.BooleanVar(value=bool(account.get('username'))),
            'username': tk.StringVar(value=account.get('username', '')),
            'password': tk.StringVar(value=account.get('password', '')),
            'remember': tk.BooleanVar(value=bool(account.get('password'))),
            'sender': tk.StringVar(value=account.get('sender', self.app.settings.get('news_sender', ''))),
        }
        row = 0

        def line(label, widget):
            nonlocal row
            ttk.Label(grid, text=label).grid(row=row, column=0, sticky='w', pady=3, padx=(0, 8))
            widget.grid(row=row, column=1, sticky='ew', pady=3)
            row += 1
            return widget

        state = 'normal' if custom else 'readonly'
        line('Name:', ttk.Entry(grid, textvariable=v['name'], width=40, state=state))
        line('Server:', ttk.Entry(grid, textvariable=v['host'], state=state))
        port_row = ttk.Frame(grid)
        ttk.Entry(port_row, textvariable=v['port'], width=7).pack(side='left')
        ttk.Checkbutton(port_row, text='Encrypted (TLS)', variable=v['tls'],
                        command=lambda: v['port'].set('563' if v['tls'].get() else '119')).pack(side='left', padx=10)
        line('Port:', port_row)
        ttk.Separator(grid).grid(row=row, column=0, columnspan=2, sticky='ew', pady=8)
        row += 1
        ttk.Radiobutton(grid, text='Anonymous', value=False, variable=v['login']).grid(
            row=row, column=0, columnspan=2, sticky='w')
        row += 1
        ttk.Radiobutton(grid, text='With an account (user name and password)', value=True,
                        variable=v['login']).grid(row=row, column=0, columnspan=2, sticky='w')
        row += 1
        user = line('User name:', ttk.Entry(grid, textvariable=v['username']))
        password = line('Password:', ttk.Entry(grid, textvariable=v['password'], show='*'))
        remember = ttk.Checkbutton(grid, text='Remember the password on this computer '
                                   '(stored in your private Nettalabbo settings)', variable=v['remember'])
        remember.grid(row=row, column=0, columnspan=2, sticky='w')
        row += 1
        warning = tk.StringVar()
        ttk.Label(grid, textvariable=warning, foreground='#9a3412', wraplength=430).grid(
            row=row, column=0, columnspan=2, sticky='w')
        row += 1

        def refresh(*_):
            enabled = 'normal' if v['login'].get() else 'disabled'
            for widget in (user, password, remember):
                widget.configure(state=enabled)
            warning.set('Without TLS the password is sent unencrypted.'
                        if v['login'].get() and not v['tls'].get() else '')
        for key in ('login', 'tls'):
            v[key].trace_add('write', refresh)
        refresh()
        ttk.Separator(grid).grid(row=row, column=0, columnspan=2, sticky='ew', pady=8)
        row += 1
        line('Post as:', ttk.Entry(grid, textvariable=v['sender']))
        ttk.Label(grid, text='Name and address shown on your messages, for example  Ada <ada@example.org>. '
                  'They are public: use an address you are happy to show.', foreground='#547086',
                  wraplength=430).grid(row=row, column=0, columnspan=2, sticky='w')
        row += 1
        if not new and not custom:
            ttk.Label(grid, text=server['note'], foreground='#547086', wraplength=430).grid(
                row=row, column=0, columnspan=2, sticky='w', pady=(6, 0))
            row += 1
        buttons = ttk.Frame(grid)
        buttons.grid(row=row, column=0, columnspan=2, sticky='e', pady=(12, 0))
        ttk.Button(buttons, text='Cancel', command=window.destroy).pack(side='right')
        ttk.Button(buttons, text='Save', command=lambda: self.save_server(window, server, v)).pack(
            side='right', padx=(0, 6))
        if not new and custom:
            ttk.Button(buttons, text='Remove server', command=lambda: self.remove_server(window, server)).pack(
                side='left')

    def save_server(self, window, server, v):
        settings = self.app.settings
        new = server is None
        name = ' '.join(v['name'].get().split())
        host = v['host'].get().strip()
        try:
            port = int(v['port'].get())
            if not 0 < port < 65536:
                raise ValueError
        except ValueError:
            messagebox.showerror('Nettalabbo', 'The port must be a number from 1 to 65535.', parent=window)
            return
        login = v['login'].get()
        username = v['username'].get().strip() if login else ''
        if login and (not username or any(c.isspace() for c in username)):
            messagebox.showerror('Nettalabbo', 'Enter a user name without spaces.', parent=window)
            return
        if new or server['custom']:
            if not name or not host or any(c.isspace() for c in host):
                messagebox.showerror('Nettalabbo', 'Enter a name and a server address.', parent=window)
                return
            others = [s['name'] for s in self.servers() if new or s['name'] != server['name']]
            if name in others:
                messagebox.showerror('Nettalabbo', 'A server with this name already exists.', parent=window)
                return
            entries = [e for e in settings['news_custom_servers']
                       if new or e.get('name') != server['name']]
            entries.append({'name': name, 'host': host, 'port': port, 'tls': v['tls'].get()})
            settings['news_custom_servers'] = entries
            if not new and name != server['name']:
                for key in ('news_accounts', 'news_subscribed', 'news_read'):
                    if server['name'] in settings[key]:
                        settings[key][name] = settings[key].pop(server['name'])
        else:
            name = server['name']
        account = {'sender': v['sender'].get().strip()}
        if not (new or server['custom']):
            account.update({'port': port, 'tls': v['tls'].get()})
        if username != self.account(name).get('username', '') or not username:
            self.session_passwords.pop(name, None)
        if username:
            account['username'] = username
            if v['remember'].get() and v['password'].get():
                account['password'] = v['password'].get()
            elif v['password'].get():
                self.session_passwords[name] = v['password'].get()
        self.plaintext_accepted.discard(name)
        settings['news_accounts'][name] = account
        self.app.persist()
        window.destroy()
        self.server_box.configure(values=[s['name'] for s in self.servers()])
        self.server_var.set(name)
        self.groups_server = None if new else self.groups_server
        self.server_changed()

    def remove_server(self, window, server):
        if not messagebox.askyesno('Nettalabbo', 'Remove {} and its account settings?'.format(server['name']),
                                   parent=window):
            return
        settings = self.app.settings
        settings['news_custom_servers'] = [e for e in settings['news_custom_servers']
                                           if e.get('name') != server['name']]
        for key in ('news_accounts', 'news_subscribed', 'news_read'):
            settings[key].pop(server['name'], None)
        self.session_passwords.pop(server['name'], None)
        self.app.persist()
        window.destroy()
        names = [s['name'] for s in self.servers()]
        self.server_box.configure(values=names)
        self.server_var.set(names[0])
        self.server_changed()
