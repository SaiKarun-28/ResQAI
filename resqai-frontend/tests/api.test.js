import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { api } from '../src/services/api.js';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

test('incident list preserves an empty session instead of inventing records', async () => {
  globalThis.fetch = async (url) => { assert.equal(url, '/api/incidents'); return json([]); };
  assert.deepEqual(await api.getIncidents(), []);
});

test('create sends the backend report contract', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/incidents');
    assert.equal(options.method, 'POST');
    assert.equal(options.headers['Content-Type'], 'application/json');
    assert.deepEqual(JSON.parse(options.body), { report: 'Flood near school.' });
    return json({ incident_id: 'INC-001' }, 201);
  };
  assert.equal((await api.createIncident({ report: 'Flood near school.' })).incident_id, 'INC-001');
});

test('HTTP errors reject rather than being treated as incident data', async () => {
  globalThis.fetch = async () => json({ detail: 'Incident not found.' }, 404);
  await assert.rejects(api.getIncidentDetails('missing'), /Incident not found/);
});

test('FastAPI validation errors become readable messages', async () => {
  globalThis.fetch = async () => json({ detail: [{ msg: 'Report is required' }, { msg: 'Invalid input' }] }, 422);
  await assert.rejects(api.createIncident({}), /Report is required; Invalid input/);
});

test('HTML from a missing proxy is reported clearly', async () => {
  globalThis.fetch = async () => new Response('<html>Not the API</html>');
  await assert.rejects(api.getIncidents(), /invalid response.*API URL/);
});

test('invalid incident-list shape is rejected', async () => {
  globalThis.fetch = async () => json({ incidents: [] });
  await assert.rejects(api.getIncidents(), /invalid incident list/);
});

test('network failures explain how to recover', async () => {
  globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };
  await assert.rejects(api.getHealth(), /Cannot reach the ResQAI API/);
});

test('route identifiers are encoded for API paths', async () => {
  globalThis.fetch = async (url) => { assert.equal(url, '/api/incidents/a%2Fb%3Fc/trace'); return json({ trace: [] }); };
  assert.deepEqual(await api.getIncidentTrace('a/b?c'), { trace: [] });
});

test('review sends approve/reject and reviewer fields unchanged', async () => {
  const review = { decision: 'reject', reviewer_id: 'tester', reviewer_notes: 'Unverified location' };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/incidents/INC-001/review');
    assert.equal(options.method, 'POST');
    assert.deepEqual(JSON.parse(options.body), review);
    return json({ human_review: { reviewed: true, ...review } });
  };
  assert.equal((await api.reviewIncident('INC-001', review)).human_review.decision, 'reject');
});

test('component cancellation remains an AbortError', async () => {
  const controller = new AbortController();
  controller.abort();
  globalThis.fetch = async (_url, options) => { options.signal.throwIfAborted(); };
  await assert.rejects(api.getIncidents({ signal: controller.signal }), { name: 'AbortError' });
});

test('timeouts warn that a submitted incident might still complete', async (context) => {
  context.mock.timers.enable({ apis: ['setTimeout'] });
  globalThis.fetch = async (_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
  });
  const assertion = assert.rejects(api.createIncident({ report: 'Example' }), /Processing may still finish.*Incident History/);
  context.mock.timers.tick(120_001);
  await assertion;
});

for (const [name, invoke, expected] of [
  ['weather', () => api.getWeather(52.52, 13.41), /Weather request timed out.*Retry weather/],
  ['review', () => api.reviewIncident('INC-001', { decision: 'approve', reviewer_id: 'tester' }), /review request timed out.*may have been saved.*reload this incident/i],
  ['read-only data', () => api.getIncidents(), /request timed out.*Please retry/],
]) {
  test(`${name} timeouts provide relevant recovery instructions`, async (context) => {
    context.mock.timers.enable({ apis: ['setTimeout'] });
    globalThis.fetch = async (_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
    });
    const assertion = assert.rejects(invoke(), expected);
    context.mock.timers.tick(120_001);
    await assertion;
  });
}
