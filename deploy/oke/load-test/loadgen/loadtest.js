import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { Trend, Counter } from 'k6/metrics';

const target =
    __ENV.LOADTEST_TARGET ||
    'http://agent-template-backend.agent-load-test.svc.cluster.local:8000';

const agentId =
    __ENV.LOADTEST_AGENT_ID || 'telecom_contas';

const tenantId =
    __ENV.LOADTEST_TENANT_ID || 'loadtest';

const scenario =
    __ENV.LOADTEST_SCENARIO || 'unique_sessions';

const message =
    __ENV.LOADTEST_MESSAGE ||
    'Explique em uma frase o que é uma fatura de telecom.';

const duration =
    __ENV.LOADTEST_DURATION || '10m';

const maxVUs =
    Number(__ENV.LOADTEST_MAX_VUS || 300);

const startVUs =
    Number(__ENV.LOADTEST_START_VUS || 30);

const thinkTime =
    Number(__ENV.LOADTEST_THINK_TIME || 0);

const httpTimeout =
    __ENV.LOADTEST_HTTP_TIMEOUT || '180s';

const backendLatency =
    new Trend('agent_backend_latency', true);

const errors =
    new Counter('agent_backend_errors');

export const options = {
  discardResponseBodies: false,

  scenarios: {
    requests: {
      executor: 'ramping-vus',

      startVUs,

      stages: [
        { duration: '1m', target: 100 },
        { duration: '2m', target: 200 },
        { duration: '2m', target: maxVUs },
        { duration: '4m', target: maxVUs },
        { duration: '1m', target: 0 },
      ],

      gracefulRampDown: '30s',
    },
  },

  thresholds: {
    http_req_failed: ['rate<0.05'],
    checks: ['rate>0.95'],
  },
};

function sessionId() {
  if (scenario === 'shared_sessions') {
    return `shared-${exec.vu.idInTest % 100}`;
  }

  /*
   * Para unique_sessions, mantenha uma sessão por VU.
   *
   * Isso representa melhor um usuário conversando continuamente
   * com o agente durante o teste.
   */
  return `load-${exec.vu.idInTest}`;
}

export default function () {
  const sid = sessionId();

  const mid =
      `msg-${exec.vu.idInTest}-${exec.scenario.iterationInTest}-${Date.now()}`;

  const payload = JSON.stringify({
    channel: 'web',
    agent_id: agentId,
    tenant_id: tenantId,

    payload: {
      text: message,
      session_id: sid,

      user_id: `user-${exec.vu.idInTest}`,
      customer_id: `cust-${exec.vu.idInTest}`,
      message_id: mid,

      metadata: {
        load_test: true,
        scenario,
      },
    },
  });

  const started = Date.now();

  const res = http.post(
      `${target}/gateway/message`,
      payload,
      {
        headers: {
          'Content-Type': 'application/json',
          'X-Request-ID': mid,
          'X-Load-Test': 'true',
        },

        timeout: httpTimeout,
      }
  );

  backendLatency.add(Date.now() - started);

  const ok = check(res, {
    'status is 200': (r) => r.status === 200,

    'response has body': (r) =>
        !!r.body && r.body.length > 0,
  });

  if (!ok) {
    errors.add(1);
  }

  /*
   * Se LOADTEST_THINK_TIME=0:
   *
   * usuário envia a próxima mensagem assim que recebe a resposta.
   *
   * Se quiser simular tempo humano entre mensagens:
   * LOADTEST_THINK_TIME=5, 10 etc.
   */
  if (thinkTime > 0) {
    sleep(thinkTime);
  }
}