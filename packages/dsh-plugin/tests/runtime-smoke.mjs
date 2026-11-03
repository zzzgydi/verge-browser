import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
const config = JSON.parse(process.env.VERGE_DSH_CONFIG);
const engine = process.env.VERGE_SMOKE_ENGINE;
const url = process.env.VERGE_SMOKE_URL;
const transport = new StdioClientTransport({ command: process.execPath, args: [process.env.VERGE_DSH_BRIDGE ?? 'dist/bridge.js'],
  env: { ...process.env }, stderr: 'pipe' });
let errors = ''; transport.stderr?.on('data', chunk => errors += chunk);
const client = new Client({ name: 'runtime-smoke', version: '1' });
async function call(name, args = {}) {
 const result = await client.callTool({ name, arguments: args }, undefined, { timeout: 60_000 });
 assert(!result.isError, JSON.stringify(result));return result;
}
try {
 await client.connect(transport);
 const tools = (await client.listTools()).tools.map(t=>t.name);
 assert(tools.includes(engine === 'camoufox' ? 'verge_snapshot' : 'browser_snapshot'));
 const nav = engine === 'camoufox' ? 'verge_open' : 'browser_navigate';
 const snap = engine === 'camoufox' ? 'verge_snapshot' : 'browser_snapshot';
 await call(nav,{url});
 let snapshot = await call(snap);
 let text = snapshot.structuredContent?.snapshot ?? snapshot.content.filter(b=>b.type==='text').map(b=>b.text).join('\n');
 let match = text.match(/textbox "Name"[^\n]*?\[ref=(@?(?:f\d+)?e\d+)\]/);
 assert(match, text);
 const ref = match[1];
 if(engine === 'camoufox') await call('verge_fill',{ref,text:'DSH'});
 else await call('browser_type',{target:ref,text:'DSH',element:'Name'});
 snapshot=await call(snap);text=snapshot.structuredContent?.snapshot ?? snapshot.content.filter(b=>b.type==='text').map(b=>b.text).join('\n');
 match=text.match(/Save state[^\n]*?\[ref=(@?(?:f\d+)?e\d+)\]/);assert(match,text);
 await call(engine === 'camoufox' ? 'verge_click':'browser_click',engine==='camoufox'?{ref:match[1]}:{target:match[1],element:'Save state'});
 snapshot=engine === 'camoufox' ? await call('verge_text',{target:'#result'}) : await call(snap);
 assert(JSON.stringify(snapshot).includes('saved:DSH trusted:true'),JSON.stringify(snapshot));
 const shot=await call('verge_screenshot',{type:'window'});
 assert(shot.content.some(b=>b.type==='image' && Buffer.from(b.data,'base64').subarray(0,8).toString('hex')==='89504e470d0a1a0a'));
 await call('verge_file_write',{path:'/workspace/dsh-smoke.txt',content:'DSH file'});
 assert(JSON.stringify(await call('verge_file_read',{path:'/workspace/dsh-smoke.txt'})).includes('DSH file'));
 const handoff=await call('verge_handoff');
 const sessionUrl=handoff.structuredContent.url;
 const entry=await fetch(sessionUrl,{redirect:'manual'});
 assert.equal(entry.status,302);
 const cookie=entry.headers.get('set-cookie').split(';')[0];
 const session=await fetch(new URL(entry.headers.get('location'),sessionUrl),{headers:{cookie}});
 assert(session.ok,`Session page status ${session.status}`);
 assert.equal((await fetch(sessionUrl,{redirect:'manual'})).status,403);
 assert((await client.callTool({name:snap,arguments:{}})).isError);
 // A separate operator changes the real X11 window while bridge tools are blocked.
 const metadata=JSON.parse(shot.content[0].text);
 const gui=await fetch(`${config.baseUrl}/sandbox/${config.sandbox}/browser/actions`,{
   method:'POST',headers:{authorization:`Bearer ${config.token}`,'content-type':'application/json'},
   body:JSON.stringify({actions:[{type:'CLICK',x:90,y:metadata.height-42}]}),
 });
 assert(gui.ok);assert((await gui.json()).data.ok);
 await call('verge_resume');
 await call(snap);
 assert(JSON.stringify(engine === 'camoufox' ? await call('verge_text',{target:'#result'}) : await call(snap)).includes('gui-click trusted:true'));
 console.log(JSON.stringify({engine,tools:tools.length,nativeClick:true,png:true,files:true,handoff:true,resume:true}));
} finally { await client.close(); if(errors) console.error(errors.replace(/https?:\/\/\S+/g,'[URL]')); }
