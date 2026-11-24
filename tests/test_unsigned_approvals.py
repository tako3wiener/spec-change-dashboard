import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from sdd_dashboard.reader import approval_info


class UnsignedApprovalTests(unittest.TestCase):
    def test_g2_no_key_and_stale_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            change='CHG-001'
            folder=root/'docs/changes'/change
            folder.mkdir(parents=True)
            local=root/'.claude/local'
            approvals=local/'approvals'
            approvals.mkdir(parents=True)
            files={'requirements_hash':folder/'requirements.csv',
                   'test_cases_hash':folder/'test_cases.csv',
                   'scope_hash':folder/'change-plan.md',
                   'project_config_hash':local/'project-env.json'}
            for p in files.values():p.write_text('fixture',encoding='utf-8')
            record={'change_id':change,'gate':'G2','decision':'APPROVED',
                    'approver':'operator','approved_at':'2026-11-24T07:00:00+09:00'}
            record.update({k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in files.items()})
            doc=approvals/f'{change}-G2.json'
            doc.write_text(json.dumps(record),encoding='utf-8')
            self.assertEqual(approval_info(root,change,'G2',{})['status'],'verified')
            self.assertFalse(doc.with_suffix('.sig').exists())
            files['scope_hash'].write_text('changed',encoding='utf-8')
            self.assertEqual(approval_info(root,change,'G2',{})['status'],'invalid')

    def test_standalone_net_reapproval_on_context_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            local=root/'.claude/local'
            approvals=local/'approvals'
            approvals.mkdir(parents=True)
            config={'execution_context':'local','allowed_origin':'http://localhost:8080'}
            config_file=local/'project-env.json'
            config_file.write_text(json.dumps(config))
            record={'change_id':'CHG-001','gate':'NET','decision':'APPROVED',
                    'approver':'operator','approved_at':'2026-11-24T07:00:00+09:00',
                    'allowed_origin':config['allowed_origin'],'isolation_mode':'container-egress-policy',
                    'dedicated_test_credentials':True,'synthetic_test_data':True,'trace_storage_approved':True,
                    'project_config_hash':hashlib.sha256(config_file.read_bytes()).hexdigest()}
            (approvals/'CHG-001-NET.json').write_text(json.dumps(record))
            self.assertEqual(approval_info(root,'CHG-001','NET',config)['status'],'verified')
            config['execution_context']='devcontainer'
            config_file.write_text(json.dumps(config))
            self.assertEqual(approval_info(root,'CHG-001','NET',config)['status'],'invalid')


if __name__=='__main__':unittest.main()

