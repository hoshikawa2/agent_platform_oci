const chat = document.getElementById("chat");
const form = document.getElementById("form");
let eventSource = null;
let currentSessionId = null;
const renderedResponses = new Set();

function status(text) { const el = document.getElementById("status"); if (el) el.textContent = text; }
function val(id) { return (document.getElementById(id)?.value || "").trim(); }
function uuid() { return crypto.randomUUID(); }
function humanizeAgentName(value) {
  return String(value || "agent").trim().replace(/([a-zà-ÿ])([A-Z])/g, "$1 $2").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function responseText(value) {
  if (typeof value === "string") return value;
  if (value == null) return "";
  return JSON.stringify(value, null, 2);
}
function splitTaggedAgentMessages(value) {
  const text = responseText(value).trim();
  if (!text) return [];
  const marker = /^\[([^\]\r\n]*Agent)\]\s*/gim;
  const matches = [...text.matchAll(marker)];
  if (!matches.length || matches[0].index !== 0) return [];
  return matches.map((match, index) => {
    const start = match.index + match[0].length;
    const end = index + 1 < matches.length ? matches[index + 1].index : text.length;
    return { agent: match[1].trim(), text: text.slice(start, end).trim() };
  }).filter((item) => item.agent && item.text);
}
function stripOwnAgentMarker(value, agent) {
  const text = responseText(value).trim();
  const marker = text.match(/^\[([^\]\r\n]*Agent)\]\s*/i);
  if (!marker) return text;
  const normalize = (name) => String(name || "").replace(/[_\s-]+/g, "").toLowerCase();
  return normalize(marker[1]) === normalize(agent) ? text.slice(marker[0].length).trim() : text;
}
function orderAgentMessages(agentResponses) {
  return [...agentResponses].sort(
    (a, b) => Number(Boolean(a.primary)) - Number(Boolean(b.primary))
  );
}
function sameAgent(left, right) {
  const normalize = (name) => String(name || "").replace(/[_\s-]+/g, "").toLowerCase();
  return Boolean(normalize(left)) && normalize(left) === normalize(right);
}
function addUserMessage(text) {
  const div = document.createElement("div");
  div.className = "msg user chat-bubble--user";
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}
function addAgentMessage(agentId, text, group) {
  const article = document.createElement("article");
  article.className = "agent-message";
  article.dataset.agentId = agentId || "agent";
  const header = document.createElement("header");
  header.className = "agent-message__header";
  const avatar = document.createElement("span");
  avatar.className = "agent-message__avatar";
  avatar.textContent = humanizeAgentName(agentId).charAt(0) || "A";
  avatar.setAttribute("aria-hidden", "true");
  const name = document.createElement("span");
  name.className = "agent-message__name";
  name.textContent = humanizeAgentName(agentId);
  const body = document.createElement("div");
  body.className = "agent-message__body";
  body.textContent = responseText(text);
  header.append(avatar, name);
  article.append(header, body);
  group.appendChild(article);
}
function getAgentMessages(data) {
  const metadata = data?.metadata || {};
  const candidates = data?.supervisor_results || metadata.supervisor_results || data?.agent_responses || metadata.agent_responses || (Array.isArray(data?.messages) ? data.messages : null);
  if (Array.isArray(candidates)) {
    const messages = candidates.map((item) => ({
      agent: item?.agent || item?.agent_id || item?.agentId || item?.name,
      text: stripOwnAgentMarker(item?.answer ?? item?.text ?? item?.message ?? item?.response ?? item?.content, item?.agent || item?.agent_id || item?.agentId || item?.name),
      primary: item?.primary === true,
    })).filter((item) => item.agent && responseText(item.text).trim());
    if (messages.length) return orderAgentMessages(messages);
  }
  const text = data?.text ?? data?.speak ?? data?.message ?? data?.response ?? data?.content ?? data?.output;
  const taggedMessages = splitTaggedAgentMessages(text);
  if (taggedMessages.length) {
    const primaryAgent = metadata.active_agent || metadata.route || data?.route || metadata.route_decision?.agent || metadata.route_decision?.route;
    return orderAgentMessages(taggedMessages.map((item) => ({
      ...item,
      primary: sameAgent(item.agent, primaryAgent),
    })));
  }
  const agent = metadata.active_agent || metadata.route || data?.agent_id || metadata.agent_id || val("agent") || "agent";
  return responseText(text).trim() ? [{ agent, text }] : [];
}
function responseKey(data) {
  const stableId = data?.metadata?.message_id || data?.message_id;
  return stableId ? `id:${stableId}` : JSON.stringify(getAgentMessages(data));
}
function renderAgentResponse(data) {
  const normalized = typeof data === "string" ? { text: data } : (data || {});
  const messages = getAgentMessages(normalized);
  if (!messages.length) return false;
  const key = responseKey(normalized);
  if (renderedResponses.has(key)) return false;
  renderedResponses.add(key);
  const group = document.createElement("section");
  group.className = "agent-response-group";
  group.setAttribute("aria-label", "Respostas dos agentes");
  messages.forEach((message) => addAgentMessage(message.agent, message.text, group));
  chat.appendChild(group);
  chat.scrollTop = chat.scrollHeight;
  return true;
}
function buildBusinessContext(session, messageId) {
  return {
    customer_key: val("customerKey") || null, contract_key: val("contractKey") || null,
    interaction_key: val("interactionKey") || messageId, account_key: val("accountKey") || null,
    resource_key: val("resourceKey") || null, session_key: session || null,
    metadata: { frontend: "agent_frontend", version: "business-context-v2" },
  };
}
function syncDomainAliases(payload, businessContext) {
  if (val("agent") === "retail_orders") {
    payload.customer_id = businessContext.customer_key; payload.order_id = businessContext.contract_key;
  } else {
    payload.msisdn = businessContext.customer_key; payload.invoice_id = businessContext.contract_key;
    payload.ura_call_id = businessContext.interaction_key; payload.asset_id = businessContext.resource_key;
  }
}
function normalizeSessionId(value) {
  if (!value) return uuid();
  const parts = value.split(":"); return parts[parts.length - 1];
}
function connectSSE(backend, sessionId) {
  if (!backend || !sessionId) return;
  if (eventSource) eventSource.close();
  const url = `${backend.replace(/\/$/, "")}/gateway/events/${encodeURIComponent(sessionId)}`;
  eventSource = new EventSource(url);
  eventSource.onopen = () => status("SSE conectado");
  eventSource.onerror = () => {
    if (eventSource?.readyState === EventSource.CONNECTING) status("SSE aguardando/reconectando");
    else if (eventSource?.readyState === EventSource.CLOSED) status("SSE fechado");
    else status("SSE com erro");
  };
  const statuses = { waiting: "SSE aguardando backend", "backend.selected": "Backend selecionado", "flow.start": "Fluxo iniciado", "workflow.started": "Workflow em execução", "workflow.completed": "Workflow concluído", "flow.end": "Fluxo finalizado" };
  Object.entries(statuses).forEach(([eventName, label]) => eventSource.addEventListener(eventName, () => status(label)));
  eventSource.addEventListener("message.responded", (event) => {
    try { renderAgentResponse(JSON.parse(event.data)); } catch { renderAgentResponse(event.data); }
    status("Resposta recebida");
  });
  eventSource.addEventListener("server.error", (event) => {
    renderAgentResponse({ text: `Erro SSE: ${event.data || "erro informado pelo servidor"}`, agent_id: "sistema" });
    status("Erro no fluxo SSE");
  });
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const input = document.getElementById("message");
  const text = input.value.trim();
  if (!text) return;
  addUserMessage(text); input.value = "";
  const backend = val("backend").replace(/\/$/, "");
  const channel = val("channel");
  const session = normalizeSessionId(val("session"));
  const messageId = uuid();
  const tenantId = val("tenant") || "default";
  const agentId = val("agent") || "telecom_contas";
  document.getElementById("session").value = session;
  const businessContext = buildBusinessContext(session, messageId);
  const commonContext = { channel_id: "browser", tenant_id: tenantId, agent_id: agentId, business_context: businessContext };
  const payload = channel === "voice"
    ? { transcript: text, session_id: session, ani: businessContext.customer_key, message_id: messageId, tenant_id: tenantId, agent_id: agentId, context: commonContext }
    : { message: text, text, session_id: session, user_id: businessContext.customer_key || "web-user", message_id: messageId, tenant_id: tenantId, agent_id: agentId, context: commonContext };
  syncDomainAliases(payload, businessContext);
  if (document.getElementById("useSse")?.checked) connectSSE(backend, session);
  try {
    status("Enviando mensagem");
    const response = await fetch(`${backend}/gateway/message`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel, tenant_id: tenantId, agent_id: agentId, payload }) });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const data = await response.json();
    const returnedSessionId = data.session_id || session;
    currentSessionId = returnedSessionId;
    document.getElementById("session").value = returnedSessionId;
    renderAgentResponse(data);
    status("Resposta recebida");
  } catch (error) {
    renderAgentResponse({ text: `Erro ao chamar backend: ${error.message}`, agent_id: "sistema" });
    status("Erro de conexão");
  }
});
