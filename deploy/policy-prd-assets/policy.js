(()=>{
 const mq=matchMedia('(min-width:601px) and (prefers-color-scheme: dark)');
 const theme=()=>{document.documentElement.dataset.theme=mq.matches?'dark':'light'};theme();mq.addEventListener('change',theme);
 const sections=[...document.querySelectorAll('.policy-section')], links=[...document.querySelectorAll('[data-section]')];
 const status=document.getElementById('policy-status'), panel=document.getElementById('policy-inspector'),open=document.getElementById('inspector-open'),close=document.getElementById('inspector-close');
 let current=0;
 function select(id,focus=false){let idx=sections.findIndex(s=>s.id===id);if(idx<0)idx=sections.length>1?1:0;current=idx;sections.forEach((s,i)=>s.hidden=i!==idx);links.forEach((a,i)=>i===idx?a.setAttribute('aria-current','page'):a.removeAttribute('aria-current'));const title=sections[idx].dataset.title;document.getElementById('selection-title').textContent='선택 정책 · '+String(idx+1).padStart(2,'0')+' / '+sections.length;document.getElementById('inspector-section').textContent=title;status.textContent=title+' 정책을 표시했습니다.';if(focus)sections[idx].focus({preventScroll:true});}
 document.documentElement.classList.add('enhanced');select(location.hash.slice(1));
 links.forEach(a=>a.addEventListener('click',()=>select(a.dataset.section,true)));addEventListener('hashchange',()=>select(location.hash.slice(1)));
 document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)||e.altKey||e.ctrlKey||e.metaKey)return;if(e.key==='j'||e.key==='k'){e.preventDefault();const idx=Math.max(0,Math.min(sections.length-1,current+(e.key==='j'?1:-1)));location.hash=sections[idx].id;select(sections[idx].id,true);}if(e.key==='Escape'&&panel.hasAttribute('data-open'))close.click();});
 function modal(active){if(!matchMedia('(max-width:600px)').matches)return;document.querySelector('.page-head').inert=active;document.querySelector('.qb-side').inert=active;document.querySelector('main').inert=active;if(active){panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');}else{panel.removeAttribute('role');panel.removeAttribute('aria-modal');}}
 open.addEventListener('click',()=>{panel.setAttribute('data-open','');open.setAttribute('aria-expanded','true');modal(true);close.focus();});
 close.addEventListener('click',()=>{modal(false);panel.removeAttribute('data-open');open.setAttribute('aria-expanded','false');open.focus();});
 document.getElementById('print-document').addEventListener('click',()=>print());
 const mobile=matchMedia('(max-width:600px)');mobile.addEventListener('change',()=>{document.querySelector('.page-head').inert=false;document.querySelector('.qb-side').inert=false;document.querySelector('main').inert=false;panel.removeAttribute('role');panel.removeAttribute('aria-modal');panel.removeAttribute('data-open');open.setAttribute('aria-expanded','false');});
})();
