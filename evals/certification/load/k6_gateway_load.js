import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: Number(__ENV.K6_VUS || 10),
  duration: __ENV.K6_DURATION || '1m',
  thresholds: {
    http_req_failed: ['rate<0.05'],
    http_req_duration: ['p(95)<5000'],
  },
};

const BASE_URL = __ENV.BACKEND_URL || 'http://localhost:8000';

export default function () {
  const payload = JSON.stringify({
    channel: 'web',
    payload: {
      text: 'Quero consultar minha fatura e rastrear meu pedido PED-1001',
      message: 'Quero consultar minha fatura e rastrear meu pedido PED-1001',
      session_id: `k6-${__VU}-${__ITER}`,
      user_id: `k6-user-${__VU}`,
      channel_id: 'k6',
      context: { load_test: true },
    },
  });
  const params = { headers: { 'Content-Type': 'application/json' } };
  const res = http.post(`${BASE_URL}/debug/route`, payload, params);
  check(res, {
    'status 2xx': (r) => r.status >= 200 && r.status < 300,
    'has route response': (r) => r.body && r.body.length > 2,
  });
  sleep(1);
}
