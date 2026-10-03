'use client';

import {useEffect, useState} from 'react';

export default function AnimatedBackdrop() {
  const [paused,setPaused]=useState(false);
  const [reduced,setReduced]=useState(false);
  useEffect(()=>{
    const media=window.matchMedia('(prefers-reduced-motion: reduce)');
    const sync=()=>setReduced(media.matches);
    sync();media.addEventListener('change',sync);
    try{setPaused(localStorage.getItem('background-motion')==='paused');}catch{}
    return()=>media.removeEventListener('change',sync);
  },[]);
  function toggle(){
    const next=!paused;setPaused(next);
    try{localStorage.setItem('background-motion',next?'paused':'playing');}catch{}
  }
  return <>
    <div className={`ambient-background ${paused?'motion-paused':''}`} aria-hidden="true">
      <div className="ambient-layer ambient-layer-one">
        <span className="ambient-halo"/>
        <svg className="ambient-cube" viewBox="0 0 200 220" fill="none"><path d="m100 10 85 49v100l-85 49-85-49V59l85-49Zm0 98 85-49M100 108 15 59m85 49v100"/></svg>
      </div>
      <div className="ambient-layer ambient-layer-two">
        <span className="ambient-ring"/><span className="ambient-dot"/>
        <svg className="ambient-diamond" viewBox="0 0 100 100" fill="none"><path d="m50 5 45 45-45 45L5 50 50 5Z"/></svg>
      </div>
    </div>
    {!reduced&&<button className="motion-control" onClick={toggle} aria-pressed={paused} aria-label={paused?'Resume background animation':'Pause background animation'}>
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">{paused?<path d="m6 3 10 7-10 7V3Z"/>:<path d="M7 4v12M13 4v12"/>}</svg>
      <span>{paused?'Motion paused':'Pause motion'}</span>
    </button>}
  </>;
}
