const $ = s => document.querySelector(s);
let documents = [], history = [], currentSources = [], registering = true, busy = false;
const escapeHTML = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path, body) {
  const response = await fetch('/api/' + path, body === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}
let toastTimer;
function toast(message) { $('#toast').textContent=message; $('#toast').classList.remove('hidden'); clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('#toast').classList.add('hidden'),6500); }
function view(name) {
  document.querySelectorAll('.view').forEach(el=>el.classList.add('hidden'));
  $(`#${name}-view`).classList.remove('hidden');
  document.querySelectorAll('.nav-item').forEach(el=>el.classList.toggle('active',el.dataset.view===name));
  const titles={ask:['Ask knowledge','Good questions. Grounded answers.','Turn scattered documents into knowledge you can trust.'],library:['Knowledge sources','Your knowledge, in one place.','Upload and manage the documents your answers come from.'],history:['Recent questions','Pick up where you left off.','Revisit your questions and the evidence behind them.']};
  ['#breadcrumb','#page-title','#page-description'].forEach((id,i)=>$(id).textContent=titles[name][i]);
  if(name==='history') refreshHistory().catch(e=>toast(e.message));
}
async function boot() {
  try {
    const user=await api('me');
    $('#auth').classList.add('hidden'); $('#app').classList.remove('hidden');
    $('#workspace-name').textContent=user.workspace; $('#workspace-avatar').textContent=user.workspace[0].toUpperCase(); $('#user-email').textContent=user.email;
    await refreshDocuments();
  } catch(e) { $('#auth').classList.remove('hidden'); $('#app').classList.add('hidden'); }
}
$('#auth-toggle').onclick=()=>{
  registering=!registering; $('#workspace-label').classList.toggle('hidden',!registering); $('[name=workspace]').required=registering;
  $('#auth-submit').textContent=registering?'Create workspace ↗':'Sign in ↗';
  $('[name=password]').autocomplete=registering?'new-password':'current-password';
  $('#auth-toggle').textContent=registering?'Already have a workspace? Sign in':'New here? Create a workspace'; $('#auth-error').textContent='';
};
$('#auth-form').onsubmit=async e=>{e.preventDefault();$('#auth-submit').disabled=true;$('#auth-error').textContent='';try{await api(registering?'register':'login',Object.fromEntries(new FormData(e.target)));await boot();}catch(error){$('#auth-error').textContent=error.message;}finally{$('#auth-submit').disabled=false;}};
$('#logout').onclick=async()=>{try{await api('logout',{});location.reload();}catch(e){toast(e.message);}};
document.querySelectorAll('[data-view]').forEach(el=>el.onclick=()=>view(el.dataset.view));
$('#browse-sources').onclick=()=>view('library');
$('#upload-button').onclick=()=>$('#file-input').click();
$('#dropzone').onclick=()=>$('#file-input').click();
$('#dropzone').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('#file-input').click();}};
$('#dropzone').ondragover=e=>{e.preventDefault();$('#dropzone').classList.add('dragging');};
$('#dropzone').ondragleave=()=>$('#dropzone').classList.remove('dragging');
$('#dropzone').ondrop=e=>{e.preventDefault();$('#dropzone').classList.remove('dragging');upload(e.dataTransfer.files);};
$('#file-input').onchange=e=>upload(e.target.files);
async function upload(files){
  if(busy) return toast('Please wait for the current upload to finish.');
  busy=true;$('#upload-button').disabled=true;
  try{for(const file of files){
    if(file.size>10*1024*1024){toast(`${file.name}: exceeds the 10 MB limit.`);continue;}
    toast(`Indexing ${file.name}…`);
    try{
      const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read file.'));reader.readAsDataURL(file);});
      const result=await api('upload',{name:file.name,content});
      toast(`${file.name} is ready · ${result.chunks} searchable passages`);
    }catch(e){toast(`${file.name}: ${e.message}`);}
  }await refreshDocuments();view('library');}finally{busy=false;$('#upload-button').disabled=false;$('#file-input').value='';}
}
async function refreshDocuments(){documents=await api('documents');$('#nav-count').textContent=documents.length;$('#stat-docs').innerHTML=`${documents.length} <small>documents</small>`;$('#stat-chunks').innerHTML=`${documents.reduce((n,d)=>n+d.chunks,0)} <small>indexed</small>`;renderDocuments();}
function renderDocuments(){const filtered=documents.filter(d=>d.name.toLowerCase().includes($('#source-filter').value.toLowerCase()));$('#document-rows').innerHTML=filtered.length?filtered.map(d=>`<tr><td>▤ &nbsp; ${escapeHTML(d.name)}<small>${Math.max(1,Math.round(d.size/1024))} KB · ${d.pages} page${d.pages!==1?'s':''}</small></td><td><span class="pill">Ready</span></td><td>${d.chunks}</td><td>${new Date(d.created*1000).toLocaleDateString(undefined,{month:'short',day:'numeric'})}</td><td><button class="delete-button" data-delete="${d.id}">Delete</button></td></tr>`).join(''):`<tr><td colspan="5" class="empty-row">${documents.length?'No documents match your filter.':'No sources yet. Upload your first document to get started.'}</td></tr>`;}
$('#source-filter').oninput=renderDocuments;
$('#document-rows').onclick=async e=>{const button=e.target.closest('[data-delete]');if(!button)return;if(!confirm('Delete this source and clear saved answer history? This removes its indexed passages.'))return;try{await api('delete',{id:button.dataset.delete});currentSources=[];$('#conversation-content').innerHTML='';$('#evidence-content').innerHTML='<p class="muted">Ask a question to find source evidence.</p>';$('#evidence-count').textContent='0';await refreshDocuments();toast('Source and saved answer history removed.');}catch(error){toast(error.message);}};
document.querySelectorAll('[data-question]').forEach(el=>el.onclick=()=>{$('#question').value=el.dataset.question;$('#question').focus();});
$('#question').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#question-form').requestSubmit();}};
$('#question-form').onsubmit=async e=>{e.preventDefault();const question=$('#question').value.trim();if(question.length<3)return toast('Enter a question of at least 3 characters.');if($('#ask-button').disabled)return;$('#ask-button').disabled=true;$('#conversation-content').innerHTML=`<div class="question-bubble">${escapeHTML(question)}</div><div class="answer-block" role="status">Searching your sources…</div>`;try{const result=await api('ask',{question});renderAnswer(question,result);$('#question').value='';}catch(error){$('#conversation-content').innerHTML=`<div class="answer-block error">${escapeHTML(error.message)}</div>`;}finally{$('#ask-button').disabled=false;}};
function renderAnswer(question,result){
  currentSources=result.sources;
  $('#conversation-content').innerHTML=`<div class="question-bubble">${escapeHTML(question)}</div><div class="answer-block"><h3>✧ &nbsp; ${result.status==='evidence_found'?'Related source evidence':'Insufficient evidence'}</h3><p>${escapeHTML(result.answer)}</p>${result.sources.map((s,i)=>`<blockquote>${escapeHTML(s.text.slice(0,420))}${s.text.length>420?'…':''}<br><button class="citation" data-source="${i}">[${i+1}] ${escapeHTML(s.name)} · Page ${s.page} ↗</button></blockquote>`).join('')}</div>`;
  $('#evidence-count').textContent=result.sources.length;
  $('#evidence-content').innerHTML=result.sources.length?result.sources.map((s,i)=>`<button class="evidence-card" data-source="${i}"><strong><span class="citation">${i+1}</span> ${escapeHTML(s.name)}</strong><p>${escapeHTML(s.text.slice(0,160))}…</p><small>Page ${s.page} · View full passage ↗</small></button>`).join(''):'<div class="evidence-empty"><span>⌕</span><h3>No matching evidence</h3><p>Add relevant documents or use more specific terms from your sources.</p></div>';
}
document.addEventListener('click',e=>{const target=e.target.closest('[data-source]');if(!target)return;const source=currentSources[Number(target.dataset.source)];if(!source)return;$('#source-title').textContent=source.name;$('#source-page').textContent=`Page ${source.page} · Indexed passage`;$('#source-text').textContent=source.text;$('#source-dialog').showModal();});
$('#close-dialog').onclick=()=>$('#source-dialog').close();
async function refreshHistory(){history=await api('history');$('#history-list').innerHTML=history.length?history.map((h,i)=>`<button class="history-item" data-history="${i}"><strong>${escapeHTML(h.question)}</strong><small>${new Date(h.created*1000).toLocaleString()} · ${JSON.parse(h.answer).sources.length} sources</small></button>`).join(''):'<div class="empty-row">Your questions will appear here after your first search.</div>';}
$('#history-list').onclick=e=>{const item=e.target.closest('[data-history]');if(!item)return;const h=history[Number(item.dataset.history)];view('ask');renderAnswer(h.question,JSON.parse(h.answer));};
boot();
