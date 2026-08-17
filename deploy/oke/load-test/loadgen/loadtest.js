import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { Trend, Counter } from 'k6/metrics';

const target = __ENV.LOADTEST_TARGET || 'http://agent-template-backend.agent-load-test.svc.cluster.local:8000';
const agentId = __ENV.LOADTEST_AGENT_ID || 'telecom_contas';
const tenantId = __ENV.LOADTEST_TENANT_ID || 'loadtest';
const scenario = __ENV.LOADTEST_SCENARIO || 'unique_sessions';
const message = __ENV.LOADTEST_MESSAGE || 'Explique em uma frase o que é uma fatura de telecom.';
const rps = Number(__ENV.LOADTEST_RPS || 100);
const duration = __ENV.LOADTEST_DURATION || '10m';
const maxVUs = Number(__ENV.LOADTEST_MAX_VUS || 1000);

const backendLatency = new Trend('agent_backend_latency', true);
const errors = new Counter('agent_backend_errors');

export const options = {
  discardResponseBodies: false,
  scenarios: {
    requests: {
      executor: 'constant-arrival-rate',
      rate: rps,
      timeUnit: '1s',
      duration,
      preAllocatedVUs: Math.min(maxVUs, Math.max(50, rps * 2)),
      maxVUs,
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
  return `load-${exec.scenario.iterationInTest}-${exec.vu.idInTest}`;
}

export default function () {
  const sid = sessionId();
  const mid = `msg-${exec.scenario.iterationInTest}-${Date.now()}`;
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
      metadata: { load_test: true, scenario },
    },
  });
  const started = Date.now();
  const res = http.post(`${target}/gateway/message`, payload, {
    headers: {
      'Content-Type': 'application/json',
      'X-Request-ID': mid,
      'X-Load-Test': 'true',
    },
    timeout: __ENV.LOADTEST_HTTP_TIMEOUT || '180s',
  });
  backendLatency.add(Date.now() - started);
  const ok = check(res, {
    'status is 200': (r) => r.status === 200,
    'response has body': (r) => !!r.body && r.body.length > 0,
  });
  if (!ok) errors.add(1);
  sleep(Number(__ENV.LOADTEST_THINK_TIME || 0));
}
