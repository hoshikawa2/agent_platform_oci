import { A2AClient, TaskView, displayResponse, isStopped, needsInput, selectVersion, stateName, uid } from './a2a-client.js';

const $ = id => document.getElementById(id);
const value = id => $(id).value.trim();
const labels = { submitted:'Tarefa recebida', working:'Agente trabalhando', completed:'Concluída', failed:'Falha no processamento', canceled:'Tarefa cancelada', rejected:'Solicitação recusada', 'input-required':'Aguardando sua resposta', 'auth-required':'Aguardando autorização' };
const eventLabels = { 'flow.start':'Fluxo iniciado', 'session.upserted':'Sessão preparada', 'message.received':'Mensagem recebida', 'workflow.started':'Workflow iniciado', 'workflow.completed':'Workflow concluído', 'message.responded':'Resposta disponível', 'flow.end':'Fluxo finalizado', 'a2a.backend.status':'Status do backend atualizado' };
const state = { client:null, card:null, contextId:uid(), view:new TaskView(), connected:false, busy:false, epoch:0, controller:null, turn:null, events:0, lastState:'', scope:null };
const savedKey = 'framework-a2a-session-v1';
const connectionFields = ['serviceUrl','target','version','skill','tenant','tracking','customerKey','contractKey','agentOverride','authHeader','authValue'];
const messageGroups = new Map();

function notice(text = '') { $('notice').textContent = text; $('notice').hidden = !text; }
function setStatus(text, kind = '') { $('taskStatus').textContent = text; $('taskDot').className = `dot ${kind}`; }
function setBusy(busy) { state.busy = busy; document.body.setAttribute('aria-busy', String(busy)); controls(); }
function controls() {
  const active = state.view.task.id && !isStopped(state.view.task.status?.state);
  const allowSend = state.connected && !state.busy && !active;
  $('message').disabled = !allowSend; $('sendButton').disabled = !allowSend;
  $('cancelButton').disabled = !state.connected || !(active || needsInput(state.view.task.status?.state));
  $('resumeButton').disabled = !state.connected || state.busy || !state.view.task.id;
  $('newConversation').disabled = state.busy;
  $('connectButton').disabled = state.busy;
  for (const id of connectionFields) $(id).disabled = state.busy;
}
function log(text) {
  const item = document.createElement('li');
  const time = document.createElement('time'); time.textContent = new Date().toLocaleTimeString('pt-BR');
  item.append(time, document.createTextNode(text)); $('activity').append(item);
  while ($('activity').children.length > 80) $('activity').firstChild.remove();
  $('eventCount').textContent = `${++state.events} eventos`;
}
function saveSession() {
  // Only identifiers and connection settings: no credentials or message content.
  try { sessionStorage.setItem(savedKey, JSON.stringify({
    serviceUrl: state.client?.urls.base, version:state.client?.version, target:value('target'),
    contextId:state.contextId, taskId:state.view.task.id, taskState:state.view.task.status?.state,
    tenant:value('tenant'), skill:value('skill'), agentOverride:value('agentOverride'),
  })); } catch { /* Storage can be unavailable in private browsing. */ }
}
function ids() {
  $('taskId').textContent = state.view.task.id || '—'; $('taskShort').textContent = state.view.task.id ? `#${state.view.task.id.slice(0,8)}` : '';
  $('contextId').textContent = state.contextId; $('contextShort').textContent = `Conversa ${state.contextId.slice(0,8)}`;
}
function stopWatcher() { ++state.epoch; state.controller?.abort(); state.controller = null; }
function newConversation() {
  stopWatcher(); state.contextId = uid(); state.view = new TaskView(); state.turn = null; state.lastState = ''; messageGroups.clear();
  $('chat').replaceChildren(); $('activity').replaceChildren(); state.events = 0; $('eventCount').textContent='0 eventos'; notice();
  setBusy(false); ids(); setStatus(state.connected ? 'Pronto para conversar' : 'Pronto para conectar'); saveSession(); $('message').focus();
}
function userMessage(text) {
  const div = document.createElement('div'); div.className='message user'; div.textContent=text;
  $('welcome')?.remove(); $('chat').append(div); scrollChat();
}
function agentMessages(response) {
  const metadata = response.metadata || {};
  const candidates = response.supervisor_results || metadata.supervisor_results || response.agent_responses || metadata.agent_responses;
  if (Array.isArray(candidates)) {
    const parts = candidates.map(p => ({ agent:p.agent || p.agent_id || p.name || 'Agente', text:p.answer ?? p.text ?? p.message ?? p.response ?? p.content, primary:p.primary }));
    const valid = parts.filter(p => p.text != null && String(p.text).trim());
    if (valid.length) return valid.sort((a,b)=>Number(Boolean(a.primary))-Number(Boolean(b.primary)));
  }
  const text = response.text ?? response.speak ?? response.content ?? '';
  return [{ agent:metadata.active_agent || metadata.agent_id || state.card?.name || 'Agente', text }];
}
function scrollChat() { $('chat').scrollTop = $('chat').scrollHeight; }
function renderResponse(response) {
  if (!response) return;
  $('welcome')?.remove(); state.turn ||= uid();
  let group = messageGroups.get(state.turn);
  if (!group) { group=document.createElement('section'); group.className='message agent'; group.setAttribute('aria-label','Resposta do agente'); messageGroups.set(state.turn,group); $('chat').append(group); }
  const signature=JSON.stringify(response); if (group.dataset.signature === signature) return;
  group.dataset.signature=signature; group.replaceChildren();
  for (const part of agentMessages(response)) {
    const section=document.createElement('section'); section.className='agent-section';
    const header=document.createElement('div'); header.className='agent-header';
    const avatar=document.createElement('span'); avatar.className='agent-avatar'; avatar.textContent='O'; avatar.setAttribute('aria-hidden','true');
    const name=document.createElement('span'); name.textContent=String(part.agent).replaceAll('_',' ');
    const body=document.createElement('div'); body.className='agent-body'; body.textContent=typeof part.text==='string' ? part.text : JSON.stringify(part.text,null,2);
    header.append(avatar,name); section.append(header,body); group.append(section);
  }
  scrollChat();
}
function updateTask(event) {
  const task=state.view.apply(event);
  if (task.contextId) state.contextId=task.contextId;
  const current=stateName(task.status?.state);
  if (current && current!==state.lastState) { log(labels[current] || current); state.lastState=current; }
  if (event.type==='status' && event.value.metadata?.framework_event) log(eventLabels[event.value.metadata.framework_event] || event.value.metadata.framework_event);
  setStatus(labels[current] || 'Acompanhando tarefa', ['failed','rejected'].includes(current) ? 'error' : isStopped(current) ? '' : 'busy');
  if (event.type==='artifact' || isStopped(current)) renderResponse(displayResponse(task));
  ids(); saveSession(); controls();
}
function sleep(ms,signal) {
  return new Promise((resolve,reject)=>{
    if (signal.aborted) { reject(new DOMException('Interrompido','AbortError')); return; }
    const abort=()=>{clearTimeout(timer);reject(new DOMException('Interrompido','AbortError'));};
    const timer=setTimeout(()=>{signal.removeEventListener('abort',abort);resolve();},ms);
    signal.addEventListener('abort',abort,{once:true});
  });
}
async function watchTask() {
  stopWatcher(); const epoch=state.epoch; const controller=new AbortController(); state.controller=controller;
  const signal=controller.signal; const id=state.view.task.id; setBusy(true);
  try {
    if (value('tracking')==='stream' && state.card?.capabilities?.streaming && !isStopped(state.view.task.status?.state)) {
      try {
        log('Conectando ao fluxo da tarefa');
        for await (const event of state.client.subscribe(id,signal)) {
          if (epoch!==state.epoch) return; updateTask(event);
          if (isStopped(state.view.task.status?.state)) break;
        }
      } catch (error) {
        if (signal.aborted) return;
        log('Fluxo interrompido; recuperando por consulta');
      }
    }
    // Always obtain the authoritative final snapshot; also recovers a fast Task
    // that completed before SubscribeToTask or a dropped/truncated SSE stream.
    let failures=0;
    while (true) {
      try {
        const task=await state.client.getTask(id,signal);
        if (epoch!==state.epoch) return;
        updateTask({type:'task',value:task}); failures=0;
        if (isStopped(task.status?.state)) break;
      } catch (error) {
        if (signal.aborted) return;
        if (++failures>=3 || error.code) throw error;
        log('Conexão indisponível; tentando consultar novamente');
      }
      await sleep(failures ? failures*1000 : 900,signal);
    }
  } catch (error) {
    if (!signal.aborted && epoch===state.epoch) {
      notice(`Acompanhamento pausado: ${error.message} Use Retomar para consultar a mesma tarefa. Nenhuma mensagem foi reenviada.`);
      setStatus('Acompanhamento pausado','error'); log('Acompanhamento pausado');
    }
  } finally {
    if (epoch===state.epoch) { setBusy(false); $('message').focus(); }
  }
}
function authHeaders() {
  const secret=$('authValue').value;
  if (!secret) return {};
  const name=value('authHeader');
  if (!/^[!#$%&'*+.^_`|~0-9A-Za-z-]+$/.test(name) || /[\r\n]/.test(secret)) throw new Error('Cabeçalho de autenticação inválido.');
  if (['content-type','accept','a2a-version','host','origin','cookie'].includes(name.toLowerCase())) throw new Error('Use Authorization ou o cabeçalho de autenticação configurado no serviço.');
  return {[name]:secret};
}
$('connectionForm').addEventListener('submit',async event=>{
  event.preventDefault(); notice(); setBusy(true); setStatus('Conectando…','busy');
  try {
    const candidate=new A2AClient({url:value('serviceUrl'),version:value('version')==='0.3'?'0.3':'1.0',headers:authHeaders()});
    const card=await candidate.discover(AbortSignal.timeout(12000)); candidate.version=selectVersion(card,value('version')); candidate.headers['A2A-Version']=candidate.version;
    const scope=JSON.stringify([candidate.urls.base,candidate.version,value('target'),value('tenant'),value('skill'),value('agentOverride')]);
    if (state.scope && scope!==state.scope) newConversation();
    state.scope=scope; state.client=candidate; state.card=card; state.connected=true;
    const previous=value('skill'); $('skill').replaceChildren(new Option('Seleção automática',''));
    for (const skill of card.skills || []) $('skill').append(new Option(skill.name || skill.id,skill.id));
    $('skill').value=[...$('skill').options].some(o=>o.value===previous)?previous:'';
    $('serviceName').textContent=card.name || 'Serviço A2A'; $('connectionDetail').textContent=`${(card.skills || []).length === 1 ? '1 opção disponível' : `${(card.skills || []).length} opções disponíveis`} · ${card.capabilities?.streaming ? 'Atualizações em tempo real' : 'Consulta de tarefas'}`;
    $('connectionDot').className='dot'; $('versionBadge').textContent=`A2A ${candidate.version}`;
    setStatus(state.view.task.id?'Conectado · tarefa disponível para consulta':'Pronto para conversar');
    log('Conectado ao serviço'); ids(); saveSession();
  } catch(error) {
    state.connected=false; $('connectionDot').className='dot error'; $('connectionDetail').textContent='Não foi possível conectar.';
    setStatus('Falha na conexão','error'); notice(`${error.message} Se o navegador bloquear a conexão, confira CORS_ORIGINS no serviço e use HTTP/HTTPS para servir esta página.`);
  } finally { setBusy(false); }
});
$('messageForm').addEventListener('submit',async event=>{
  event.preventDefault(); const text=value('message'); if(!text || !state.connected || $('sendButton').disabled) return;
  notice(); const previousTask=state.view.task; const resumeId=needsInput(previousTask.status?.state)?previousTask.id:undefined;
  state.turn=uid(); userMessage(text); $('message').value=''; $('message').style.height='auto'; setBusy(true); setStatus('Enviando mensagem…','busy');
  const messageId=uid();
  const business_context={customer_key:value('customerKey')||null,contract_key:value('contractKey')||null,interaction_key:messageId,session_key:state.contextId};
  const data={message_id:messageId,business_context,context:{business_context}};
  if(value('customerKey')) data.customer_key=value('customerKey');
  if(value('contractKey')) data.contract_key=value('contractKey');
  try {
    const gateway=value('target')==='gateway';
    const result=await state.client.sendMessage(text,{contextId:state.contextId,taskId:resumeId,tenantId:value('tenant')||'default',
      agentId:gateway?value('agentOverride'):value('skill'),backendId:gateway?value('skill'):undefined,data});
    if(result.type==='message') {
      state.view=new TaskView(); if(result.value.contextId) state.contextId=result.value.contextId;
      renderResponse(displayResponse(result.value)); setStatus('Resposta recebida'); ids(); saveSession(); setBusy(false);
    } else if(result.type==='task') {
      state.view=new TaskView(); state.lastState=''; updateTask(result); log(`Tarefa ${state.view.task.id.slice(0,8)} recebida`); await watchTask();
    } else throw new Error('Resposta de envio inesperada.');
  } catch(error) {
    notice(`Não foi possível confirmar o envio: ${error.message} Ele pode ter sido aceito pelo serviço; não houve reenvio automático.`);
    setStatus('Envio não confirmado','error'); setBusy(false);
  }
});
$('resumeButton').addEventListener('click',()=>{notice();state.turn ||= uid();watchTask();});
$('cancelButton').addEventListener('click',async()=>{
  const id=state.view.task.id; if(!id || !state.connected) return;
  stopWatcher(); setBusy(true); setStatus('Solicitando cancelamento…','busy');
  try { updateTask({type:'task',value:await state.client.cancelTask(id)});log('Cancelamento confirmado pelo serviço');notice(); }
  catch(error) {
    try {updateTask({type:'task',value:await state.client.getTask(id)});} catch { /* Keep the last known Task. */ }
    notice(`O serviço não confirmou o cancelamento: ${error.message} Consulte a tarefa com Retomar.`);
  } finally {setBusy(false);}
});
$('newConversation').addEventListener('click',newConversation);
$('message').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey&&!event.isComposing){event.preventDefault();$('messageForm').requestSubmit();}});
$('message').addEventListener('input',()=>{ $('message').style.height='auto';$('message').style.height=`${Math.min($('message').scrollHeight,150)}px`; });
for(const button of document.querySelectorAll('[data-prompt]')) button.addEventListener('click',()=>{if(!$('message').disabled){$('message').value=button.dataset.prompt;$('message').focus();}else notice('Conecte ao serviço para iniciar a conversa.');});
$('target').addEventListener('change',()=>{ $('skillLabel').firstChild.textContent=value('target')==='gateway'?'Backend no Gateway':'Agente'; });
for(const id of ['serviceUrl','version','target','tenant','skill','agentOverride','authHeader','authValue']) $(id).addEventListener('change',()=>{
  if(state.connected){state.connected=false;$('connectionDot').className='dot muted';setStatus('Configuração alterada · conecte novamente');controls();}
});
try {
  const saved=JSON.parse(sessionStorage.getItem(savedKey)||'null');
  if(saved?.serviceUrl){
    $('serviceUrl').value=saved.serviceUrl;$('version').value=saved.version||'auto';$('target').value=saved.target||'backend';$('tenant').value=saved.tenant||'default';$('agentOverride').value=saved.agentOverride||'';
    if(saved.skill)$('skill').append(new Option(saved.skill,saved.skill));$('skill').value=saved.skill||'';
    state.contextId=saved.contextId||uid();state.view=new TaskView(saved.taskId?{id:saved.taskId,contextId:state.contextId,status:{state:saved.taskState}}:{});
    state.scope=JSON.stringify([saved.serviceUrl,saved.version,saved.target||'backend',saved.tenant||'default',saved.skill||'',saved.agentOverride||'']);
    if(saved.taskId)notice('Uma tarefa desta aba está disponível. Conecte ao mesmo serviço e clique em Retomar para consultar o resultado.');
  }
} catch { /* An unavailable or invalid saved session starts a fresh conversation. */ }
const requestedService=new URLSearchParams(location.search).get('service');
if(requestedService)$('serviceUrl').value=requestedService;
else if(!state.scope && location.port==='8000')$('serviceUrl').value=location.origin;
$('target').dispatchEvent(new Event('change'));ids();controls();
