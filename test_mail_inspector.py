"""Offline single-address mail tests: no DNS or third-party SMTP connections."""
import socket
import threading
import unittest
from unittest.mock import patch
import mail_inspector as mail


class MailTests(unittest.TestCase):
    def test_address_normalisation(self):
        addr, domain = mail.normalise_email('Example+newsletter@Exämple.IT ')
        self.assertEqual(addr, 'Example+newsletter@xn--exmple-cua.it')
        self.assertEqual(domain, 'xn--exmple-cua.it')
        for value in ('bob@example.org\r\nRCPT TO:<victim@t>', 'a@b',
                      'person@example..com', 'a,b@example.com', 'bob@evil domain.com'):
            with self.assertRaises(mail.MailInspectionError, msg=value):
                mail.normalise_email(value)

    def test_routing_without_probe(self):
        with patch.object(mail, 'find_mx', return_value=[(10, 'mail.test')]):
            with patch.object(mail, 'smtp_recipient_probe') as smtp:
                r=mail.inspect_address('alex@example.org')
        self.assertEqual(r.verdict, 'Mail-routing host found; mailbox unknown')
        self.assertIn('does not establish mailbox existence', r.text())
        smtp.assert_not_called()

    def test_null_mx(self):
        with patch.object(mail, 'find_mx', return_value=[(0, '.')]):
            r=mail.inspect_address('nobody@example.org', True)
        self.assertIn('Null MX', r.verdict)

    def test_mx_and_smtp_cautious(self):
        with patch.object(mail, 'find_mx', return_value=[(5, 'mail.example.org')]):
            with patch.object(mail, 'smtp_recipient_probe', return_value=(250, 'Ok', 'No delivery')) as mock:
                r=mail.inspect_address('person@example.org', True)
                mock.assert_called_once_with('mail.example.org', 'person@example.org')
        self.assertIn('not verified', r.verdict)
        self.assertNotIn('exists', r.verdict.lower())
        self.assertIn('No DATA command', r.text())
        self.assertIn('not conclusive', mail.classify_smtp(550))
        self.assertIn('indeterminate', mail.classify_smtp(451))

    def test_mx_parse(self):
        with patch.object(mail, 'dig_records',return_value=['20 alt.example.', '10 mx.example.', '0 .']):
            self.assertEqual(mail.find_mx('example.org')[0],(0,'.'))

    def test_smtp_wire_never_sends_data(self):
        listener = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        listener.bind(('127.0.0.1',0))
        listener.listen(1)
        port=listener.getsockname()[1]
        requests=[]
        def serve():
            with listener:
                conn,_=listener.accept()
                with conn:
                    conn.settimeout(3)
                    conn.sendall(b'220 mail.test ESMTP\r\n')
                    pending=b''
                    while True:
                        packet=conn.recv(4096)
                        if not packet:break
                        pending+=packet
                        while b'\r\n' in pending:
                            line,pending=pending.split(b'\r\n',1)
                            requests.append(line)
                            cmd=line.upper()
                            if cmd.startswith(b'EHLO'):
                                conn.sendall(b'250-mail.test\r\n250 OK\r\n')
                            elif cmd.startswith(b'MAIL FROM') or cmd.startswith(b'RCPT TO'):
                                conn.sendall(b'250 OK\r\n')
                            elif cmd==b'QUIT':
                                conn.sendall(b'221 Bye\r\n')
                                return
                            else:conn.sendall(b'500 unknown\r\n')
        t=threading.Thread(target=serve,daemon=True)
        t.start()
        code,reply,_=mail.smtp_recipient_probe('127.0.0.1','real@example.org',port)
        t.join(3)
        self.assertEqual(code,250)
        self.assertTrue(any(x.upper().startswith(b'RCPT TO') for x in requests))
        self.assertFalse(any(x.upper().startswith(b'DATA') for x in requests))
        self.assertFalse(any(x.upper().startswith(b'VRFY') for x in requests))

    def test_pop3_plain_greeting(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        port=listener.getsockname()[1]
        def handler():
            with listener:
                s,_=listener.accept()
                with s:s.sendall(b'+OK POP3 ready\r\n')
        t=threading.Thread(target=handler,daemon=True);t.start()
        output=mail.test_mail_service('POP3','127.0.0.1',port)
        t.join(2)
        self.assertIn('POP3 ready',output)
        self.assertIn('No login credentials',output)

if __name__ == '__main__':unittest.main()
