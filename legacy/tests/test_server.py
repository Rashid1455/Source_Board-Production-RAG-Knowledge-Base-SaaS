import base64
import http.cookiejar
import json
import uuid
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
import server


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        test_root = server.ROOT / 'data' / 'tests'
        test_root.mkdir(parents=True, exist_ok=True)
        self.previous_db = server.DB
        server.DB = test_root / (uuid.uuid4().hex + '.db')
        self.test_db = server.DB
        server.init_db()
        self.http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.http.server_port}/api/'
        self.client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()
        server.DB = self.previous_db
        self.test_db.unlink(missing_ok=True)

    def request(self, path, body=None, client=None):
        req = urllib.request.Request(self.url+path, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Content-Type':'application/json'})
        try:
            with (client or self.client).open(req) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def register(self, email='test@example.com'):
        status, _ = self.request('register', {'email':email,'password':'long-password-123','workspace':'Test team'})
        self.assertEqual(status,200)

    def upload(self):
        content = b'Remote work policy: Employees may work remotely three days per week. Manager approval is required.'
        status, doc = self.request('upload',{'name':'policy.txt','content':base64.b64encode(content).decode()})
        self.assertEqual(status,201)
        return doc

    def test_evidence_abstention_history_and_deletion(self):
        self.register()
        doc = self.upload()
        status, answer = self.request('ask',{'question':'What is the remote work policy?'})
        self.assertEqual(status,200)
        self.assertEqual(answer['status'],'evidence_found')
        self.assertIn('three days',answer['sources'][0]['text'])
        self.assertEqual(answer['sources'][0]['page'],1)
        _, missing = self.request('ask',{'question':'What is the annual revenue?'})
        self.assertEqual(missing['status'],'insufficient_evidence')
        self.assertEqual(missing['sources'],[])
        self.assertEqual(len(self.request('history')[1]),2)
        self.request('delete',{'id':doc['id']})
        self.assertEqual(self.request('documents')[1],[])
        self.assertEqual(self.request('history')[1],[])
        self.assertEqual(self.request('ask',{'question':'remote work policy'})[1]['sources'],[])

    def test_workspace_isolation_and_unauthenticated_access(self):
        status, _ = self.request('documents')
        self.assertEqual(status,401)
        self.register()
        doc=self.upload()
        first_client=self.client
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.register('other@example.com')
        self.assertEqual(self.request('documents')[1],[])
        self.assertEqual(self.request('ask',{'question':'remote work policy'})[1]['sources'],[])
        self.request('delete',{'id':doc['id']})
        self.assertEqual(len(self.request('documents',client=first_client)[1]),1)

    def test_upload_validation_and_login(self):
        self.register()
        self.assertEqual(self.request('upload',{'name':'bad.exe','content':'dGVzdA=='})[0],400)
        self.assertEqual(self.request('upload',{'name':'empty.txt','content':''})[0],400)
        self.request('logout',{})
        self.assertEqual(self.request('me')[0],401)
        self.assertEqual(self.request('login',{'email':'test@example.com','password':'wrong-password'})[0],401)
        self.assertEqual(self.request('login',{'email':'test@example.com','password':'long-password-123'})[0],200)
        self.assertEqual(self.request('me')[1]['workspace'],'Test team')

    def test_pdf_extraction(self):
        try:
            from pypdf import PdfWriter
        except ImportError:
            self.skipTest('Install requirements to test PDF parsing')
        from pypdf.generic import DecodedStreamObject, NameObject, DictionaryObject
        import io
        writer=PdfWriter()
        page=writer.add_blank_page(width=612,height=792)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject()
        stream.set_data(b'BT /F1 12 Tf 72 720 Td (Remote work policy: three days per week.) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        output=io.BytesIO()
        writer.write(output)
        self.assertIn('three days',server.extract('policy.pdf',output.getvalue())[0])

if __name__ == '__main__':
    unittest.main()
