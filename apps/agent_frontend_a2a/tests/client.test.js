import test from 'node:test';
import assert from 'node:assert/strict';
import { A2AClient, TaskView, displayResponse, parseSSE, serviceURLs, selectVersion, normalizeResult, isStopped, needsInput, RpcError } from '../a2a-client.js';

function bodyFor(text, size = 1) {
  const bytes=new TextEncoder().encode(text);
  return new ReadableStream({start(controller){for(let i=0;i<bytes.length;i+=size)controller.enqueue(bytes.slice(i,i+size));controller.close();}});
}

test('SSE handles fragmented UTF-8, CRLF, comments and multi-line data',async()=>{
  const text=': ping\r\nid: 1\r\nevent: message\r\ndata: {"text":\r\ndata: "Olá 👋"}\r\n\r\ndata: second\n\n';
  const frames=[];for await(const frame of parseSSE(bodyFor(text)))frames.push(frame);
  assert.deepEqual(frames,['{"text":\n"Olá 👋"}','second']);
});
test('SSE discards an unfinished frame for recovery by GetTask',async()=>{
  const frames=[];for await(const frame of parseSSE(bodyFor('data: complete\n\ndata: truncated')))frames.push(frame);
  assert.deepEqual(frames,['complete']);
});
test('service URLs accept a base or /a2a and reject embedded credentials',()=>{
  assert.equal(serviceURLs('http://localhost:8000/a2a/').rpc,'http://localhost:8000/a2a');
  assert.equal(serviceURLs('https://host/prefix').card,'https://host/prefix/.well-known/agent-card.json');
  for(const url of ['javascript:alert(1)','https://user:secret@host','https://host?token=secret'])assert.throws(()=>serviceURLs(url));
});
test('version selection uses JSONRPC interfaces and allows explicit legacy compatibility',()=>{
  assert.equal(selectVersion({supportedInterfaces:[{protocolBinding:'JSONRPC',protocolVersion:'1.0'}]}),'1.0');
  assert.equal(selectVersion({protocolVersion:'0.3.0'}),'0.3');
  assert.equal(selectVersion({},'0.3'),'0.3');
  assert.throws(()=>selectVersion({supportedInterfaces:[{protocolBinding:'GRPC',protocolVersion:'1.0'}]}));
});
test('both versions normalize task, message and streaming events',()=>{
  assert.equal(normalizeResult({statusUpdate:{taskId:'t'}}).type,'status');
  assert.equal(normalizeResult({kind:'artifact-update',taskId:'t'}).type,'artifact');
  assert.equal(normalizeResult({message:{messageId:'m'}}).type,'message');
  assert.throws(()=>normalizeResult({unexpected:true}));
});
test('TaskView updates status, replaces snapshots and appends artifact chunks',()=>{
  const view=new TaskView({id:'t',artifacts:[]});
  view.apply({type:'artifact',value:{taskId:'t',artifact:{artifactId:'a',parts:[{text:'Hel'}]}}});
  view.apply({type:'artifact',value:{taskId:'t',append:true,artifact:{artifactId:'a',parts:[{text:'lo'}]}}});
  assert.equal(displayResponse(view.task).text,'Hello');
  view.apply({type:'status',value:{taskId:'t',contextId:'c',status:{state:'TASK_STATE_COMPLETED'}}});
  assert.ok(isStopped(view.task.status.state));assert.ok(needsInput('input-required'));
  assert.throws(()=>view.apply({type:'status',value:{taskId:'other',status:{state:'working'}}}));
});
test('framework text/data duplicates render once and native agent metadata survives',()=>{
  const native={text:'answer',metadata:{agent_responses:[{agent:'billing',text:'answer'}]}};
  const task={artifacts:[{parts:[{text:'answer'},{data:native}]}],status:{message:{parts:[{text:'answer'}]}}};
  assert.deepEqual(displayResponse(task),native);
  const wrapped={parts:[{data:{text:'answer',metadata:{a2a_result:{task}}}}]};
  assert.deepEqual(displayResponse(wrapped),native);
});
for(const legacy of [false,true]){
  test(`send/get/cancel use correct envelopes and credentials (${legacy?'0.3':'1.0'})`,async()=>{
    const requests=[];
    const fetchImpl=async function(url,options){
      assert.equal(this,globalThis);
      const body=JSON.parse(options.body);requests.push({url,options,body});
      return Response.json({jsonrpc:'2.0',id:body.id,result:body.method.includes('send')||body.method==='SendMessage' ? (legacy?{kind:'task',id:'t',status:{state:'working'}}:{task:{id:'t',status:{state:'TASK_STATE_WORKING'}}}):{id:'t'}});
    };
    const client=new A2AClient({url:'https://service',version:legacy?'0.3':'1.0',headers:{Authorization:'Bearer test'},fetchImpl});
    await client.sendMessage('hello',{contextId:'c',agentId:'a',backendId:'billing',tenantId:'tenant',data:{business_context:{customer_key:'customer'}}});
    await client.getTask('t');await client.cancelTask('t');
    assert.deepEqual(requests.map(r=>r.body.method),legacy?['message/send','tasks/get','tasks/cancel']:['SendMessage','GetTask','CancelTask']);
    const params=requests[0].body.params;
    assert.equal(params.message.role,legacy?'user':'ROLE_USER');assert.equal(params.message.metadata.backend_id,'billing');
    assert.equal(params.message.metadata.agent_id,'a');assert.equal(params.message.contextId,'c');
    assert.equal(legacy?params.configuration.blocking:params.configuration.returnImmediately,!legacy);
    assert.equal(requests[0].options.headers.Authorization,'Bearer test');
    assert.equal(requests[0].options.credentials,'omit');
  });
}
test('JSON-RPC errors and mismatched response IDs never become successful responses',async()=>{
  const bad=new A2AClient({url:'https://service',fetchImpl:async()=>Response.json({jsonrpc:'2.0',id:'wrong',result:{}})});
  await assert.rejects(bad.getTask('t'),/JSON-RPC/);
  const failure=new A2AClient({url:'https://service',fetchImpl:async(url,o)=>Response.json({jsonrpc:'2.0',id:JSON.parse(o.body).id,error:{code:-32001,message:'Task missing'}})});
  await assert.rejects(failure.getTask('t'),RpcError);
});
test('POST SSE supports auth headers, validates envelopes and streams canonical events',async()=>{
  const client=new A2AClient({url:'https://service',headers:{'x-api-key':'test'},fetchImpl:async(url,o)=>{
    assert.equal(o.method,'POST');assert.equal(o.headers['x-api-key'],'test');
    const body=JSON.parse(o.body);assert.equal(body.method,'SubscribeToTask');
    return new Response(bodyFor(`data: ${JSON.stringify({jsonrpc:'2.0',id:body.id,result:{statusUpdate:{taskId:'t',status:{state:'TASK_STATE_COMPLETED'}}}})}\n\n`),{headers:{'content-type':'text/event-stream'}});
  }});
  const events=[];for await(const event of client.subscribe('t'))events.push(event);
  assert.equal(events[0].type,'status');assert.equal(events[0].value.taskId,'t');
});
