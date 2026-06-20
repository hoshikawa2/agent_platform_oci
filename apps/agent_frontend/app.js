const chat=document.getElementById('chat');
const form=document.getElementById('form');
let eventSource=null;
let currentSessionId = null;

function add(role,text){
  const d=document.createElement('div');
  d.className='msg '+role;
  d.textContent=text;
  chat.appendChild(d);
  chat.scrollTop=chat.scrollHeight;
}
function status(text){const el=document.getElementById('status'); if(el) el.textContent=text;}
function val(id){return (document.getElementById(id)?.value || '').trim();}
function uuid(){return crypto.randomUUID();}

function buildBusinessContext(session, messageId){
  return {
    customer_key: val('customerKey') || null,
    contract_key: val('contractKey') || null,
    interaction_key: val('interactionKey') || messageId,
    account_key: val('accountKey') || null,
    resource_key: val('resourceKey') || null,
    session_key: session || null,
    metadata: {frontend: 'agent_frontend', version: 'business-context-v2'}
  };
}

function syncDomainAliases(payload, businessContext){
  const agent=val('agent');
  if(agent === 'retail_orders'){
    payload.customer_id = businessContext.customer_key;
    payload.order_id = businessContext.contract_key;
  } else {
    payload.msisdn = businessContext.customer_key;
    payload.invoice_id = businessContext.contract_key;
    payload.ura_call_id = businessContext.interaction_key;
    payload.asset_id = businessContext.resource_key;
  }
}

function adicionarMensagem(role, text) {
  const chat =
      document.getElementById("chat") ||
      document.getElementById("messages") ||
      document.querySelector(".chat") ||
      document.querySelector(".messages") ||
      document.querySelector("[data-chat]");

  if (!chat) {
    console.error("Não encontrei o container do chat no HTML.");
    console.log("Mensagem que seria exibida:", role, text);
    return;
  }

  const div = document.createElement("div");

  if (role === "user") {
    div.className = "msg user chat-bubble--user";
  } else {
    div.className = "msg assistant chat-bubble--agent";
  }

  div.textContent = text || "";

  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function abrirSSE(sessionId) {
  if (!sessionId) {
    console.error("Não vou abrir SSE sem sessionId.");
    return;
  }

  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  const url = `${backend}/gateway/events/${sessionId}`;

  eventSource = new EventSource(url);

  eventSource.onopen = () => {
    console.log("SSE OPEN");
  };

  eventSource.onerror = (err) => {
    console.error("SSE ERROR:", err);
  };

  const eventos = [
    "connected",
    "waiting",
    "backend.selected",
    "flow.start",
    "workflow.started",
    "message.responded",
    "workflow.completed",
    "flow.end",
    "error"
  ];

  for (const nome of eventos) {
    eventSource.addEventListener(nome, (event) => {

      if (nome === "message.responded") {
        try {
          const data = JSON.parse(event.data);

          const text =
              data.text ||
              data.message ||
              data.response ||
              data.content ||
              data.output ||
              event.data;

          adicionarMensagem("assistant", text);
        } catch {
          adicionarMensagem("assistant", event.data);
        }
      }

      if (nome === "error") {
        adicionarMensagem("assistant", `Erro SSE: ${event.data}`);
      }
    });
  }
}

function normalizeSessionId(value) {
  if (!value) return uuid();

  const parts = value.split(":");
  return parts[parts.length - 1]; // mantém só o UUID final
}

function connectSSE(backend, sessionId) {
  if (!sessionId) {
    console.warn("SSE não aberto: sessionId ausente.");
    return;
  }

  if (!backend) {
    console.warn("SSE não aberto: backend ausente.");
    return;
  }

  if (eventSource) {
    console.log("Fechando SSE anterior:", eventSource.url);
    eventSource.close();
    eventSource = null;
  }

  const url = `${backend.replace(/\/$/, "")}/gateway/events/${encodeURIComponent(sessionId)}`;

  console.log("Abrindo SSE:", url);

  eventSource = new EventSource(url);
  eventSource._sessionId = sessionId;

  eventSource.onopen = () => {
    console.log("SSE OPEN:", url);
    status("SSE conectado");
  };

  eventSource.onerror = (err) => {
    console.error("SSE ERROR raw:", err);
    console.error("SSE readyState:", eventSource?.readyState);
    console.error("SSE url:", eventSource?.url);

    if (eventSource?.readyState === EventSource.CONNECTING) {
      status("SSE aguardando/reconectando");
      return;
    }

    if (eventSource?.readyState === EventSource.CLOSED) {
      status("SSE fechado");
      return;
    }

    status("SSE com erro");
  };

  eventSource.addEventListener("connected", (event) => {
    console.log("SSE connected:", event.data);
    status("SSE conectado");
  });

  eventSource.addEventListener("waiting", (event) => {
    console.log("SSE waiting:", event.data);
    status("SSE aguardando backend");
  });

  eventSource.addEventListener("backend.selected", (event) => {
    console.log("SSE backend.selected:", event.data);
    status("Backend selecionado");
  });

  eventSource.addEventListener("flow.start", (event) => {
    console.log("SSE flow.start:", event.data);
    status("Fluxo iniciado");
  });

  eventSource.addEventListener("workflow.started", (event) => {
    console.log("SSE workflow.started:", event.data);
    status("Workflow em execução");
  });

  eventSource.addEventListener("session.upserted", (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.business_context) {
        console.debug("business_context", data.business_context);
      }
    } catch (e) {
      console.warn("Não consegui interpretar session.upserted:", event.data);
    }
  });

  eventSource.addEventListener("message.responded", (event) => {
    try {
      const data = JSON.parse(event.data);

      const text =
          data.text ||
          data.message ||
          data.response ||
          data.content ||
          data.output ||
          event.data;

      if (text) {
        add("assistant", text);
      }

      if (data.metadata?.business_context) {
        console.debug("metadata.business_context", data.metadata.business_context);
      }

      status("Resposta recebida");
    } catch (e) {
      add("assistant", event.data);
      status("Resposta recebida");
    }
  });

  eventSource.addEventListener("workflow.completed", (event) => {
    console.log("SSE workflow.completed:", event.data);
    status("Workflow concluído");
  });

  eventSource.addEventListener("flow.end", (event) => {
    console.log("SSE flow.end:", event.data);
    status("Fluxo finalizado");
  });

  // Use um nome diferente de "error" para erro enviado pelo servidor.
  // "error" é reservado/conflituoso com erro nativo do EventSource.
  eventSource.addEventListener("server.error", (event) => {
    console.error("SSE server.error:", event.data);
    add("assistant", `Erro SSE: ${event.data || "erro informado pelo servidor"}`);
    status("Erro no fluxo SSE");
  });
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();

  const input = document.getElementById('message');
  const text = input.value.trim();

  if (!text) return;

  adicionarMensagem('user', text);
  input.value = '';

  const backend = val('backend').replace(/\/$/, '');
  const channel = val('channel');
  // const session = val('session') || uuid();
  const session = normalizeSessionId(val('session'));
  const messageId = uuid();
  const tenantId = val('tenant') || 'default';
  const agentId = val('agent') || 'telecom_contas';

  document.getElementById('session').value = session;

  const businessContext = buildBusinessContext(session, messageId);

  const commonContext = {
    channel_id: 'browser',
    tenant_id: tenantId,
    agent_id: agentId,
    business_context: businessContext
  };

  const payload = channel === 'voice'
      ? {
        transcript: text,
        session_id: session,
        ani: businessContext.customer_key,
        message_id: messageId,
        tenant_id: tenantId,
        agent_id: agentId,
        context: commonContext
      }
      : {
        message: text,
        text: text,
        session_id: session,
        user_id: businessContext.customer_key || 'web-user',
        message_id: messageId,
        tenant_id: tenantId,
        agent_id: agentId,
        context: commonContext
      };

  syncDomainAliases(payload, businessContext);

  try {
    status('Enviando mensagem');

    const res = await fetch(`${backend}/gateway/message`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        channel,
        tenant_id: tenantId,
        agent_id: agentId,
        payload
      })
    });

    if (!res.ok) {
      throw new Error(`${res.status} ${res.statusText}`);
    }

    const data = await res.json();

    const returnedSessionId = data.session_id || session;
    currentSessionId = returnedSessionId;
    document.getElementById('session').value = returnedSessionId;

    const resposta =
        data.text ||
        data.speak ||
        data.message ||
        data.response ||
        data.content ||
        data.output ||
        JSON.stringify(data);

    adicionarMensagem('assistant', resposta);
    status('Resposta recebida');

  } catch (err) {
    adicionarMensagem('assistant', `Erro ao chamar backend: ${err.message}`);
    status('Erro de conexão');
  }
});