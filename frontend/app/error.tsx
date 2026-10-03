'use client';

export default function ErrorPage({reset}:{reset:()=>void}) {
  return <main className="route-error"><section className="connection-error" role="alert">
    <div className="eyebrow">SOURCEBOARD</div>
    <h1>Let's get you back on track.</h1>
    <p>This screen could not be displayed. Try loading it again.</p>
    <button className="primary" onClick={reset}>Try again</button>
  </section></main>;
}
