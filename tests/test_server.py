import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sdd_dashboard.reader import RepositoryReader
from sdd_dashboard.server import DashboardHandler

class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.repo=Path(cls.tmp.name)
        subprocess.run(['git','init','-q',str(cls.repo)],check=True)
        repo=cls.repo/'docs/changes/CHG-003';repo.mkdir(parents=True)
        (repo/'requirements.csv').write_text('req_id,description\nREQ-003,DEMO requirement\n')
        (repo/'test_cases.csv').write_text('tc_id,req_id\nTC-003,REQ-003\n')
        (repo/'change-plan.md').write_text('## Demo plan\n')
        cfg=cls.repo/'.claude/local';cfg.mkdir(parents=True)
        (cfg/'project-env.json').write_text(json.dumps({'confirmed_codebase':True,'confirmed_isolated':True}))
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),DashboardHandler)
        cls.http.reader=RepositoryReader(cls.repo)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.http.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join(timeout=2);cls.tmp.cleanup()
    def fetch(self,path):
        with urllib.request.urlopen(self.url+path,timeout=5) as r:return r.status,r.headers,r.read()
    def test_page_and_assets(self):
        _,headers,b=self.fetch('/')
        self.assertIn(b'SPECFLOW',b);self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertIn(b'function renderTabs',self.fetch('/app.js')[2])
        self.assertIn(b'createMarkdownViewer',self.fetch('/markdown-viewer.js')[2])
        self.assertIn(b'createDiffViewer',self.fetch('/diff-viewer.js')[2])
    def test_overview_and_details(self):
        body=json.loads(self.fetch('/api/overview')[2]);self.assertEqual(body['changes'][0]['change_id'],'CHG-003')
        body=json.loads(self.fetch('/api/change?id=CHG-003')[2]);self.assertEqual(body['requirements']['count'],1)
    def test_doc_and_approval_draft(self):
        self.assertIn(b'Demo plan',self.fetch('/api/document?id=CHG-003&path=change-plan.md')[2])
        packet=json.loads(self.fetch('/api/approval-materials?id=CHG-003&gate=G2')[2]);self.assertEqual(packet['decision'],'PENDING');self.assertEqual(len(packet['requirements_hash']),64)
    def test_traversal_rejected(self):
        for url in ['/api/document?id=CHG-003&path=..%2F..%2Fsecrets',
                    '/api/artifact?kind=e2e&id=CHG-003&run=RUN-01&path=..%2Fsecret']:
            with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(self.url+url,timeout=5)
            self.assertEqual(cm.exception.code,400)
    def test_host_header_filter(self):
        req=urllib.request.Request(self.url+'/api/overview',headers={'Host':'outside.example'})
        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req,timeout=5)
        self.assertEqual(cm.exception.code,403)

if __name__=='__main__':unittest.main()
