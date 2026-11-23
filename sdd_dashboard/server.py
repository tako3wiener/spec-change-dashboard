"""Zero-dependency, loopback-only, read-only dashboard HTTP service."""
from __future__ import annotations
import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .reader import RepositoryReader, file_hash, read_json, diff_text

WEB=Path(__file__).parent/'static'
ALLOWED_HOSTS={'127.0.0.1','localhost','[::1]'}

class DashboardHandler(BaseHTTPRequestHandler):
    server_version='SDDDashboard/1.0'
    def log_message(self, fmt, *args):
        # Never log paths containing sensitive filenames or query parameters.
        return

    def _headers(self, code, content_type, length):
        self.send_response(code)
        for name,value in [('Content-Type',content_type),('Content-Length',str(length)),
                           ('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),
                           ('Referrer-Policy','no-referrer'),('X-Frame-Options','DENY'),
                           ('Cross-Origin-Resource-Policy','same-origin'),
                           ('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")]:
            self.send_header(name,value)
        self.end_headers()

    def _send(self, value, code=200, content_type='application/json; charset=utf-8'):
        data=json.dumps(value,ensure_ascii=False).encode('utf-8') if content_type.startswith('application/json') else value
        self._headers(code,content_type,len(data));self.wfile.write(data)

    def _params(self):
        parsed=urlsplit(self.path)
        qs=parse_qs(parsed.query,keep_blank_values=True,strict_parsing=False)
        def one(name,default=None):
            vals=qs.get(name,[])
            if len(vals)>1:raise ValueError('Duplicate parameter: '+name)
            return vals[0] if vals else default
        return parsed.path,one

    def do_GET(self):
        try:
            # Do not serve a localhost dashboard through DNS rebinding aliases.
            host=self.headers.get('Host','').split(':',1)[0]
            if host not in ('127.0.0.1','localhost','[::1]'):
                self._send({'error':'Unsupported Host'},403);return
            path,get=self._params()
            if path in ('/','/index.html','/style.css','/app.js','/markdown-viewer.js','/diff-viewer.js'):
                name=path.lstrip('/') or 'index.html'
                file=WEB/name
                content_type={'index.html':'text/html; charset=utf-8','style.css':'text/css; charset=utf-8','app.js':'application/javascript; charset=utf-8', 'markdown-viewer.js':'application/javascript; charset=utf-8', 'diff-viewer.js':'application/javascript; charset=utf-8'}[name]
                self._send(file.read_bytes(),content_type=content_type);return
            reader:RepositoryReader=self.server.reader
            if path=='/api/overview':result=reader.overview()
            elif path=='/api/change':result=reader.change(get('id',''))
            elif path=='/api/document':
                file=reader.document(get('id',''),get('path',''),source=get('source')=='1')
                self._send_file(file, allow_pdf=True);return
            elif path=='/api/diff':
                f=get('path','');result={'path':f,'diff':diff_text(reader.repo,f,reader.change(get('id',''))['code_changes'],reader.base_ref)}
            elif path=='/api/artifact':
                file=reader.artifact(get('kind',''),get('id',''),get('run',''),get('path',''))
                self._send_file(file);return
            elif path=='/api/approval-materials':
                result=self._approval_materials(reader,get('id',''),get('gate','G2'))
            else:self._send({'error':'Not found'},404);return
            self._send(result)
        except (ValueError,FileNotFoundError,PermissionError,KeyError) as exc:
            self._send({'error':str(exc)[:180]},400)
        except (OSError, UnicodeError) as exc:
            self._send({'error':'Read failed'},500)
        except Exception:
            # Keep internal paths and stack traces out of browser responses.
            self._send({'error':'Internal dashboard error'},500)

    def _send_file(self, file:Path, allow_pdf=False):
        suffix=file.suffix.lower()
        kinds={'.png':'image/png','.pdf':'application/pdf','.zip':'application/zip',
               '.json':'text/plain; charset=utf-8','.xml':'text/plain; charset=utf-8',
               '.csv':'text/plain; charset=utf-8','.md':'text/plain; charset=utf-8',
               '.txt':'text/plain; charset=utf-8','.log':'text/plain; charset=utf-8',
               '.yaml':'text/plain; charset=utf-8','.yml':'text/plain; charset=utf-8',
               '.properties':'text/plain; charset=utf-8'}
        if suffix not in kinds:raise ValueError('Unsupported artifact type')
        if suffix=='.pdf' and not allow_pdf:raise ValueError('PDF artifacts are not previewed')
        if file.stat().st_size>(15_000_000 if suffix in ('.png','.zip','.pdf') else 320_000):
            raise ValueError('File too large for local dashboard')
        content=file.read_bytes();self._send(content,content_type=kinds[suffix])

    def _approval_materials(self,reader,change,gate):
        if gate not in ('G2','G6'):raise ValueError('Only G2 and G6 are supported')
        detail=reader.change(change)
        packet={'change_id':change,'gate':gate,'decision':'PENDING','warning':'Review draft only. NOT an approval. External human signing remains mandatory.'}
        if gate=='G2':
            base=reader.repo/'docs/changes'/change
            sources={'requirements_hash':base/'requirements.csv',
                     'test_cases_hash':base/'test_cases.csv',
                     'scope_hash':base/'change-plan.md',
                     'project_config_hash':reader.repo/'.claude/local/project-env.json'}
            for key,file in sources.items():
                if not file.is_file() or file.is_symlink():raise ValueError('Missing G2 source: '+key)
                packet[key]=file_hash(file)
        else:
            runs=detail['e2e_runs']
            latest=runs[0] if runs else None
            if not latest or latest['status']!='PASS':raise ValueError('A passing E2E run is required for G6 review')
            base=reader.roots()['e2e']/change/latest['run_id']
            ctx=read_json(base/'run-context.json',{})
            if not ctx or ctx.get('execution_finished') is not True:raise ValueError('Incomplete run context')
            packet.update({'run_id':latest['run_id'],'snapshot_id':latest['snapshot_id'],
                           'summary_sha256':file_hash(base/'summary.json')})
        return packet

def main(argv=None):
    parser=argparse.ArgumentParser(description='Read-only local dashboard for Claude Code /spec-change')
    parser.add_argument('--repo',type=Path,required=True,help='Existing Java Git repository with v5.1/v5.2 artifacts')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--base-ref',help='Optional comparison branch such as main/origin/main. Defaults to auto-detection or HEAD.')
    args=parser.parse_args(argv)
    if args.host not in ('127.0.0.1','localhost'):
        parser.error('Only loopback binding is supported; use an authenticated reverse proxy for remote access (not bundled)')
    repo=args.repo.expanduser().resolve(strict=True)
    if not (repo/'.git').exists() and not (repo/'.git').is_file():
        parser.error('Selected path is not a Git repository root')
    server=ThreadingHTTPServer((args.host,args.port),DashboardHandler)
    server.reader=RepositoryReader(repo,base_ref=args.base_ref)
    print(f'SDD Dashboard: http://{args.host}:{server.server_port}  (read-only, local)')
    print(f'Repository: {repo}')
    try:server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':main()
