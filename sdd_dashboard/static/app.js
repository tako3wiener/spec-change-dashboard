'use strict';
const $=id=>document.getElementById(id);
const ui={overview:null,detail:null,selected:null,tab:'overview',busy:false};
const labels={G0:'初期設定',G1:'仕様・影響調査',G2:'設計承認',G3:'Java実装・テスト',G4:'Playwright E2E',G5:'独立レビュー',G6:'最終承認',DONE:'完了'};
function el(tag,cls='',content=null){const x=document.createElement(tag);if(cls)x.className=cls;if(content!==null)x.textContent=String(content);return x}
function add(parent,...children){children.forEach(x=>parent.append(x));return parent}
function title(tag,text){return el(tag,'',text)}
function button(label,fn,cls='link-button'){const b=el('button',cls,label);b.type='button';b.addEventListener('click',fn);return b}
function pill(text,kind=''){return el('span','status-pill '+kind,text)}
function card(cls=''){return el('div','card '+cls)}
function info(text){return el('p','muted',text)}
function warning(text){return el('div','notice',text)}
function uri(path,params){return path+'?'+new URLSearchParams(params).toString()}
async function get(path){const r=await fetch(path,{cache:'no-store'});const data=await r.json();if(!r.ok)throw Error(data.error||r.statusText);return data}
function showError(text){$('alert').textContent=text;$('alert').classList.remove('hidden')}
function hideError(){$('alert').classList.add('hidden')}
function fmt(t){if(!t)return '不明';let d=new Date(t);return Number.isNaN(+d)?t:d.toLocaleString('ja-JP',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}
function statusKind(status){return status==='PASS'||status==='verified'?'pass':status==='FAIL'||status==='invalid'||status==='blocked'?'danger':'warn'}
function section(parent,name){const h=el('h3','section-title',name);parent.append(h);return h}
function preview(name,kind,node){$('previewTitle').textContent=name;$('previewKind').textContent=kind;const body=$('previewBody');body.replaceChildren(node);$('preview').showModal()}
async function previewText(path,name,kind='ファイルプレビュー'){
  try{
    const r=await fetch(path,{cache:'no-store'});
    if(!r.ok)throw Error('ファイルを表示できません');
    const text=await r.text();
    if(/\.md$/i.test(name)){
      const container=el('div','document-viewer');
      const tabs=el('div','viewer-mode-tabs');
      const content=el('div','document-viewer-content');
      let mode='rendered';
      function switchMode(next){
        mode=next;
        tabs.replaceChildren(
          button('整形表示',()=>switchMode('rendered'),'viewer-mode-btn'+(mode==='rendered'?' active':'')),
          button('Markdown原文',()=>switchMode('source'),'viewer-mode-btn'+(mode==='source'?' active':''))
        );
        content.replaceChildren(mode==='rendered' && typeof createMarkdownViewer==='function'
          ?createMarkdownViewer(text):el('pre','preview-pre',text));
      }
      add(container,tabs,content);switchMode(mode);
      preview(name,'MARKDOWN VIEWER',container);
    }else preview(name,kind,el('pre','preview-pre',text));
  }catch(e){showError(String(e.message||e))}
}

function download(path,name='ファイルを開く'){const link=el('a','link-button',name);link.href=path;link.target='_blank';link.rel='noopener noreferrer';return link}
function docEntry(file,change,source=false){const box=el('div','doc-item'),left=el('div');add(left,el('strong','',file.path),el('small','',file.bytes+' bytes · '+fmt(file.updated_at)));
 const u=uri('/api/document',{id:change,path:file.path,source:source?'1':'0'});add(box,left,file.path.toLowerCase().endsWith('.pdf')?download(u,'PDFを開く'):button('表示',()=>previewText(u,file.path)));return box}
function documentGrid(files,change,source=false){const grid=el('div','item-grid');if(!files.length)grid.append(info('該当資料はまだありません。'));
 files.forEach(f=>grid.append(docEntry(f,change,source)));return grid}
function summaryCard(label,value,sub,cls=''){const x=card('metric');add(x,el('div','label',label),el('div',cls||'large-metric',value),el('div','small-note',sub));return x}
function renderOverview(body,d){const grid=el('div','summary-grid');
  const event=d.event&&!d.event.branch_mismatch?d.event:null;
  add(grid,summaryCard('現在のゲート',d.gate+' · '+(labels[d.gate]||'未確認'),d.gate_label),
    summaryCard('次に行うこと',d.next_action,event?'記録更新：'+fmt(event.reported_at):'進捗イベント未記録（成果物からの推定）','next-text'),
    summaryCard('E2E実行状況',d.e2e_status,`現在のブランチ：${d.git.branch}`,d.e2e_status==='PASS'?'large-metric':''));
  body.append(grid);
  const g=card('gate-card'),gh=el('div','gate-head');add(gh,title('h3','開発ゲート'),pill(event?`作業申告：${event.state}`:'成果物から推定','warn'));g.append(gh);
  const line=el('div','gate-line');(d.gates||[]).forEach(item=>{
    const step=el('div','gate-step'+(item.id===d.gate?' focus':'')+(item.status==='verified'?' passed':'')+(item.status==='reported-blocked'?' blocked':''));
    add(step,el('span','gate-num',item.id),el('span','gate-name',item.title),el('span','gate-state',item.status==='verified'?'署名確認':item.status.startsWith('reported')?'進捗申告':item.status==='observed'?'成果物あり':'未完了'));step.title=item.detail||'';line.append(step)
  });g.append(line);body.append(g);
  const sectionGrid=el('div','item-grid');const a=card('metric');add(a,title('h3','作業ブランチ'),el('div','large-metric mono',d.git.branch),el('div','small-note','HEAD '+d.git.commit));
  const b=card('metric');add(b,title('h3','仕様・ケース'),el('div','large-metric',`${d.requirements.count} REQ / ${d.test_cases.count} TC`),el('div','small-note','CSVから集計 · 内容の充足は別途レビュー'));const c=card('metric');add(c,title('h3','テスト実行履歴'),el('div','large-metric',`${d.java_runs.length+d.e2e_runs.length} 件`),el('div','small-note','最近のローカル記録'));add(sectionGrid,a,b,c);body.append(sectionGrid);
  if(event){const p=card('panel');add(p,title('h3','最新の作業申告'),info(`記録時ブランチ：${event.branch} · ${fmt(event.reported_at)}`),info(event.note||'詳細なメモはありません'));body.append(p)}
  if(d.activity&&d.activity.length){section(body,'最近の進捗イベント（作業申告）');const c=card('panel');for(const ev of d.activity.slice(0,8)){
    const row=el('div','file-row');add(row,el('span','',`${ev.gate} · ${ev.state} · ${ev.next||'—'}`),el('span','small-note',fmt(ev.reported_at)));c.append(row)
  }body.append(c)}
  (d.warnings||[]).forEach(t=>body.append(warning(t)));
}
function renderDocs(body,d){
  section(body,'承認用の調査・設計資料');body.append(documentGrid(d.documents,d.change_id));
  section(body,'参照元の仕様書');body.append(documentGrid(d.source_documents,d.change_id,true));
  section(body,'要求・テストケース集計');const stats=card('panel');
  add(stats,info(`${d.requirements.count} 件の要求 / ${d.test_cases.count} 件のテストケース`));
  const tbl=el('pre','preview-pre');const reqs=(d.requirements.rows||[]).slice(0,15);tbl.textContent=reqs.length?reqs.map(r=>Object.values(r).slice(0,5).join('  |  ')).join('\n'):'まだデータがありません';stats.append(tbl);body.append(stats)
}
function renderDiff(body,d){
 body.append(warning('比較元：'+(d.diff_base||'HEAD')+'。ブランチと未コミット変更を含みますが、変更IDだけに属する差分とは限りません。秘匿情報を含む変更は公開しないでください。'));
 section(body,'変更されたソースコード');
 if(!d.code_changes.length){body.append(info('現在のGit作業ツリーにプレビュー対象の変更はありません。'));return}
 d.code_changes.forEach(f=>{
   const row=el('div','file-row');
   add(row,el('span','mono',f.path+(f.untracked?'  · 未追跡':'')),button('Diffビューアー',async()=>{
     try{
       const v=await get(uri('/api/diff',{id:d.change_id,path:f.path}));
       const display=typeof createDiffViewer==='function'?createDiffViewer(v.diff||''):el('pre','preview-pre',v.diff||'差分なし');
       preview(f.path,'GIT DIFF · 統合 / 左右比較',display);
     }catch(e){showError(e.message)}
   }));body.append(row);
 });
}

function artifactUrl(kind,change,run,path){return uri('/api/artifact',{kind,id:change,run,path})}
function renderRuns(body,d){
 section(body,'Playwright E2E · スクリーンショットとTrace');
 if(!d.e2e_runs.length)body.append(info('E2Eの実行結果はまだありません。'));
 for(const r of d.e2e_runs){const wrap=el('div','run'),hdr=el('div','run-top');
   add(hdr,el('strong','mono',r.run_id),pill(r.status,statusKind(r.status)));wrap.append(hdr);
   add(wrap,info(`実行：${fmt(r.started_at)} / 完了：${fmt(r.finished_at)} / snapshot ${r.snapshot_id||'不明'}`));
   if(r.problems&&r.problems.length)wrap.append(warning(JSON.stringify(r.problems).slice(0,400)));
   for(const tc of r.test_cases||[]){wrap.append(el('p','run-sub',tc.tc_id+' · '+tc.result));const shots=el('div','shots');for(const shot of tc.screenshots){const u=artifactUrl('e2e',d.change_id,r.run_id,shot.path);const tile=el('div','shot');const img=el('img');img.loading='lazy';img.alt=tc.tc_id+' '+shot.name;img.src=u;img.addEventListener('click',()=>{const big=el('img','preview-pic');big.src=u;big.alt=img.alt;preview(img.alt,'PLAYWRIGHT SCREENSHOT',big)});add(tile,img,el('div','shot-info',shot.name));shots.append(tile)}wrap.append(shots);
    if(tc.trace){const row=el('div','file-row');add(row,el('span','',tc.tc_id+' のTrace'),download(artifactUrl('e2e',d.change_id,r.run_id,tc.trace),'Trace ZIP'));wrap.append(row)}
   }
   for(const f of r.files.filter(f=>['.xml','.json','.csv','.md'].some(s=>f.path.endsWith(s))).slice(0,20)){const row=el('div','file-row');add(row,el('span','mono',f.path),button('表示',()=>previewText(artifactUrl('e2e',d.change_id,r.run_id,f.path),f.path)));wrap.append(row)}
   body.append(wrap)}
 section(body,'JUnit 単体・結合テスト');if(!d.java_runs.length)body.append(info('JUnitの集約結果はまだありません。'));
 d.java_runs.forEach(r=>{const c=el('div','run'),head=el('div','run-top');add(head,el('strong','',`${r.phase} · ${r.run_id}`),pill(r.status,statusKind(r.status)));add(c,head,info(`完了：${fmt(r.finished_at)} · ${JSON.stringify(r.counts)}`));
  for(const f of r.files.filter(f=>f.path.endsWith('.xml')||f.path.endsWith('.json')).slice(0,18)){
   const row=el('div','file-row'),u=artifactUrl('unit',d.change_id,r.run_id,r.phase+'/'+f.path);add(row,el('span','mono',f.path),button('表示',()=>previewText(u,f.path)));c.append(row)}body.append(c)})
}
function renderApprovals(body,d){body.append(warning('承認資料はこの画面で確認できますが、承認行為は行いません。G2・NET・G6の署名は従来どおりClaudeから秘密鍵を操作できない外部環境で実施してください。'));
 const grid=el('div','approval-grid');['G2','NET','G6'].forEach(g=>{const data=d.approvals[g]||{},c=el('div','approval-card');add(c,title('h3',g+(g==='G2'?' · 実装計画':g==='G6'?' · 最終受入':' · 環境安全')),pill(data.label||'未提出',statusKind(data.status)),info('承認者：'+(data.approver||'未確認')),info('日時：'+fmt(data.approved_at)));
 if(g!=='NET')c.append(button('承認対象のハッシュを確認',async()=>{
  try{const packet=await get(uri('/api/approval-materials',{id:d.change_id,gate:g}));const pane=el('div');const pre=el('pre','preview-pre',JSON.stringify(packet,null,2));
   add(pane,warning('署名前の確認資料です。表示・コピーでは承認は成立しません。'),pre,button('JSONをコピー',async()=>{try{await navigator.clipboard.writeText(JSON.stringify(packet,null,2))}catch(e){showError('コピーできませんでした')}}));preview(g+' 承認確認用','署名なし・PENDING',pane)
  }catch(e){showError(e.message)}
 }));grid.append(c)});body.append(grid);
 section(body,'G2承認資料');body.append(documentGrid(d.documents.filter(f=>['change-plan.md','requirements.csv','test_cases.csv'].includes(f.path)),d.change_id));
}
function renderTabs(d){const root=$('changeBody');root.replaceChildren();const tabs=el('div','tabs');const labels=[['overview','概況'],['docs','仕様・調査資料'],['diff','コード変更'],['tests','テスト・エビデンス'],['approval','承認資料']];for(const [id,name] of labels)tabs.append(button(name,()=>{ui.tab=id;renderTabs(d)},'tab'+(ui.tab===id?' active':'')));
 root.append(tabs);const body=card('panel');root.append(body);
 if(ui.tab==='overview')renderOverview(body,d);else if(ui.tab==='docs')renderDocs(body,d);else if(ui.tab==='diff')renderDiff(body,d);else if(ui.tab==='tests')renderRuns(body,d);else renderApprovals(body,d)
}
async function loadChange(id){if(!id)return;ui.selected=id;try{const d=await get(uri('/api/change',{id}));ui.detail=d;$('crumb').textContent=id;$('mainTitle').textContent=id+' の開発状況';$('mainSubtitle').textContent=d.gate_label+' · 最新更新 '+fmt(d.last_updated);renderTabs(d);showSidebar()}catch(e){showError('変更情報の読み込みに失敗：'+e.message)}}
function showSidebar(){const list=$('changeList');list.replaceChildren();const cs=ui.overview?.changes||[];$('changeCount').textContent=cs.length;cs.forEach(c=>{
 const x=el('button','change-item'+(ui.selected===c.change_id?' selected':''));add(x,el('span','id',c.change_id),el('small','',`${c.gate} · ${labels[c.gate]||'確認中'}`));x.addEventListener('click',()=>{ui.tab='overview';loadChange(c.change_id)});list.append(x)
})}
async function refresh(){if(ui.busy)return;ui.busy=true;hideError();try{const data=await get('/api/overview');ui.overview=data;
 $('repoMeta').replaceChildren(el('strong','',data.name),el('small','',data.repository_root),el('small','',data.git.branch+' · '+data.git.commit));$('heroEnvironment').textContent='ENV '+data.environment;$('heroBranch').textContent='BRANCH '+data.git.branch;$('lastRefresh').textContent='更新 '+new Date().toLocaleTimeString('ja-JP');
 showSidebar();if(!data.changes.length){$('changeBody').replaceChildren(el('div','empty','変更IDはまだありません。/spec-change を実行して要求資料または進捗を作成してください。'));return}
 if(!data.changes.some(c=>c.change_id===ui.selected))ui.selected=data.changes[0].change_id;await loadChange(ui.selected)
 }catch(e){showError('読み込みに失敗：'+e.message)}finally{ui.busy=false}}
$('refresh').addEventListener('click',refresh);$('closePreview').addEventListener('click',()=>$('preview').close());$('preview').addEventListener('click',e=>{if(e.target===$('preview'))$('preview').close()});
refresh();setInterval(refresh,15000);
