"""Optional Chromium UI regression tests. Runtime dashboard needs no browser test deps."""
import json
import os
from pathlib import Path
import shutil
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'sdd_dashboard' / 'static'
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

CHROMIUM = next((p for p in ['/usr/bin/chromium', '/usr/bin/google-chrome'] if Path(p).is_file()), None)

@unittest.skipUnless(sync_playwright and CHROMIUM, 'Playwright and local Chromium are optional test dependencies')
class ViewerBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch(headless=True, executable_path=CHROMIUM, args=['--no-sandbox', '--disable-dev-shm-usage'])

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={'width': 1280, 'height': 850})
        self.errors = []
        self.page.on('pageerror', lambda err: self.errors.append(str(err)))
        self.page.set_content('<!doctype html><html><head></head><body><div id="root"></div></body></html>')
        self.page.add_script_tag(path=ROOT / 'markdown-viewer.js')
        self.page.add_script_tag(path=ROOT / 'diff-viewer.js')

    def tearDown(self):
        self.assertEqual(self.errors, [])
        self.page.close()

    def test_markdown_render_and_unsafe_html(self):
        source = ('# 仕様・調査結果\n\n## 対象\n\n**重要**、*斜体*、`コード`、~~削除~~\n\n'
                  '| ID | 結果 |\n| --- | --- |\n| REQ-01 | PASS |\n\n'
                  '- [x] 影響調査\n- [ ] 回帰\n\n> 注意事項\n\n'
                  '```java\nint x = 1;\n```\n\n'
                  '<img src=x onerror="window.__attacked=1">\n\n'
                  '[危険](javascript:alert(1)) [安全](https://example.com)')
        self.page.evaluate('(source) => document.querySelector("#root").append(createMarkdownViewer(source))', source)
        self.assertEqual(self.page.locator('.markdown-body h1').inner_text(), '仕様・調査結果')
        self.assertEqual(self.page.locator('.markdown-body table tbody tr').count(), 1)
        self.assertEqual(self.page.locator('.markdown-body input:checked').count(), 1)
        self.assertEqual(self.page.locator('.markdown-body blockquote').count(), 1)
        self.assertEqual(self.page.locator('.markdown-body pre code').inner_text(), 'int x = 1;')
        self.assertEqual(self.page.locator('.markdown-body img').count(), 0)
        self.assertEqual(self.page.locator('.markdown-body [onerror]').count(), 0)
        self.assertEqual(self.page.locator('.markdown-body a').count(), 1)
        self.assertIn('<img', self.page.locator('.markdown-body').inner_text())
        self.assertFalse(self.page.evaluate('Boolean(window.__attacked)'))

    def test_diff_unified_and_split(self):
        data = ('diff --git a/Login.java b/Login.java\nindex abc..def 100644\n'
                '--- a/Login.java\n+++ b/Login.java\n@@ -12,3 +12,4 @@\n old\n-before\n+after\n+new\n context\n')
        self.page.evaluate('(data)=>document.querySelector("#root").append(createDiffViewer(data))', data)
        self.assertEqual(self.page.locator('.diff-add').count(), 2)
        self.assertEqual(self.page.locator('.diff-del').count(), 1)
        self.assertIn('+2', self.page.locator('.diff-counts').inner_text())
        self.assertEqual(self.page.locator('.diff-row.diff-add .diff-ln').first.inner_text(), '')
        self.page.get_by_role('button', name='左右比較').click()
        self.assertGreater(self.page.locator('.diff-pair').count(), 1)
        self.assertEqual(self.page.locator('.diff-pair .diff-side.diff-del').count(), 1)
        self.assertEqual(self.page.locator('.diff-pair .diff-side.diff-add').count(), 2)
        self.page.get_by_role('button', name='統合表示').click()
        self.assertEqual(self.page.locator('.diff-row.diff-add').count(), 2)

    def test_diff_untracked_file_and_safe_text(self):
        self.page.evaluate('()=>document.querySelector("#root").append(createDiffViewer("+<img onerror=alert(1)>\\n+new file\\n"))')
        self.assertEqual(self.page.locator('.diff-add').count(), 2)
        self.assertEqual(self.page.locator('.diff-viewer img').count(), 0)
        self.assertIn('<img', self.page.locator('.diff-content').inner_text())

    def test_app_integration_markdown_and_diff_modal(self):
        self.page.close()
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 900})
        self.page.on('pageerror', lambda err:self.errors.append(str(err)))
        markup = (ROOT/'index.html').read_text(encoding='utf-8').replace('<link rel="stylesheet" href="/style.css">','').replace('<script src="/markdown-viewer.js" defer></script><script src="/diff-viewer.js" defer></script><script src="/app.js" defer></script>', '')
        self.page.set_content(markup)
        self.page.add_style_tag(content=(ROOT/'style.css').read_text(encoding='utf-8'))
        overview={'name':'demo-project','repository_root':'/demo','git':{'branch':'feature/CHG-001','commit':'d2f3a45'},'environment':'test','changes':[{'change_id':'CHG-001','gate':'G1'}]}
        detail={'change_id':'CHG-001','gate':'G1','gate_label':'仕様解析中','next_action':'変更設計の確認','last_updated':'2026-11-24T00:00:00Z',
                'git':overview['git'],'event':None,'e2e_status':'UNKNOWN',
                'gates':[],'requirements':{'count':1,'rows':[]},'test_cases':{'count':1},'java_runs':[],'e2e_runs':[],
                'documents':[{'path':'change-plan.md','bytes':123,'updated_at':None}], 'source_documents':[],
                'code_changes':[{'path':'src/main/java/Login.java','untracked':False}], 'diff_base':'HEAD', 'activity':[],
                'approvals':{},'warnings':[]}
        data={'overview':overview,'detail':detail,'markdown':'# 変更設計\n\n| REQ | Status |\n| --- | --- |\n| REQ-001 | PASS |','diff':'@@ -1,2 +1,2 @@\n-old\n+new\n context'}
        self.page.evaluate('''data => {
            window.fetch=async function(path){let url=new URL(path,'https://fake.invalid');
                if(url.pathname==='/api/overview') return new Response(JSON.stringify(data.overview),{status:200});
                if(url.pathname==='/api/change') return new Response(JSON.stringify(data.detail),{status:200});
                if(url.pathname==='/api/document') return new Response(data.markdown,{status:200});
                if(url.pathname==='/api/diff') return new Response(JSON.stringify({diff:data.diff}),{status:200});
                return new Response(JSON.stringify({error:'not found'}),{status:404});
            };
        }''',data)
        self.page.add_script_tag(path=ROOT/'markdown-viewer.js')
        self.page.add_script_tag(path=ROOT/'diff-viewer.js')
        self.page.add_script_tag(path=ROOT/'app.js')
        self.page.get_by_role('button',name='仕様・調査資料').click()
        self.page.get_by_role('button',name='表示',exact=True).click()
        self.assertEqual(self.page.locator('dialog[open] .markdown-body h1').inner_text(),'変更設計')
        self.assertEqual(self.page.locator('dialog[open] .markdown-body table').count(),1)
        if os.getenv('SDD_CAPTURE_SAMPLES'):
            self.page.screenshot(path=str(Path(os.environ['SDD_CAPTURE_SAMPLES'])/'markdown-viewer.png'),full_page=True)
        self.page.get_by_role('button',name='Markdown原文').click()
        self.assertIn('# 変更設計',self.page.locator('dialog[open] pre').inner_text())
        self.page.get_by_role('button',name='閉じる').click()
        self.page.get_by_role('button',name='コード変更').click()
        self.page.get_by_role('button',name='Diffビューアー').click()
        self.page.wait_for_selector('dialog[open] .diff-add')
        self.assertEqual(self.page.locator('dialog[open] .diff-add').count(),1)
        self.page.get_by_role('button',name='左右比較').click()
        self.assertEqual(self.page.locator('dialog[open] .diff-side.diff-add').count(),1)
        if os.getenv('SDD_CAPTURE_SAMPLES'):
            self.page.screenshot(path=str(Path(os.environ['SDD_CAPTURE_SAMPLES'])/'diff-viewer.png'),full_page=True)

if __name__=='__main__': unittest.main()
