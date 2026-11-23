/* Dependency-free Markdown document viewer. All content is built with textContent;
   untrusted Markdown is never passed to innerHTML. Supports common Markdown/GFM
   constructs; deliberately does not execute raw HTML or embedded scripts. */
'use strict';
(function(global) {
  const node=(tag,cls='')=>{const e=document.createElement(tag);if(cls)e.className=cls;return e};
  const text=(value)=>document.createTextNode(value);
  function appendInline(parent,raw,depth=0){
    if(depth>8){parent.append(text(raw));return}
    let i=0,buf='';
    const flush=()=>{if(buf){parent.append(text(buf));buf=''}};
    while(i<raw.length){
      const chunk=raw.slice(i);
      let m=null,tag='',inner='';
      if(chunk[0]==='\\' && chunk.length>1 && /[\\`*_{}\[\]()#+.!~>|-]/.test(chunk[1])){buf+=chunk[1];i+=2;continue}
      if((m=/^`([^`\n]+)`/.exec(chunk))){flush();const code=node('code');code.textContent=m[1];parent.append(code);i+=m[0].length;continue}
      if((m=/^!\[([^\]]*)\]\(([^)\n]*)\)/.exec(chunk))){flush();const x=node('span','md-image-description');x.textContent='画像: '+(m[1]||m[2]);x.title='Markdownの参照画像は安全上、自動読み込みしません';parent.append(x);i+=m[0].length;continue}
      if((m=/^\[([^\]\n]+)\]\(([^)\n]*)\)/.exec(chunk))){
        let url=m[2].trim().replace(/^<|>$/g,'');
        if(/^(https?:\/\/|mailto:)/i.test(url)){
          flush();const link=node('a');link.href=url;link.textContent=m[1];link.rel='noopener noreferrer';link.target='_blank';parent.append(link);i+=m[0].length;continue;
        }
      }
      if((m=/^\*\*(?=\S)([\s\S]*?\S)\*\*/.exec(chunk)) || (m=/^__(?=\S)([\s\S]*?\S)__/.exec(chunk))){tag='strong';inner=m[1]}
      else if((m=/^~~(?=\S)([\s\S]*?\S)~~/.exec(chunk))){tag='del';inner=m[1]}
      else if((m=/^\*(?=\S)([^*\n]*?\S)\*/.exec(chunk)) || (m=/^_(?=\S)([^_\n]*?\S)_/.exec(chunk))){tag='em';inner=m[1]}
      if(m&&tag){flush();const e=node(tag);appendInline(e,inner,depth+1);parent.append(e);i+=m[0].length;continue}
      if(chunk.startsWith('  \n')){flush();parent.append(node('br'));i+=3;continue}
      buf+=raw[i++];
    }
    flush();
  }
  const bullet=line=>/^(\s*)([-+*]|\d+[.)])\s+([\s\S]*)$/.exec(line);
  const fence=line=>/^\s{0,3}(`{3,}|~{3,})([^`]*)$/.exec(line);
  const heading=line=>/^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$/.exec(line);
  const horizontal=line=>/^\s{0,3}(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})$/.test(line);
  const quote=line=>/^\s{0,3}>\s?(.*)$/.exec(line);
  const separator=line=>/^\s*\|?\s*:?[-]{3,}:?\s*(?:\|\s*:?[-]{3,}:?\s*)+\|?\s*$/.test(line);
  const cells=line=>line.trim().replace(/^\|/,'').replace(/\|$/,'').split(/(?<!\\)\|/).map(s=>s.trim().replace(/\\\|/g,'|'));
  function blocks(lines,start,end,parent,depth=0){
    let i=start;
    while(i<end){
      const line=lines[i];
      if(!line.trim()){i++;continue}
      let m;
      if((m=fence(line))){
        const ch=m[1][0],size=m[1].length,language=m[2].trim().split(/\s+/)[0]||'text';
        let j=i+1,contents=[];
        while(j<end && !new RegExp('^\\s{0,3}'+(ch==='`'?'`':'~')+'{'+size+',}\\s*$').test(lines[j]))contents.push(lines[j++]);
        const area=node('div','md-codeblock'),tag=node('div','md-code-language');tag.textContent=language;
        const pre=node('pre'),code=node('code');code.textContent=contents.join('\n');pre.append(code);area.append(tag,pre);parent.append(area);
        i=j<end?j+1:j;continue;
      }
      if((m=heading(line))){const h=node('h'+m[1].length);appendInline(h,m[2]);parent.append(h);i++;continue}
      if(horizontal(line)){parent.append(node('hr'));i++;continue}
      if(depth<5 && (m=quote(line))){let j=i,body=[];while(j<end){const q=quote(lines[j]);if(q){body.push(q[1]);j++}else if(!lines[j].trim()){body.push('');j++}else break}
        const b=node('blockquote');blocks(body,0,body.length,b,depth+1);parent.append(b);i=j;continue}
      if(i+1<end && line.includes('|') && separator(lines[i+1])){
        const head=cells(line),aligns=cells(lines[i+1]);const tbl=node('table'),thead=node('thead'),tr=node('tr');
        head.forEach((c,k)=>{const th=node('th');const a=aligns[k]||'';if(a.startsWith(':')&&a.endsWith(':'))th.style.textAlign='center';else if(a.endsWith(':'))th.style.textAlign='right';appendInline(th,c);tr.append(th)});
        thead.append(tr);tbl.append(thead);let j=i+2,tb=node('tbody');
        while(j<end && lines[j].trim() && lines[j].includes('|')){const row=node('tr');cells(lines[j]).slice(0,head.length).forEach((c,k)=>{const td=node('td');const a=aligns[k]||'';if(a.startsWith(':')&&a.endsWith(':'))td.style.textAlign='center';else if(a.endsWith(':'))td.style.textAlign='right';appendInline(td,c);row.append(td)});tb.append(row);j++}
        tbl.append(tb);const wrap=node('div','md-table-wrap');wrap.append(tbl);parent.append(wrap);i=j;continue;
      }
      if(depth<6 && (m=bullet(line))){
        const startIndent=m[1].length,isOrdered=/\d/.test(m[2][0]);const list=node(isOrdered?'ol':'ul');
        if(isOrdered){const val=parseInt(m[2],10);if(val>1 && val<10000)list.start=val}
        let j=i;
        while(j<end){const first=bullet(lines[j]);if(!first || first[1].length!==startIndent || /\d/.test(first[2][0])!==isOrdered)break;
          const li=node('li');const task=/^\[( |x|X)\]\s+/.exec(first[3]);let content=first[3];
          if(task){content=content.slice(task[0].length);const check=node('input');check.type='checkbox';check.disabled=true;check.checked=task[1].toLowerCase()==='x';li.classList.add('md-task');li.append(check)}
          const textNode=node('span');appendInline(textNode,content);li.append(textNode);j++;
          let sub=[];
          while(j<end){const rest=lines[j];const next=bullet(rest);
            if(next && next[1].length<=startIndent)break;
            if(!rest.trim()){if(j+1>=end || (!lines[j+1].trim())){j++;break}sub.push('');j++;continue}
            const ws=/^\s*/.exec(rest)[0].length;
            if(ws>startIndent){sub.push(rest.slice(Math.min(rest.length,startIndent+2)));j++}else break;
          }
          if(sub.some(s=>s.trim())){const child=node('div','md-nested');blocks(sub,0,sub.length,child,depth+1);li.append(child)}
          list.append(li);
        }
        parent.append(list);i=j;continue;
      }
      // Text paragraphs; do not interpret raw HTML supplied by the document.
      let endAt=i+1;
      while(endAt<end && lines[endAt].trim() && !fence(lines[endAt]) && !heading(lines[endAt]) && !horizontal(lines[endAt]) && !quote(lines[endAt]) && !bullet(lines[endAt]) && !(endAt+1<end && lines[endAt].includes('|') && separator(lines[endAt+1])))endAt++;
      const para=node('p');appendInline(para,lines.slice(i,endAt).join('\n'));parent.append(para);i=endAt;
    }
  }
  function createMarkdownViewer(markdown){
    const root=node('article','markdown-body');
    const content=String(markdown||'').replace(/\r\n?/g,'\n').split('\n');
    blocks(content,0,content.length,root);
    return root;
  }
  global.createMarkdownViewer=createMarkdownViewer;
})(window);
