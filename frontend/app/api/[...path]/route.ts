import { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

async function proxy(request: NextRequest, context: {params: Promise<{path:string[]}>}) {
  const {path} = await context.params;
  const limit = path.length===1 && path[0]==='documents' ? 11*1024*1024 : 32*1024;
  if (Number(request.headers.get('content-length') || 0)>limit)
    return Response.json({detail:'Request too large.'},{status:413});
  const headers=new Headers();
  for (const name of ['cookie','content-type','origin','x-sourceboard']) {
    const value=request.headers.get(name);
    if(value) headers.set(name,value);
  }
  // This is a fixed-destination proxy; user input cannot choose a host.
  const target=(process.env.API_INTERNAL_URL || 'http://127.0.0.1:8000')+'/api/'+path.map(encodeURIComponent).join('/');
  try {
    let body: Uint8Array | undefined;
    if (!['GET','HEAD'].includes(request.method)) {
      const reader=request.body?.getReader();
      if(reader){
        const chunks: Uint8Array[]=[];
        let length=0;
        while(true){const next=await reader.read();if(next.done)break;length+=next.value.length;
          if(length>limit){await reader.cancel();return Response.json({detail:'Request too large.'},{status:413});}
          chunks.push(next.value);
        }
        body=new Uint8Array(length);let offset=0;for(const chunk of chunks){body.set(chunk,offset);offset+=chunk.length;}
      }
    }
    const upstream=await fetch(target,{method:request.method,headers,body:body as BodyInit | undefined,cache:'no-store',redirect:'manual',signal:AbortSignal.timeout(300000)});
    const outgoing=new Headers({'Cache-Control':'no-store'});
    for(const name of ['content-type','content-disposition','set-cookie']){
      const value=upstream.headers.get(name);if(value)outgoing.set(name,value);
    }
    return new Response(upstream.body,{status:upstream.status,headers:outgoing});
  } catch {
    return Response.json({detail:'The API is unavailable. Check that the backend services are running.'},{status:503});
  }
}
export {proxy as GET, proxy as POST, proxy as DELETE};
