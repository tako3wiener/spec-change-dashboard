import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sdd_dashboard.reader import RepositoryReader, safe_inside, changed_paths

class TestDashboard(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.repo=Path(self.tmp.name)
        subprocess.run(['git','init','-q',str(self.repo)],check=True)
        subprocess.run(['git','-C',str(self.repo),'config','user.email','dev@example.invalid'],check=True)
        subprocess.run(['git','-C',str(self.repo),'config','user.name','Developer'],check=True)
        self.doc=self.repo/'docs/changes/CHG-001';self.doc.mkdir(parents=True)
        (self.doc/'requirements.csv').write_text('req_id,description\nREQ-001,要件A\n',encoding='utf-8')
        (self.doc/'test_cases.csv').write_text('tc_id,req_id,level\nTC-001,REQ-001,E2E\n',encoding='utf-8')
        (self.doc/'change-plan.md').write_text('# DEMO 変更計画\n',encoding='utf-8')
        (self.repo/'src').mkdir()
        (self.repo/'src/App.java').write_text('class App {}\n',encoding='utf-8')
        subprocess.run(['git','-C',str(self.repo),'add','.'],check=True)
        subprocess.run(['git','-C',str(self.repo),'commit','-qm','baseline'],check=True)
        cfg=self.repo/'.claude/local';cfg.mkdir(parents=True)
        (cfg/'project-env.json').write_text(json.dumps({'confirmed_codebase':True,'confirmed_isolated':True,
           'environment':'test','base_url':'http://localhost:8080','artifact_retention_days':90}),encoding='utf-8')
        self.reader=RepositoryReader(self.repo)
    def tearDown(self):self.tmp.cleanup()
    def test_overview_and_estimated_gate(self):
        top=self.reader.overview();self.assertEqual(top['git']['branch'],self.reader.branches()['branch']);
        detail=self.reader.change('CHG-001');self.assertEqual(detail['gate'],'G2')
        self.assertEqual(detail['requirements']['count'],1)
        self.assertEqual(detail['approvals']['G2']['status'],'missing')
    def test_progress_event(self):
        branch=self.reader.branches()['branch']
        path=self.repo/'.claude/local/progress/CHG-001.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'change_id':'CHG-001','gate':'G1','state':'running',
          'next_action':'既存機能を調査','reported_at':'2026-11-24T00:00:00+00:00','branch':branch}),encoding='utf-8')
        d=self.reader.change('CHG-001');self.assertEqual(d['gate'],'G1');self.assertEqual(d['next_action'],'既存機能を調査')
        data=json.loads(path.read_text());data['branch']='another';path.write_text(json.dumps(data))
        d=self.reader.change('CHG-001');self.assertEqual(d['gate'],'G2');self.assertTrue(d['event']['branch_mismatch'])
    def test_diff_and_protected_paths(self):
        (self.repo/'src/App.java').write_text('class App {int x=1;}\n',encoding='utf-8')
        self.assertIn('src/App.java',{x['path'] for x in changed_paths(self.repo)})
        (self.repo/'.claude/local/secret.txt').write_text('secret')
        self.assertNotIn('.claude/local/secret.txt',{x['path'] for x in changed_paths(self.repo)})
    def test_safe_path_and_symlink(self):
        with self.assertRaises(ValueError):safe_inside(self.repo,'../etc/passwd')
        with self.assertRaises(ValueError):safe_inside(self.repo,'/etc/passwd')
        (self.repo/'out').symlink_to(Path(self.tmp.name).parent)
        with self.assertRaises(ValueError):safe_inside(self.repo,'out')
    def test_artifact_access(self):
        f=self.repo/'reports/e2e/CHG-001/RUN-001/TC-001/01-initial.png';f.parent.mkdir(parents=True)
        f.write_bytes(b'\x89PNG\r\n\x1a\n')
        self.assertEqual(self.reader.artifact('e2e','CHG-001','RUN-001','TC-001/01-initial.png'),f)
        with self.assertRaises(ValueError):self.reader.artifact('e2e','CHG-001','RUN-001','../private.json')
    def test_dashboard_disabled_no_core_dependency(self):
        self.assertTrue((self.repo/'docs/changes/CHG-001').exists())
        self.assertEqual(self.reader.event('CHG-001'),None)

if __name__=='__main__':unittest.main()
