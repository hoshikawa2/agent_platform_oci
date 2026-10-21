// Run against examples/a2a_frontend_demo.py with A2A_DEMO_URL=http://127.0.0.1:8765.
import test from 'node:test';
import assert from 'node:assert/strict';
import { A2AClient, TaskView, displayResponse, isStopped, stateName } from '../a2a-client.js';
const url=process.env.A2A_DEMO_URL;
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function complete(client,task){
  const deadline=Date.now()+6000;
  while(!isStopped(task.status?.state)&&Date.now()<deadline){await delay(50);task=await client.getTask(task.id);}
  assert.ok(isStopped(task.status?.state));return task;
}
for(const version of ['1.0','0.3']){
  test(`SDK integration: submit, subscribe, poll and resume (${version})`,{skip:!url},async()=>{
    const client=new A2AClient({url,version});const card=await client.discover();assert.ok(card.capabilities.streaming);
    const first=await client.sendMessage('hello',{contextId:crypto.randomUUID()});assert.equal(first.type,'task');assert.ok(!isStopped(first.value.status.state));
    const view=new TaskView(first.value);let count=0;
    for await(const event of client.subscribe(first.value.id)){view.apply(event);count++;}
    assert.ok(count>0);const final=await client.getTask(first.value.id);
    assert.equal(stateName(final.status.state),'completed');assert.match(displayResponse(final).text,/hello/);
    const prompt=await client.sendMessage('/confirmar',{contextId:crypto.randomUUID()});
    const waiting=await complete(client,prompt.value);assert.equal(stateName(waiting.status.state),'input-required');
    const resumed=await client.sendMessage('sim',{contextId:waiting.contextId,taskId:waiting.id});
    const finished=await complete(client,resumed.value);assert.equal(finished.id,waiting.id);assert.equal(stateName(finished.status.state),'completed');
  });
}
test('SDK integration: cancellation and failed tasks',{skip:!url},async()=>{
  const client=new A2AClient({url});
  const slow=await client.sendMessage('/lento',{contextId:crypto.randomUUID()});
  await delay(50);const canceled=await client.cancelTask(slow.value.id);assert.equal(stateName(canceled.status.state),'canceled');
  const failed=await client.sendMessage('/erro',{contextId:crypto.randomUUID()});
  assert.equal(stateName((await complete(client,failed.value)).status.state),'failed');
});
