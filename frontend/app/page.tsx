'use client';

import {useCallback, useEffect, useRef, useState, type FormEvent} from 'react';

type User={email:string;workspace:string;provider_configured:boolean};
type Document={id:string;name:string;size:number;status:string;pages:number;chunk_count:number;error:string|null;created_at:string};
type Source={id:string;document_id:string;name:string;page:number;text:string;similarity:number};
type Claim={text:string;evidence:{source_id:string;quote:string}[]};
type Answer={status:string;answer:string;claims:Claim[];sources:Source[]};
type History={id:string;question:string;result:Answer;created_at:string};
type View='ask'|'library'|'history';

class ApiError extends Error {
  constructor(message:string,public status:number){super(message);}
}

async function api<T>(path:string, options:RequestInit={}):Promise<T>{
  const headers=new Headers(options.headers);
  if(options.method && options.method!=='GET')headers.set('X-Sourceboard','1');
  if(typeof options.body==='string')headers.set('Content-Type','application/json');
  const response=await fetch('/api/'+path,{...options,headers});
  const data=await response.json();
  if(!response.ok){
    const message=typeof data.detail==='string'?data.detail:'Please check your input and try again.';
    throw new ApiError(message,response.status);
  }
  return data;
}
const post=(body:unknown):RequestInit=>({method:'POST',body:JSON.stringify(body)});
const date=(value:string)=>new Date(value).toLocaleDateString(undefined,{month:'short',day:'numeric'});
const suggestions=[
  {label:'People & culture',question:'What is the remote work policy?',icon:'people'},
  {label:'Security & operations',question:'How do I report a security incident?',icon:'shield'},
  {label:'Customer experience',question:'What are the customer support hours?',icon:'chat'},
];
function Icon({name,className=''}:{name:string;className?:string}){
  const paths:Record<string,string>={
    spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
    files:'M8 3h8l4 4v14H8V3Zm8 0v5h4M4 7v14M11 12h6m-6 4h6',
    history:'M3 11a9 9 0 1 1 2 7M3 4v7h7m2-4v5l3 2',
    arrow:'M5 12h14m-6-6 6 6-6 6',
    upload:'M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5',
    shield:'m12 3 8 3v6c0 5-8 9-8 9S4 17 4 12V6l8-3Zm-4 9 3 3 5-6',
    people:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m18 0v-2a4 4 0 0 0-3-3.9M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8m8-7a4 4 0 0 1 0 7',
    chat:'M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5a9.5 9.5 0 0 1 19 0ZM7 10h9M7 14h6',
    search:'m20 20-5-5M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14',
    layers:'m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5',
    logout:'M9 4H3v16h6m-1-8h13m-5-5 5 5-5 5',
    plus:'M12 5v14M5 12h14',
  };
  return <svg className={`icon ${className}`} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]||paths.spark}/></svg>;
}
function CreatorCredit(){return <a className="creator-credit" href="https://www.linkedin.com/in/rashid-ali-619671357/" target="_blank" rel="noopener noreferrer" aria-label="Created by Rashid Ali — LinkedIn profile (opens in a new tab)">Created by <strong>Rashid Ali</strong><span className="linkedin-mark" aria-hidden="true">in</span></a>;}


export default function Home(){
  const [user,setUser]=useState<User|null>(null),[loading,setLoading]=useState(true),[registering,setRegistering]=useState(true);
  const [view,setView]=useState<View>('ask'),[documents,setDocuments]=useState<Document[]>([]),[history,setHistory]=useState<History[]>([]);
  const [question,setQuestion]=useState(''),[asked,setAsked]=useState(''),[result,setResult]=useState<Answer|null>(null);
  const [asking,setAsking]=useState(false),[uploading,setUploading]=useState(false),[authBusy,setAuthBusy]=useState(false);
  const [notice,setNotice]=useState(''),[authError,setAuthError]=useState(''),[filter,setFilter]=useState(''),[dragging,setDragging]=useState(false);
  const [selected,setSelected]=useState<Source|null>(null);
  const [connectionError,setConnectionError]=useState(''),[answerError,setAnswerError]=useState('');
  const [documentsLoading,setDocumentsLoading]=useState(true),[documentsError,setDocumentsError]=useState('');
  const [historyLoading,setHistoryLoading]=useState(false),[historyError,setHistoryError]=useState('');
  const files=useRef<HTMLInputElement>(null),dialog=useRef<HTMLDialogElement>(null),composer=useRef<HTMLTextAreaElement>(null);
  const notify=useCallback((message:string)=>setNotice(message),[]);
  const refresh=useCallback(async()=>{
    try{setDocuments(await api<Document[]>('documents'));setDocumentsError('');}
    catch(error){setDocumentsError((error as Error).message);}
    finally{setDocumentsLoading(false);}
  },[]);
  const connect=useCallback(async()=>{
    setLoading(true);setConnectionError('');
    try{setUser(await api<User>('me'));}
    catch(error){if(!(error instanceof ApiError && error.status===401))setConnectionError((error as Error).message);}
    finally{setLoading(false);}
  },[]);
  const loadHistory=useCallback(async()=>{
    setHistoryLoading(true);setHistoryError('');
    try{setHistory(await api<History[]>('history'));}
    catch(error){setHistoryError((error as Error).message);}
    finally{setHistoryLoading(false);}
  },[]);
  useEffect(()=>{void connect();},[connect]);
  useEffect(()=>{if(!user)return;refresh().catch(e=>notify(e.message));const timer=setInterval(()=>refresh().catch(()=>{}),4000);return()=>clearInterval(timer);},[user,refresh,notify]);
  useEffect(()=>{if(user && view==='history')void loadHistory();},[view,user,loadHistory]);
  useEffect(()=>{if(!notice)return;const timer=setTimeout(()=>setNotice(''),8000);return()=>clearTimeout(timer);},[notice]);
  useEffect(()=>{if(selected)dialog.current?.showModal();},[selected]);

  async function authenticate(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setAuthBusy(true);setAuthError('');
    const data=Object.fromEntries(new FormData(event.currentTarget));
    try{await api(registering?'register':'login',post(data));setUser(await api<User>('me'));}
    catch(e){setAuthError((e as Error).message);}finally{setAuthBusy(false);}
  }
  async function upload(list:FileList|null){
    if(!list||uploading||!user?.provider_configured)return;setUploading(true);
    try{for(const file of Array.from(list)){
      if(file.size>10*1024*1024){notify(`${file.name}: exceeds the 10 MB limit.`);continue;}
      const form=new FormData();form.set('file',file);
      try{await api('documents',{method:'POST',body:form});notify(`${file.name} queued for indexing.`);}
      catch(e){notify(`${file.name}: ${(e as Error).message}`);}
    }await refresh();setView('library');}finally{setUploading(false);if(files.current)files.current.value='';}
  }
  async function ask(event:FormEvent){
    event.preventDefault();if(asking||!user?.provider_configured||question.trim().length<3)return;
    setAsking(true);setAnswerError('');setAsked(question.trim());setResult(null);
    try{setResult(await api<Answer>('ask',post({question:question.trim()})));setQuestion('');}
    catch(e){setAnswerError((e as Error).message);}finally{setAsking(false);}
  }
  async function remove(doc:Document){
    if(!confirm(`Delete ${doc.name} and clear saved answer history?`))return;
    try{await api(`documents/${doc.id}`,{method:'DELETE'});setResult(null);setAsked('');setHistory([]);await refresh();notify('Source removed from search. Original-file deletion is queued.');}
    catch(e){notify((e as Error).message);}
  }
  async function retry(doc:Document){
    try{await api(`documents/${doc.id}/retry`,post({}));await refresh();}catch(e){notify((e as Error).message);}
  }
  async function logout(){
    try{await api('logout',post({}));setUser(null);setDocuments([]);setHistory([]);setResult(null);setAsked('');setQuestion('');setSelected(null);setView('ask');setFilter('');setAnswerError('');setDocumentsError('');setDocumentsLoading(true);setHistoryError('');}
    catch(e){notify((e as Error).message);}
  }

  if(loading)return <div className="loading-screen"><span className="loading-orbit"/><p role="status">Opening your workspace…</p></div>;
  if(connectionError)return <div className="loading-screen"><section className="connection-error" role="alert"><Icon name="shield"/><h1>Your workspace is taking a moment.</h1><p>{connectionError}</p><button className="primary" onClick={()=>void connect()}>Try again <Icon name="arrow"/></button></section></div>;
  if(!user)return <div className="auth-screen"><section className="auth-card">
    <div className="eyebrow"><span className="green-dot"/> YOUR KNOWLEDGE, CONNECTED</div><h1>{registering?<>Big ideas.<br/>Clear answers.</>:<>Good to have<br/>you back.</>}</h1>
    <p>One calm place for your documents, questions, and the answers that move work forward.</p>
    <form onSubmit={authenticate} aria-busy={authBusy}>{registering&&<label>Workspace name<input disabled={authBusy} name="workspace" required maxLength={80} placeholder="Acme team"/></label>}
      <label>Work email<input disabled={authBusy} name="email" type="email" required autoComplete="email" placeholder="you@company.com"/></label>
      <label>Password<input disabled={authBusy} name="password" type="password" required minLength={10} maxLength={128} autoComplete={registering?'new-password':'current-password'} placeholder="At least 10 characters"/></label>
      <button className="primary" disabled={authBusy}>{authBusy?'Please wait…':registering?'Create workspace ↗':'Sign in ↗'}</button>
      {authError&&<p className="error" role="alert">{authError}</p>}
    </form><button className="text-button" disabled={authBusy} onClick={()=>{setRegistering(!registering);setAuthError('');}}>{registering?'Already have a workspace? Sign in':'New here? Create a workspace'}</button>
    <div className="auth-note">Private workspace · Semantic search · Traceable evidence</div>
    <div className="auth-credit"><CreatorCredit/></div>
  </section><aside className="auth-art"><div className="art-topline"><span>THE CONNECTED WORKSPACE</span><Icon name="spark"/></div><div className="orbit orbit-one"/><div className="orbit orbit-two"/><div className="art-composition"><div className="floating-source source-one"><Icon name="files"/><span>Company handbook<small>Your team's collective knowledge</small></span><span className="source-check">✓</span></div><div className="art-document"><span className="demo-label">A LITTLE PREVIEW</span><div className="demo-question">What does our team know?</div><div className="demo-answer"><Icon name="spark"/><div>Bring the right knowledge<br/>into every conversation.</div></div><div className="demo-lines"><i/><i/><i/></div><span className="demo-citation"><Icon name="files"/> Connected to your sources</span></div><div className="floating-source source-two"><span className="source-check">✓</span>Every answer. A path to the source.</div></div><div className="art-caption">Less searching.<br/><em>More knowing.</em><span>Make room for your next great idea.</span></div><span className="art-edition">SOURCEBOARD — YOUR KNOWLEDGE STUDIO</span></aside></div>;

  const labels={ask:'Ask anything',library:'Source library',history:'Question history'};
  const titles={ask:'A little curiosity. A lot of clarity.',library:'Good knowledge starts here.',history:'Keep your train of thought.'};
  const descriptions={ask:'Explore your sources. Find the evidence. Move an idea forward.',library:'A considered collection of everything your workspace knows.',history:'Revisit your questions and the evidence behind each answer.'};
  const filteredDocuments=documents.filter(d=>d.name.toLowerCase().includes(filter.toLowerCase()));
  const ready=documents.filter(d=>d.status==='ready');
  return <div className="app"><a className="skip-link" href="#main-content">Skip to main content</a><aside className="sidebar">
    <div className="workspace"><span className="workspace-avatar">{user.workspace[0].toUpperCase()}</span><div><strong>{user.workspace}</strong><small>Company workspace</small></div></div>
    <div className="nav-label">YOUR WORKSPACE</div><nav aria-label="Workspace navigation">{(['ask','library','history'] as View[]).map((name,i)=><button key={name} className={`nav-item ${view===name?'active':''}`} aria-current={view===name?'page':undefined} onClick={()=>setView(name)}><Icon name={['spark','files','history'][i]}/>{labels[name]}{name==='library'&&<small>{documents.length}</small>}</button>)}</nav>
    <div className="sidebar-note"><div className="sidebar-note-icon"><Icon name="shield"/></div>Built on your knowledge<p>Your sources set the story. Every answer brings you back to the evidence.</p><span className="tiny-label">SOURCE-BACKED ANSWERS</span></div>
    <div className="profile"><span className="profile-avatar">{user.email[0].toUpperCase()}</span><div><strong>{user.email}</strong><small>Workspace owner</small></div><button onClick={logout} aria-label="Sign out"><Icon name="logout"/></button></div>
  </aside><main id="main-content" tabIndex={-1}><header><div><span className="muted">Workspace</span><span className="slash">/</span>{labels[view]}</div><div className="header-right"><span className="green-dot"/>Private workspace <span className="header-avatar">{user.workspace[0].toUpperCase()}</span></div><button className="mobile-logout text-button" onClick={logout}>Sign out</button></header>
    <div className="main-content"><div className="page-heading"><div><div className="eyebrow">{view==='ask'?'THE KNOWLEDGE STUDIO':view==='library'?'COLLECT. CONNECT. DISCOVER.':'THINKING, SAVED.'}</div><h1>{titles[view]}</h1><p>{descriptions[view]}</p></div><button className="primary" disabled={uploading||!user.provider_configured} onClick={()=>files.current?.click()}><Icon name="plus"/>{uploading?'Uploading…':'Add sources'}</button></div>
    {!user.provider_configured&&<div className="configuration-note" role="status">Your workspace is ready. Ask your administrator to connect an AI provider to enable uploads and answers.</div>}
    <section className="stats" aria-label="Workspace overview" aria-busy={documentsLoading}><div><span className="stat-icon"><Icon name="files"/></span><div><span className="stat-label">Knowledge sources</span><strong>{documentsLoading?'—':documents.length} <small>documents</small></strong></div></div><div><span className="stat-icon"><Icon name="layers"/></span><div><span className="stat-label">Searchable passages</span><strong>{documentsLoading?'—':ready.reduce((n,d)=>n+d.chunk_count,0)} <small>indexed</small></strong></div></div><div><span className="stat-icon"><Icon name="shield"/></span><div><span className="stat-label">Answer approach</span><strong className="stat-text">Grounded answers <span className="pill">With citations</span></strong></div></div></section>
    {documentsError&&<div className="inline-error source-error" role="alert"><strong>Sources could not be refreshed.</strong><p>{documentsError}</p><button className="text-button" onClick={()=>void refresh()}>Retry loading sources</button></div>}
    {view==='ask'&&<section><div className="ask-layout"><div className="conversation"><div className="panel-heading"><span className="panel-title"><Icon name="spark"/> Your thinking space</span>{asked?<button className="text-button" disabled={asking} onClick={()=>{setAsked('');setResult(null);setQuestion('');setAnswerError('');composer.current?.focus();}}>New question <span aria-hidden="true">＋</span></button>:<span className="subtle-tag"><span className="green-dot"/> Source grounded</span>}</div>
      {!asked?<><div className="welcome"><div className="sparkle"><Icon name="spark"/></div><div className="welcome-kicker">LET'S CONNECT THE DOTS</div><h2>Where will your curiosity take you?</h2><p>Ask in your own words. Find the relevant knowledge<br/>with the evidence right beside it.</p></div><div className="suggestions"><span className="tiny-label">A STARTING POINT, IF YOU NEED ONE</span><div className="suggestion-grid">{suggestions.map(q=><button key={q.question} onClick={()=>{setQuestion(q.question);composer.current?.focus();}}><Icon name={q.icon}/><span className="suggestion-label">{q.label}</span><span className="suggestion-question">{q.question}</span><span className="suggestion-arrow" aria-hidden="true">&#8599;</span></button>)}</div></div></>:<div><div className="question-bubble">{asked}</div><div className="answer-block" aria-live="polite" aria-busy={asking}>{asking?<p>Searching your documents and checking citations…</p>:result?<><h3>✧ &nbsp; {result.status==='answered'?'Source-backed answer':'Insufficient evidence'}</h3>{result.claims.length?result.claims.map((claim,i)=><div className="claim" key={i}><p>{claim.text}</p>{claim.evidence.map((e,j)=>{const source=result.sources.find(s=>s.id===e.source_id);return source&&<button className="citation" key={j} onClick={()=>setSelected(source)}>[{result.sources.indexOf(source)+1}] {source.name} · p. {source.page}</button>;})}</div>):<p>{result.answer}</p>}</>:<div className="inline-error" role="alert"><strong>We could not complete this answer.</strong><p>{answerError||'Please try again.'}</p><button className="text-button" onClick={()=>composer.current?.form?.requestSubmit()}>Retry question <Icon name="arrow"/></button></div>}</div></div>}
      <form id="question-form" onSubmit={ask}><div className="composer"><textarea disabled={asking} ref={composer} value={question} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing){e.preventDefault();e.currentTarget.form?.requestSubmit();}}} placeholder="Ask anything about your company knowledge…" rows={2} maxLength={2000} minLength={3} required aria-label="Your question"/><div className="composer-bottom"><span className="composer-sources"><Icon name="files"/> {ready.length} ready {ready.length===1?'source':'sources'}</span><button className="send" disabled={asking||!user.provider_configured||question.trim().length<3} aria-label="Ask question">↑</button></div></div><div className="composer-note"><span>Review cited evidence. AI answers can still contain mistakes.</span><span>Enter ↵</span></div></form>
    </div><aside className="evidence-panel"><div className="panel-heading">Source evidence <span className="count">{result?.sources.length||0}</span></div><div className="evidence-content">{result?.sources.length?result.sources.map((source,i)=><button className="evidence-card" key={source.id} onClick={()=>setSelected(source)}><strong><span className="citation">{i+1}</span> {source.name}</strong><p>{source.text.slice(0,180)}…</p><small>Page {source.page} · View passage ↗</small></button>):<><div className="evidence-empty"><div className="evidence-illustration"><Icon name="files"/><span><Icon name="search"/></span></div><h3>The proof is in the passage.</h3><p>Ask a question to see the sources<br/>that bring your answer to life.</p></div><div className="trust-card"><strong>Built to say “I don’t know”</strong><p>If the evidence does not support an answer, we’ll ask for more information.</p></div></>}</div></aside></div><div className="bottom-banner"><div className="banner-icon"><Icon name="layers"/></div><div><strong>Great answers start with great sources.</strong><p>Add policies, product docs, SOPs, and team knowledge.</p></div><button className="text-button" onClick={()=>setView('library')}>Manage sources →</button></div></section>}
    {view==='library'&&<section><div className={`dropzone ${dragging?'dragging':''}`} tabIndex={user.provider_configured?0:-1} role="button" aria-disabled={!user.provider_configured||uploading} aria-label="Upload documents" onClick={()=>{if(user.provider_configured&&!uploading)files.current?.click();}} onKeyDown={e=>{if(user.provider_configured&&!uploading&&(e.key==='Enter'||e.key===' ')){e.preventDefault();files.current?.click();}}} onDragOver={e=>{e.preventDefault();setDragging(true);}} onDragLeave={()=>setDragging(false)} onDrop={e=>{e.preventDefault();setDragging(false);upload(e.dataTransfer.files);}}><span className="upload-icon"><Icon name="upload"/></span><div className="eyebrow">YOUR NEXT GREAT ANSWER STARTS HERE</div><h2>Give your knowledge a home.</h2><p>{uploading?'Uploading documents…':'Drop files here or click to browse'}</p><small>PDF, TXT, Markdown, CSV · Up to 10 MB each · Text-based PDFs only</small></div><div className="table-panel"><div className="panel-heading">All sources<input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="Filter sources…" aria-label="Filter sources"/></div><div className="table-scroll"><table><caption className="sr-only">Workspace documents, indexing status, and file actions</caption><thead><tr><th>DOCUMENT</th><th>STATUS</th><th>PASSAGES</th><th>ADDED</th><th>ACTIONS</th></tr></thead><tbody>{filteredDocuments.map(doc=><tr key={doc.id}><td>▤ &nbsp; {doc.name}<small>{Math.max(1,Math.round(doc.size/1024))} KB{doc.pages>0&&` · ${doc.pages} pages`}</small>{doc.error&&<small className="error">{doc.error}</small>}</td><td><span className={`pill status-${doc.status}`}>{doc.status}</span></td><td>{doc.chunk_count}</td><td>{date(doc.created_at)}</td><td><div className="document-actions">{doc.status==='failed'&&<button className="text-button" onClick={()=>retry(doc)}>Retry</button>}{doc.status!=='deleting'&&<><a className="text-button" href={`/api/documents/${doc.id}/download`}>Download</a><button className="delete-button" onClick={()=>remove(doc)}>Delete</button></>}</div></td></tr>)}</tbody></table>{documentsLoading?<div className="list-loading" role="status"><span className="loading-orbit"/> Loading your sources...</div>:!documentsError&&!filteredDocuments.length&&<div className="empty-row"><Icon name="search"/><h3>{documents.length?'No matching sources':'A fresh start for your knowledge'}</h3><p>{documents.length?'Try a different file name or clear your filter.':'Upload a document to give your first answer something to build on.'}</p>{documents.length>0&&<button className="text-button" onClick={()=>setFilter('')}>Clear filter</button>}</div>}</div></div><p className="storage-note">Documents are processed in the background. Document text and questions are sent to your configured model provider.</p></section>}
    {view==='history'&&<section className="history-list" aria-busy={historyLoading}>{historyLoading?<div className="list-loading" role="status"><span className="loading-orbit"/> Loading your questions...</div>:historyError?<div className="inline-error" role="alert"><strong>History could not be loaded.</strong><p>{historyError}</p><button className="text-button" onClick={()=>void loadHistory()}>Retry history</button></div>:history.length?history.map(item=><button className="history-item" key={item.id} onClick={()=>{setAsked(item.question);setResult(item.result);setView('ask');}}><span className="history-symbol"><Icon name="chat"/></span><span className="history-copy"><strong>{item.question}</strong><small>{date(item.created_at)} &middot; {item.result.sources.length} sources &middot; {item.result.status==='answered'?'Answered':'Insufficient evidence'}</small></span><Icon name="arrow"/></button>):<div className="empty-row history-empty"><span className="sparkle"><Icon name="history"/></span><h2>Every good idea starts with a question.</h2><p>Your conversations will find a home here.<br/>Start with something you have been wondering about.</p><button className="primary" onClick={()=>setView('ask')}>Ask your first question <Icon name="arrow"/></button></div>}</section>}
    <footer><span className="workspace-privacy"><span className="green-dot"/>Source access is scoped to your workspace.</span><CreatorCredit/></footer></div>
  </main><input ref={files} type="file" accept=".pdf,.txt,.md,.csv" multiple hidden onChange={e=>upload(e.target.files)}/>{notice&&<div className="toast" role="status">{notice}</div>}
  <dialog aria-labelledby="source-title" ref={dialog} onClose={()=>setSelected(null)}><div className="dialog-heading"><h2 id="source-title">{selected?.name}</h2><button aria-label="Close source" onClick={()=>dialog.current?.close()}>×</button></div><span className="pill">Page {selected?.page} · Indexed passage</span><p id="source-text">{selected?.text}</p>{selected&&<a className="text-button" href={`/api/documents/${selected.document_id}/download`}>Download original document ↗</a>}</dialog>
  </div>;
}
