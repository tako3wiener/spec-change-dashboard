/* Read-only Git unified/split diff viewer. Git source text is never HTML. */
'use strict';
(function(global){
  const el=(tag,cls='',value)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(value!==undefined)e.textContent=String(value);return e};
  const HUNK=/^@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@(.*)$/;
  function parseUnifiedDiff(raw){
    const lines=String(raw||'').replace(/\r\n?/g,'\n').split('\n');if(lines.at(-1)==='')lines.pop();
    const records=[];let old=0,now=0,counts={added:0,removed:0,hunks:0};let inHunk=false;
    for(const line of lines){let m;
      if((m=HUNK.exec(line))){old=+m[1];now=+m[3];inHunk=true;counts.hunks++;records.push({type:'hunk',text:line});continue}
      if(/^diff --git |^index |^--- |^\+\+\+ |^new file mode |^deleted file mode |^rename (from|to) |^similarity index |^Binary files |^GIT binary patch|^\\ No newline at end of file/.test(line)){
        records.push({type:'meta',text:line});continue;
      }
      if(inHunk){
        if(line.startsWith('+')){records.push({type:'add',old:null,now:now++,text:line.slice(1)});counts.added++;continue}
        if(line.startsWith('-')){records.push({type:'del',old:old++,now:null,text:line.slice(1)});counts.removed++;continue}
        if(line.startsWith(' ')){records.push({type:'ctx',old:old++,now:now++,text:line.slice(1)});continue}
      }
      // Old v1.0 backend generates untracked files as bare +lines.
      if(!inHunk && line.startsWith('+') && !line.startsWith('+++')){
        records.push({type:'add',old:null,now:++now,text:line.slice(1)});counts.added++;continue;
      }
      if(!inHunk && line.startsWith('-') && !line.startsWith('---')){
        records.push({type:'del',old:++old,now:null,text:line.slice(1)});counts.removed++;continue;
      }
      records.push({type:'meta',text:line});
    }
    return {records,counts};
  }
  function makeToolbar(raw,parsed,controls){
    const bar=el('div','diff-toolbar'),summary=el('div','diff-counts');
    summary.append(el('span','diff-add-count','+'+parsed.counts.added),el('span','diff-del-count','−'+parsed.counts.removed),el('span','diff-hunk-count',parsed.counts.hunks+' hunk'));
    const toggle=el('div','diff-switch');
    ['unified','split'].forEach(mode=>{const b=el('button','diff-switch-btn'+(mode===controls.mode?' active':''),mode==='unified'?'統合表示':'左右比較');b.type='button';b.setAttribute('aria-pressed',String(mode===controls.mode));b.onclick=()=>controls.switchTo(mode);toggle.append(b)});
    const copy=el('button','diff-copy','差分をコピー');copy.type='button';copy.onclick=async()=>{try{await navigator.clipboard.writeText(raw);copy.textContent='コピー済み'}catch{copy.textContent='コピー不可'}};
    bar.append(summary,toggle,copy);return bar;
  }
  function cell(cls,textValue){return el('span','diff-cell '+cls,textValue==null?'':textValue)}
  function row(record){
    const r=el('div','diff-row diff-'+record.type);
    if(record.type==='hunk'||record.type==='meta'){r.classList.add('diff-row-meta');r.append(cell('diff-line-full',record.text));return r}
    r.append(cell('diff-ln',record.old??''),cell('diff-ln',record.now??''),cell('diff-mark',record.type==='add'?'+':record.type==='del'?'−':' '),cell('diff-code',record.text));
    return r;
  }
  function splitPair(left,right){
    const r=el('div','diff-pair');
    function side(record,isRight){const x=el('div','diff-side '+(record?'diff-'+record.type:'diff-empty'));
      const ln=record?(isRight?record.now:record.old):'';
      x.append(cell('diff-ln',ln??''),cell('diff-mark',record?.type==='add'?'+':record?.type==='del'?'−':' '),cell('diff-code',record?.text??''));return x}
    r.append(side(left,false),side(right,true));return r;
  }
  function splitRows(records){
    const out=[];let i=0;
    while(i<records.length){const r=records[i];
      if(r.type==='meta'||r.type==='hunk'){out.push(row(r));i++;continue}
      if(r.type==='ctx'){out.push(splitPair(r,r));i++;continue}
      if(r.type==='del'){
        const deleted=[];while(records[i]?.type==='del')deleted.push(records[i++]);
        const added=[];while(records[i]?.type==='add')added.push(records[i++]);
        for(let j=0;j<Math.max(deleted.length,added.length);j++)out.push(splitPair(deleted[j],added[j]));continue;
      }
      if(r.type==='add'){
        while(records[i]?.type==='add')out.push(splitPair(null,records[i++]));continue;
      }
      out.push(row(r));i++;
    }
    return out;
  }
  function createDiffViewer(raw){
    const text=String(raw||'');const parsed=parseUnifiedDiff(text),root=el('section','diff-viewer');
    const content=el('div','diff-content unified');let mode='unified';
    const controls={get mode(){return mode},switchTo(next){
      mode=next;
      root.replaceChild(makeToolbar(text,parsed,controls),root.firstChild);
      content.className='diff-content '+mode;
      renderContent();
    }};
    function renderContent(){
      if(!parsed.records.length){content.replaceChildren(el('div','diff-empty-message','差分はありません。'));return}
      const rows=parsed.records.slice(0,4000);
      content.replaceChildren(...(mode==='split'?splitRows(rows):rows.map(row)));
    }
    root.append(makeToolbar(text,parsed,controls),content);
    renderContent();
    if(parsed.records.length>4000)root.append(el('p','diff-note','差分が大きいため、最初の4,000行のみ表示しています。'));
    return root;
  }
  global.createDiffViewer=createDiffViewer;
  global.parseUnifiedDiff=parseUnifiedDiff;
})(window);
