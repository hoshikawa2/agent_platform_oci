export const uid = () => globalThis.crypto.randomUUID();
export const stateName = (state = '') => state.replace(/^TASK_STATE_/, '').toLowerCase().replaceAll('_', '-');
export const isStopped = state => ['completed', 'failed', 'canceled', 'rejected', 'input-required', 'auth-required'].includes(stateName(state));
export const needsInput = state => ['input-required', 'auth-required'].includes(stateName(state));

export class RpcError extends Error {
  constructor(error) { super(error.message || 'O serviço retornou um erro.'); this.name = 'RpcError'; this.code = error.code; }
}
export function serviceURLs(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('Informe uma URL HTTP ou HTTPS sem credenciais, parâmetros ou fragmentos.');
  const base = url.href.replace(/\/$/, '').replace(/\/a2a$/, '');
  return { base, rpc: `${base}/a2a`, card: `${base}/.well-known/agent-card.json` };
}
export function normalizeResult(result) {
  if (!result || typeof result !== 'object') throw new Error('Resposta A2A inválida.');
  for (const [key, type] of [['task','task'], ['message','message'], ['statusUpdate','status'], ['artifactUpdate','artifact']]) {
    if (result[key]) return { type, value: result[key] };
  }
  const kinds = { task: 'task', message: 'message', 'status-update': 'status', 'artifact-update': 'artifact' };
  if (kinds[result.kind]) return { type: kinds[result.kind], value: result };
  throw new Error('O serviço não retornou uma mensagem, tarefa ou evento A2A reconhecido.');
}
export function selectVersion(card, preference = 'auto') {
  if (preference !== 'auto') return preference;
  const versions = (card.supportedInterfaces || []).filter(i => i.protocolBinding === 'JSONRPC').map(i => i.protocolVersion);
  if (versions.some(v => /^1\./.test(v))) return '1.0';
  if (/^0\.3/.test(card.protocolVersion || '') || versions.some(v => /^0\.3/.test(v))) return '0.3';
  throw new Error('O Agent Card não anuncia A2A 1.0 ou 0.3 por JSON-RPC.');
}

// SSE over POST/fetch supports authentication headers and both A2A versions.
export async function* parseSSE(body) {
  if (!body) throw new Error('O serviço não abriu o fluxo de eventos.');
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', data = [], size = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      while (true) {
        const end = buffer.search(/[\r\n]/);
        if (end < 0 || (!done && buffer[end] === '\r' && end === buffer.length - 1)) break;
        const line = buffer.slice(0, end);
        buffer = buffer.slice(end + (buffer.slice(end, end + 2) === '\r\n' ? 2 : 1));
        if (!line) {
          if (data.length) yield data.join('\n');
          data = []; size = 0;
        } else if (line.startsWith('data:')) {
          const entry = line.slice(5).replace(/^ /, '');
          data.push(entry); size += entry.length;
        }
        if (size > 4 * 1024 * 1024) throw new Error('Evento recebido excedeu o limite de tamanho.');
      }
      if (buffer.length > 4 * 1024 * 1024) throw new Error('Evento recebido excedeu o limite de tamanho.');
      if (done) break; // A partial frame is not an event; the caller can recover with GetTask.
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export class A2AClient {
  constructor({ url, version = '1.0', headers = {}, fetchImpl = globalThis.fetch }) {
    this.urls = serviceURLs(url); this.version = version; this.fetch = fetchImpl.bind(globalThis);
    this.headers = { ...headers, 'A2A-Version': version };
  }
  method(v1, v03) { return this.version === '0.3' ? v03 : v1; }
  async discover(signal) {
    const response = await this.fetch(this.urls.card, { headers: this.headers, credentials: 'omit', signal });
    if (!response.ok) throw new Error(`Não foi possível carregar o Agent Card (HTTP ${response.status}).`);
    return response.json();
  }
  async rpc(method, params, { signal, timeoutMs = 15000 } = {}) {
    const id = uid();
    const timeout = AbortSignal.timeout(timeoutMs);
    const response = await this.fetch(this.urls.rpc, {
      method: 'POST', headers: { ...this.headers, 'Content-Type': 'application/json' }, credentials: 'omit',
      body: JSON.stringify({ jsonrpc: '2.0', id, method, params }),
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
    });
    if (!response.ok) throw new Error(`O serviço retornou HTTP ${response.status}. Confira o endereço e a autenticação.`);
    const data = await response.json();
    return this.validate(data, id);
  }
  validate(data, id) {
    if (data.jsonrpc !== '2.0' || data.id !== id) throw new Error('Resposta JSON-RPC inválida.');
    if (data.error) throw new RpcError(data.error);
    if (!Object.hasOwn(data, 'result')) throw new Error('Resposta sem resultado A2A.');
    return data.result;
  }
  async sendMessage(text, { contextId, taskId, tenantId, agentId, backendId, data = {}, signal } = {}) {
    const legacy = this.version === '0.3';
    const message = {
      messageId: uid(), role: legacy ? 'user' : 'ROLE_USER', contextId,
      parts: [{ text }, { data }], metadata: {},
    };
    if (taskId) message.taskId = taskId;
    for (const [key, value] of Object.entries({ tenant_id: tenantId, agent_id: agentId, backend_id: backendId })) {
      if (value) message.metadata[key] = value;
    }
    if (legacy) {
      message.kind = 'message'; message.parts[0].kind = 'text'; message.parts[1].kind = 'data';
    }
    const result = await this.rpc(this.method('SendMessage', 'message/send'), {
      message, configuration: legacy ? { blocking: false } : { returnImmediately: true },
    }, { signal });
    return normalizeResult(result);
  }
  async getTask(id, signal) { return this.rpc(this.method('GetTask', 'tasks/get'), { id }, { signal }); }
  async cancelTask(id) { return this.rpc(this.method('CancelTask', 'tasks/cancel'), { id }); }
  async *subscribe(id, signal) {
    const requestId = uid();
    const response = await this.fetch(this.urls.rpc, {
      method: 'POST', credentials: 'omit', signal,
      headers: { ...this.headers, 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ jsonrpc: '2.0', id: requestId, method: this.method('SubscribeToTask', 'tasks/resubscribe'), params: { id } }),
    });
    if (!response.ok) throw new Error(`Não foi possível acompanhar os eventos (HTTP ${response.status}).`);
    if (!(response.headers.get('content-type') || '').includes('text/event-stream')) {
      this.validate(await response.json(), requestId);
      throw new Error('O serviço não retornou um fluxo SSE.');
    }
    for await (const frame of parseSSE(response.body)) {
      yield normalizeResult(this.validate(JSON.parse(frame), requestId));
    }
  }
}

export class TaskView {
  constructor(task = {}) { this.task = structuredClone(task); this.task.artifacts ||= []; }
  apply(event) {
    const value = event.value;
    if (event.type === 'task') {
      if (this.task.id && value.id !== this.task.id) throw new Error('Evento de outra tarefa.');
      this.task = structuredClone(value); this.task.artifacts ||= [];
    }
    else if (event.type === 'status') {
      if (this.task.id && value.taskId !== this.task.id) throw new Error('Evento de outra tarefa.');
      this.task.id = value.taskId; this.task.contextId = value.contextId; this.task.status = value.status;
    } else if (event.type === 'artifact') {
      if (this.task.id && value.taskId !== this.task.id) throw new Error('Evento de outra tarefa.');
      const index = this.task.artifacts.findIndex(a => a.artifactId === value.artifact.artifactId);
      if (index < 0) this.task.artifacts.push(structuredClone(value.artifact));
      else if (value.append) this.task.artifacts[index].parts.push(...structuredClone(value.artifact.parts || []));
      else this.task.artifacts[index] = structuredClone(value.artifact);
    }
    return this.task;
  }
}

export function displayResponse(value, depth = 0) {
  if (!value || depth > 5) return null;
  const task = value.task || value;
  const parts = task.artifacts?.at(-1)?.parts || task.status?.message?.parts || value.message?.parts || value.parts || [];
  const native = parts.find(p => p.data && typeof p.data === 'object' && ('text' in p.data || 'speak' in p.data || 'metadata' in p.data))?.data;
  if (native) {
    const remote = native.metadata?.a2a_result;
    return (remote && displayResponse(remote, depth + 1)) || native;
  }
  const text = parts.filter(p => typeof p.text === 'string').map(p => p.text).join('');
  if (text) return { text };
  const structured = parts.filter(p => 'data' in p).map(p => p.data);
  return structured.length ? { text: JSON.stringify(structured.length === 1 ? structured[0] : structured, null, 2) } : null;
}
