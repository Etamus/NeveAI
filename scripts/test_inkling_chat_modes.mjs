// Opt-in integration test: same socket events the chat renders, no saved chats.
import assert from 'node:assert/strict';
import {randomUUID} from 'node:crypto';
import {io} from 'socket.io-client';
const base='http://127.0.0.1:8080',filename='Inkling-2-Mini-UD-Q4_K_XL.gguf',model='local/'+filename.slice(0,-5);
async function api(path,data){
	const r=await fetch(base+path,data?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}:{});
	assert(r.ok,await r.clone().text());return r.json();
}
assert.deepEqual((await api('/api/tasks')).tasks,[]);
const state=await api('/llamacpp/media-state');
assert(!state.busy && state.loaded_models.every(m=>m.id===model));
const needsLoad=!state.loaded_models.length;
const {token}=await api('/api/v1/auths/');
const socket=io(base,{path:'/ws/socket.io',auth:{token},transports:['websocket'],autoConnect:false});
if(needsLoad)await api('/llamacpp/models/load',{filename});
try{
	await api('/api/models');
	await new Promise((res,rej)=>{socket.once('connect',res);socket.once('connect_error',rej);socket.connect()});
	let failures=0;
	for(const mode of (process.env.INKLING_LANDING_ONLY?['landing']:['quick','reasoning','followup','landing'])){
		const quick=mode==='quick',id=randomUUID(),parent_id=randomUUID(),chat_id='local:'+randomUUID();
		const prompt=mode==='landing'?'Fa\u00e7a uma landing page .html sobre batata':'Responda em uma palavra: qual a capital da Fran\u00e7a?';
		let last='',done=false;
		const receive=e=>{if(e.message_id===id && e.data?.type==='chat:completion'){const d=e.data.data;if(d.content!=null)last=d.content;if(d.done)done=true;}};
		socket.on('events',receive);
		const messages=[{role:'user',content:prompt}];
		if(mode==='followup'||mode==='landing')messages.unshift({role:'user',content:'Bom dia'},{role:'assistant',content:'<|content_thinking|>Answer in Portuguese.<|end_message|>Bom dia!'});
		await api('/api/chat/completions',{model,id,chat_id,parent_id,session_id:socket.id,stream:true,messages,features:{},parent_message:{id:parent_id,role:'user',content:prompt},params:{reasoning_mode:quick?'quick':'reasoning',no_think:quick,reasoning_extended:true,temperature:0,seed:42,max_tokens:mode==='landing'?1600:512}});
		const end=Date.now()+240000;while(!done&&Date.now()<end)await new Promise(r=>setTimeout(r,120));
		socket.off('events',receive);
		const answer=last.replace(/<details\b[\s\S]*?<\/details>/gi,'').trim();
		const leaked=/<\|(?:content_thinking|end_message)\|>/.test(last);
		const ok=done&&!leaked&&(mode==='landing'?/<html\b/i:/Paris/i).test(answer)&&(quick?!last.includes('<details'):last.includes('<details'));
		console.log(JSON.stringify({mode,done,answerLength:answer.length,leaked,hasReasoning:last.includes('<details'),ok}));
		if(!ok)failures++;
	}
	assert.equal(failures,0);
}finally{
	socket.disconnect();if(needsLoad)await api('/llamacpp/models/unload',{model_id:model});
}
