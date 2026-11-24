"""Read-only, best-effort v5.1 repository inspection. No imports from the project."""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone

CHANGE_RE = re.compile(r'CHG-[0-9]+\Z')
RUN_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,100}\Z')
SAFE_FILE = re.compile(r'[\w.\- /()+@]+\Z', re.UNICODE)
TEXT_EXT = {'.md', '.txt', '.csv', '.json', '.xml', '.log', '.yaml', '.yml', '.properties'}
ARTIFACT_EXT = TEXT_EXT | {'.png', '.zip', '.pdf'}
MAX_TEXT = 320_000
MAX_DIFF = 500_000
MAX_BINARY = 15_000_000
MAX_FILES = 500


def safe_inside(base: Path, rel: str, *, allow_dir=False) -> Path:
    if not isinstance(rel, str) or not rel or '\\' in rel or '\x00' in rel or any(ord(c)<32 for c in rel):
        raise ValueError('Invalid relative file path')
    path = Path(rel)
    if path.is_absolute() or '..' in path.parts or '.' in path.parts or not SAFE_FILE.fullmatch(rel):
        raise ValueError('Unsafe file path')
    base = Path(base).resolve()
    child = base
    for segment in path.parts:
        child = child / segment
        if child.is_symlink():
            raise ValueError('Symlink path is not permitted')
    result = child.resolve()
    if not result.is_relative_to(base):
        raise ValueError('Path escapes allowed directory')
    if not allow_dir and (not result.is_file() or result.is_symlink()):
        raise FileNotFoundError(rel)
    return result


def read_json(path: Path, default=None):
    try:
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_TEXT:
            return default
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        return default


def file_hash(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str, timeout=6, limit=MAX_DIFF):
    try:
        process = subprocess.run(['git','-C',str(repo),*args], capture_output=True, timeout=timeout,
            env={**os.environ, 'GIT_OPTIONAL_LOCKS':'0', 'GIT_PAGER':'cat', 'GIT_CONFIG_NOSYSTEM':'1'},check=False)
        if process.returncode:
            return ''
        return process.stdout[:limit].decode('utf-8','replace')
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ''


def utc_timestamp(path: Path):
    try: return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec='seconds')
    except OSError: return None


def list_limited_files(base: Path, extensions=TEXT_EXT):
    if not base.is_dir() or base.is_symlink(): return []
    result=[]
    for p in sorted(base.rglob('*')):
        if len(result)>=MAX_FILES: break
        try:
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in extensions and not any(x.is_symlink() for x in p.parents if x!=base):
                resolved=p.resolve()
                if resolved.is_relative_to(base.resolve()):
                    result.append({'path':p.relative_to(base).as_posix(),'name':p.name,
                                   'bytes':p.stat().st_size,'updated_at':utc_timestamp(p)})
        except OSError: continue
    return result


def csv_info(path: Path):
    if not path.is_file() or path.is_symlink(): return {'count':0,'rows':[]}
    try:
        if path.stat().st_size>MAX_TEXT: return {'count':0,'rows':[]}
        with path.open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.DictReader(f))
        return {'count':len(rows),'rows':rows[:160]}
    except (UnicodeError,OSError,csv.Error): return {'count':0,'rows':[]}


def approval_info(repo: Path, change: str, gate: str, config: dict, run: dict|None=None):
    """Check local human approval records without claiming verified identity."""
    doc=repo/'.claude/local/approvals'/f'{change}-{gate}.json'
    if not doc.is_file():
        return {'status':'missing','label':'未提出'}
    if doc.is_symlink():
        return {'status':'invalid','label':'承認ファイル不正'}
    payload=read_json(doc)
    if not isinstance(payload,dict):
        return {'status':'invalid','label':'承認データ不正'}
    if payload.get('change_id')!=change or payload.get('gate')!=gate or payload.get('decision')!='APPROVED' or not isinstance(payload.get('approver'),str) or not payload['approver'].strip() or not payload.get('approved_at'):
        return {'status':'invalid','label':'承認対象が一致しません'}
    try:
        if datetime.fromisoformat(payload['approved_at'].replace('Z','+00:00')).tzinfo is None:
            raise ValueError('missing timezone')
    except (ValueError,TypeError,AttributeError):
        return {'status':'invalid','label':'承認日時不正'}
    expiry=payload.get('expires_at')
    if expiry is not None:
        try:
            dt=datetime.fromisoformat(expiry.replace('Z','+00:00'))
            if not dt.tzinfo or dt<=datetime.now(timezone.utc):raise ValueError('expired')
        except (ValueError,TypeError,AttributeError):return {'status':'invalid','label':'承認期限切れ・不正'}
    if gate=='G2':
        plans={'requirements_hash':repo/'docs/changes'/change/'requirements.csv',
               'test_cases_hash':repo/'docs/changes'/change/'test_cases.csv',
               'scope_hash':repo/'docs/changes'/change/'change-plan.md',
               'project_config_hash':repo/'.claude/local/project-env.json'}
        for key, p in plans.items():
            try:
                if not p.is_file() or p.is_symlink() or file_hash(p)!=payload.get(key):
                    return {'status':'invalid','label':'承認対象が変更されています'}
            except OSError:return {'status':'invalid','label':'承認対象を読めません'}
    if gate=='NET':
        if config.get('execution_context') in ('local','devcontainer'):
            try:
                config_file=repo/'.claude/local/project-env.json'
                if config_file.is_symlink() or file_hash(config_file)!=payload.get('project_config_hash'):
                    return {'status':'invalid','label':'NET実行環境・設定変更：再承認が必要'}
            except OSError:
                return {'status':'invalid','label':'設定ファイルを読めません'}
        if (payload.get('allowed_origin')!=config.get('allowed_origin') or
            payload.get('isolation_mode') not in ('container-egress-policy','network-firewall','dedicated-isolated-host') or
            any(payload.get(k) is not True for k in ('dedicated_test_credentials','synthetic_test_data','trace_storage_approved'))):
            return {'status':'invalid','label':'NET設定不一致'}
    if gate=='G6':
        if not run or run.get('status')!='PASS' or payload.get('run_id')!=run.get('run_id') or payload.get('snapshot_id')!=run.get('snapshot_id'):
            return {'status':'invalid','label':'G6対象実行不一致'}
        summary_file=run.get('_summary_path')
        if config.get('execution_context') in ('local','devcontainer'):
            try:
                config_hash=file_hash(repo/'.claude/local/project-env.json')
                if (run.get('execution_context')!=config['execution_context'] or
                        run.get('project_config_hash')!=config_hash or
                        run.get('summary_config_hash')!=config_hash):
                    return {'status':'invalid','label':'G6実行環境・設定変更：E2E再実行が必要'}
            except OSError:
                return {'status':'invalid','label':'設定ファイルを読めません'}
        if not summary_file or not summary_file.is_file() or file_hash(summary_file)!=payload.get('summary_sha256'):
            return {'status':'invalid','label':'G6成果物ハッシュ不一致'}
    return {'status':'verified','label':'承認記録・対象一致（本人未認証）','approver':str(payload.get('approver'))[:100],
            'approved_at':str(payload.get('approved_at'))[:64]}


def _run_metadata(run_dir:Path, root:Path, kind:str):
    summary=read_json(run_dir/'summary.json',{})
    ctx=read_json(run_dir/'run-context.json',{})
    if not isinstance(summary,dict):summary={}
    if not isinstance(ctx,dict):ctx={}
    status=summary.get('status') if summary.get('status') in ('PASS','FAIL','BLOCKED') else 'UNKNOWN'
    item={'run_id':run_dir.name,'kind':kind,'status':status,'updated_at':utc_timestamp(run_dir/'summary.json') or utc_timestamp(run_dir),
          'phase':summary.get('phase') or ctx.get('phase'),
          'execution_context':ctx.get('execution_context'),
          'project_config_hash':ctx.get('project_config_hash'),
          'summary_config_hash':summary.get('project_config_hash'),
          'snapshot_id':str(summary.get('snapshot_id') or ctx.get('snapshot_id') or '')[:80],
          'branch':ctx.get('git',{}).get('branch') if isinstance(ctx.get('git'),dict) else None,
          'started_at':ctx.get('started_at_utc'),'finished_at':summary.get('finished_at_utc'),
          'counts':summary.get('counts') if isinstance(summary.get('counts'),dict) else {},
          'problems':summary.get('problem') or summary.get('errors') or [],
          'files':list_limited_files(run_dir,ARTIFACT_EXT)}
    if kind=='e2e':
        item['verification'] = read_json(run_dir/'verification.json',{})
        if status=='PASS' and (ctx.get('execution_finished') is not True or not (run_dir/'verification.json').is_file() or
            not isinstance(item['verification'],dict) or item['verification'].get('errors') or item['verification'].get('format_and_crosscheck_passed') is not True):
            item['status']='UNKNOWN'
        tc=[]
        for f in sorted(run_dir.glob('TC-*/manifest.json'))[:160]:
            if f.is_symlink() or f.parent.is_symlink() or not f.parent.name.startswith('TC-'):continue
            meta=read_json(f,{})
            if not isinstance(meta,dict):continue
            shots=[]
            for x in meta.get('screenshots',[]):
                if not isinstance(x,dict):continue
                name=x.get('file','')
                if isinstance(name,str) and re.fullmatch(r'\d{2}-[A-Za-z0-9_-]+\.png',name) and (f.parent/name).is_file():
                    shots.append({'name':name,'path':f'{f.parent.name}/{name}'})
            tc.append({'tc_id':f.parent.name,'result':meta.get('result','UNKNOWN'),
                       'screenshots':shots,'trace':f'{f.parent.name}/trace.zip' if (f.parent/'trace.zip').is_file() else None})
        item['test_cases']=tc
    return item


def _extract_run_dirs(base:Path,change:str,kind:str):
    root=base/change
    if not root.is_dir() or root.is_symlink():return []
    result=[]
    for run in sorted(root.iterdir(),reverse=True):
        if not run.is_dir() or run.is_symlink() or not RUN_RE.fullmatch(run.name):continue
        if kind=='e2e':
            result.append(_run_metadata(run,base,'e2e'))
        else:
            for phase in ('unit','integration'):
                rp=run/phase
                if rp.is_dir() and not rp.is_symlink():result.append(_run_metadata(rp,base,phase) | {'run_id':run.name})
        if len(result)>35:break
    return result


def changed_paths(repo:Path,base_ref='HEAD'):
    raw=git(repo,'diff','--name-only','-z',base_ref,limit=MAX_TEXT)
    paths=set(raw.strip('\x00').split('\x00') if raw else [])
    untracked=git(repo,'ls-files','--others','--exclude-standard','-z',limit=MAX_TEXT)
    untracked_names=set(untracked.strip('\x00').split('\x00') if untracked else [])
    paths.update(untracked_names)
    out=[]
    for path in sorted(paths):
        if not path or not SAFE_FILE.fullmatch(path) or path.startswith('/') or '..' in Path(path).parts:continue
        try:
            # Only show source / docs; never expose local config, test screenshots or credentials.
            if any(part in ('.git','.claude','target','build','node_modules','reports') for part in Path(path).parts):continue
            suffix=Path(path).suffix.lower()
            if suffix not in {'.java','.kt','.py','.js','.jsx','.ts','.tsx','.css','.html','.xml','.md','.yaml','.yml','.json','.sql','.gradle','.groovy'}:continue
            if any(x in Path(path).name.lower() for x in ('secret','credential','.env','private','token','password','key.pem')):continue
            out.append({'path':path,'untracked':path in untracked_names})
        except (OSError,ValueError):continue
        if len(out)>=MAX_FILES:break
    return out


def diff_text(repo:Path, path:str, approved_paths,base_ref='HEAD'):
    if path not in {p['path'] for p in approved_paths}:raise ValueError('File not in current Git change list')
    if any(part in ('.git','.claude','reports','target','build','node_modules') for part in Path(path).parts):raise ValueError('Protected path')
    if path in {p['path'] for p in approved_paths if p['untracked']}:
        p=safe_inside(repo,path)
        if p.stat().st_size>MAX_DIFF:return 'ファイルが大きいためプレビュー対象外です。'
        try:return '\n'.join('+'+line for line in p.read_text(encoding='utf-8').splitlines()[:2200])
        except UnicodeDecodeError:return 'バイナリファイルは表示できません。'
    return git(repo,'diff','--no-ext-diff','--no-textconv',base_ref,'--',path,limit=MAX_DIFF)


class RepositoryReader:
    def __init__(self,repo:Path,state_dir:Path|None=None,base_ref:str|None=None):
        self.repo=Path(repo).resolve(strict=True)
        self.state_dir=Path(state_dir).resolve() if state_dir else self.repo/'.claude/local/progress'
        self.config_path=self.repo/'.claude/local/project-env.json'

        self.base_ref='HEAD'
        if base_ref:
            if not re.fullmatch(r'[A-Za-z0-9._/\-]+',base_ref) or base_ref.startswith('-') or '..' in base_ref:
                raise ValueError('Invalid base ref')
            if not git(self.repo,'rev-parse','--verify',base_ref):raise ValueError('Base ref does not exist')
            self.base_ref=git(self.repo,'merge-base','HEAD',base_ref).strip() or 'HEAD'
        else:
            for candidate in ('origin/main','main','origin/master','master'):
                if candidate==git(self.repo,'branch','--show-current').strip():continue
                if git(self.repo,'rev-parse','--verify',candidate):
                    self.base_ref=git(self.repo,'merge-base','HEAD',candidate).strip() or 'HEAD'
                    break

    def config(self):
        data=read_json(self.config_path,{})
        return data if isinstance(data,dict) else {}

    def roots(self):
        cfg=self.config()
        roots={}
        for kind, setting, fallback in [('unit','unit_integration_results_dir','reports/test-results'),
                                       ('e2e','e2e_evidence_dir','reports/e2e')]:
            try:
                path=safe_inside(self.repo,cfg.get(setting,fallback),allow_dir=True)
                if not path.is_relative_to(self.repo):raise ValueError('outside')
            except (ValueError,FileNotFoundError,OSError):path=self.repo/'__disabled__'
            roots[kind]=path
        return roots

    def branches(self):
        return {'branch':git(self.repo,'branch','--show-current').strip() or '不明',
                'commit':git(self.repo,'rev-parse','--short','HEAD').strip() or '不明'}

    def change_ids(self):
        ids=set()
        bases=[self.repo/'docs/changes',*self.roots().values()]
        for base in bases:
            if base.is_dir() and not base.is_symlink():
                for item in base.iterdir():
                    if item.is_dir() and not item.is_symlink() and CHANGE_RE.fullmatch(item.name):ids.add(item.name)
        if self.state_dir:
            folder=self.state_dir
            if folder.is_dir():
                for f in folder.glob('CHG-*.json'):
                    if CHANGE_RE.fullmatch(f.stem):ids.add(f.stem)
        return sorted(ids, key=lambda x:int(x[4:]), reverse=True)[:100]

    def event(self,change:str):
        if not self.state_dir:return None
        path=self.state_dir/f'{change}.json'
        data=read_json(path)
        if not isinstance(data,dict) or data.get('change_id')!=change or data.get('gate') not in [f'G{i}' for i in range(7)]:return None
        if data.get('state') not in ('running','waiting','blocked','done'):return None
        return {'gate':data['gate'],'state':data['state'],'next':str(data.get('next_action',data.get('next','')))[:500],
                'note':str(data.get('note',''))[:1000], 'branch':str(data.get('branch',''))[:160],
                'commit':str(data.get('commit',''))[:64],
                'reported_at':data.get('reported_at'),'source':'optional-unverified-event'}

    def history(self, change: str):
        """Read recent reported events; not a verified audit log."""
        if not CHANGE_RE.fullmatch(change):return []
        file=self.state_dir/f'{change}.jsonl'
        try:
            if file.is_symlink() or not file.is_file() or file.stat().st_size>750_000:return []
            events=[]
            for line in file.read_text(encoding='utf-8').splitlines()[-40:]:
                try: entry=json.loads(line)
                except (ValueError,TypeError):continue
                if (not isinstance(entry,dict) or entry.get('change_id')!=change or
                    entry.get('gate') not in {f'G{i}' for i in range(7)} or
                    entry.get('state') not in ('running','waiting','blocked','done')):continue
                events.append({'gate':entry['gate'],'state':entry['state'],
                               'next':str(entry.get('next_action',''))[:260],
                               'reported_at':entry.get('reported_at'),
                               'branch':str(entry.get('branch',''))[:160]})
            return list(reversed(events))
        except (OSError,UnicodeError):return []

    def overview(self):
        changes=self.change_ids()
        b=self.branches()
        cfg=self.config()
        return {'name':self.repo.name,'repository_root':str(self.repo),'git':b,
                'environment':cfg.get('environment','未設定'),'base_url':cfg.get('base_url',''),
                'unit_results_dir':str(self.roots()['unit'].relative_to(self.repo)),
                'e2e_evidence_dir':str(self.roots()['e2e'].relative_to(self.repo)),
                'retention_days':cfg.get('artifact_retention_days',90), 'diff_base':self.base_ref,
                'changes':[self._change_summary(x) for x in changes],
                'read_only':True,'notice':'画面のゲートはファイルからの推定です。承認はローカル記録と対象の整合確認です。承認者本人の認証は行いません。'}

    def _change_summary(self,change:str):
        d=self.change(change,details=False)
        return {k:d[k] for k in ('change_id','gate','gate_label','next_action','last_updated','e2e_status','event')}

    def change(self,change:str,details=True):
        if not CHANGE_RE.fullmatch(change):raise ValueError('Invalid change ID')
        if change not in self.change_ids():raise FileNotFoundError(change)
        base=self.repo/'docs/changes'/change
        cfg=self.config()
        docs=list_limited_files(base)
        # Also surface read-only spec index for source review.
        spec=list_limited_files(self.repo/'docs/spec',TEXT_EXT|{'.pdf'})[:120]
        req=csv_info(base/'requirements.csv')
        tc=csv_info(base/'test_cases.csv')
        roots=self.roots()
        e2e_runs=_extract_run_dirs(roots['e2e'],change,'e2e')
        java_runs=_extract_run_dirs(roots['unit'],change,'unit')
        e2e_runs.sort(key=lambda r:r.get('updated_at') or '',reverse=True)
        java_runs.sort(key=lambda r:r.get('updated_at') or '',reverse=True)
        latest=e2e_runs[0] if e2e_runs else None
        ap2=approval_info(self.repo,change,'G2',cfg)
        apnet=approval_info(self.repo,change,'NET',cfg)
        # G6 checks only latest PASS, for review we show its status without claiming core G6 execution.
        latest_path=roots['e2e']/change/latest['run_id']/'summary.json' if latest else None
        g6_run=dict(latest or {},_summary_path=latest_path) if latest else None
        ap6=approval_info(self.repo,change,'G6',cfg,run=g6_run)
        document_names={d['path'] for d in docs}
        have_plan={'requirements.csv','test_cases.csv','change-plan.md'}.issubset(document_names)
        have_config=bool(cfg.get('confirmed_codebase') and cfg.get('confirmed_isolated'))
        unit_latest=next((r for r in java_runs if r['kind']=='unit'),None)
        int_latest=next((r for r in java_runs if r['kind']=='integration'),None)
        int_required=bool(cfg.get('integration_test_argv'))
        java_pass=bool(unit_latest and unit_latest['status']=='PASS' and (not int_required or int_latest and int_latest['status']=='PASS'))
        e2e_pass=bool(latest and latest['status']=='PASS')
        stale_e2e=False
        if e2e_pass and cfg.get('execution_context') in ('local','devcontainer'):
            try:
                current_hash=file_hash(self.config_path)
                stale_e2e=(latest.get('execution_context')!=cfg['execution_context'] or
                           latest.get('project_config_hash')!=current_hash or
                           latest.get('summary_config_hash')!=current_hash)
            except OSError:
                stale_e2e=True
            e2e_pass=not stale_e2e
        review_exists=any(p in document_names for p in ('review.md','independent-review.md','final-report.md'))
        gates=[{'id':f'G{i}','title':name,'status':'pending','detail':''} for i,name in enumerate(
            ['初期設定','仕様・影響調査','変更設計承認','実装・Javaテスト','Playwright E2E','独立レビュー','最終承認'])]
        gates[0]['status']='observed' if have_config else 'pending'
        gates[0]['detail']='設定内容あり・検査コマンド未実行' if have_config else 'project-setup未設定'
        gates[1]['status']='observed' if have_plan else 'pending'
        gates[1]['detail']='REQ・TC・変更計画あり' if have_plan else '資料作成中・未完成'
        gates[2]['status']='verified' if ap2['status']=='verified' else 'pending'
        gates[2]['detail']=ap2['label']
        gates[3]['status']='observed' if java_pass else 'pending'
        gates[3]['detail']='今回とは限らないローカルJUnit PASS' if java_pass else ('JUnit結果未完了' if java_runs else 'JUnit結果なし')
        gates[4]['status']='observed' if e2e_pass else 'pending'
        gates[4]['detail']='ローカル検証PASS（独立証明なし）' if e2e_pass else ('実行環境・設定変更：E2E再実行が必要' if stale_e2e else (latest['status'] if latest else 'E2E実行結果なし'))
        gates[5]['status']='observed' if review_exists else 'pending'
        gates[5]['detail']='レビュー資料あり（内容未検証）' if review_exists else 'レビュー記録なし'
        gates[6]['status']='verified' if ap6['status']=='verified' else 'pending'
        gates[6]['detail']=ap6['label']
        if not have_config:
            gate='G0';action='対象リポジトリで /project-setup を完了し、設定検証を実行する'
        elif not have_plan:
            gate='G1';action='仕様・影響調査と requirements.csv / test_cases.csv / change-plan.md を揃える'
        elif ap2['status']!='verified':
            gate='G2';action='変更設計・TC・既存影響を確認し、別ターミナルでG2承認を記録する'
        elif not java_pass:
            gate='G3';action='Javaを実装し、承認済み仕様に対する単体・結合テストを実行する'
        elif apnet['status']!='verified':
            gate='G4';action='実ネットワーク隔離を確認し、別ターミナルでNET承認を記録する'
        elif not e2e_pass:
            gate='G4';action='Playwright正式E2Eを実行して証跡を確認する'
        elif not review_exists:
            gate='G5';action='独立レビューで仕様・差分・JUnit・E2E証跡を照合する'
        elif ap6['status']!='verified':
            gate='G6';action='成果物と残課題を確認し、別ターミナルでG6受入承認を記録する'
        else:
            gate='DONE';action='受入承認記録確認済み。マージ・デプロイは既存手順で別途判断する'
        for g in gates:
            if g['id']==gate:g['status']='current' if g['status']=='pending' else g['status']
        event=self.event(change)
        # A progress event is an unverified status report, NEVER G2/G6 approval or PASS.
        # Branch mismatch makes the event stale for the current checkout.
        if event and event.get('branch') == self.branches()['branch']:
            gate=event['gate']
            action=event.get('next') or action
            for g in gates:
                if g['id']==gate and g['status']!='verified':
                    g['status']='reported-'+event['state']
                    g['detail']='進捗申告（品質・承認証明ではありません）'
        elif event:
            event['branch_mismatch']=True
        dates=[d.get('updated_at') for d in docs if d.get('updated_at')]
        dates += [r.get('updated_at') for r in e2e_runs+java_runs if r.get('updated_at')]
        result={'change_id':change,'gate':gate,'gate_label':('進捗申告（非承認）' if event and not event.get('branch_mismatch') else '成果物から推定') if gate!='DONE' else '承認記録確認済み・ローカル推定',
                'next_action':action,'last_updated':max(dates) if dates else None,
                'e2e_status': latest['status'] if latest else '未実行',
                'event':event,'activity':self.history(change) if details else [],'gates':gates,'approvals':{'G2':ap2,'NET':apnet,'G6':ap6},
                'requirements':{'count':req['count'],'rows':req['rows'] if details else []},
                'test_cases':{'count':tc['count'],'rows':tc['rows'] if details else []},
                'documents':docs if details else [], 'source_documents':spec if details else [],
                'e2e_runs':e2e_runs[:12] if details else [],
                'java_runs':java_runs[:12] if details else [],
                'code_changes':changed_paths(self.repo,self.base_ref) if details else [],
                'git':self.branches(),'diff_base':self.base_ref,
                'warnings':['表示された差分はベース参照からのブランチ変更と作業ツリーの変更を含みます。特定CHG専用とは断定できません。',
                    'G0/G1/G3/G4/G5は成果物からの推定・ローカル観測で、正式な品質ゲート通過証明ではありません。']}
        if event and event.get('branch_mismatch'):
            result['warnings'].append('進捗記録は別ブランチのものです。現ブランチには適用していません。')
        if latest and latest.get('branch') and latest['branch']!=result['git']['branch']:
            result['warnings'].append(f"最新E2Eはブランチ {latest['branch']} で実行されました。現在のブランチと異なります。")
        return result

    def document(self,change:str, path:str,source=False):
        if not CHANGE_RE.fullmatch(change):raise ValueError('Invalid change ID')
        base=self.repo/('docs/spec' if source else f'docs/changes/{change}')
        file=safe_inside(base,path)
        if file.suffix.lower() not in TEXT_EXT|{'.pdf'}:raise ValueError('Unsupported document type')
        if file.stat().st_size>MAX_TEXT and file.suffix.lower()!='.pdf':raise ValueError('Document exceeds preview size')
        return file

    def artifact(self,kind:str,change:str,run:str,path:str):
        if kind not in ('e2e','unit') or not CHANGE_RE.fullmatch(change) or not RUN_RE.fullmatch(run):raise ValueError('Invalid artifact identity')
        file=safe_inside(self.roots()[kind]/change/run,path)
        if file.suffix.lower() not in ARTIFACT_EXT or file.stat().st_size>MAX_BINARY:raise ValueError('Artifact unavailable or too large')
        return file
