import test from 'node:test';
import assert from 'node:assert/strict';
import { createInterventionController } from '../src/features/intervention/controller.js';

function fixture(options = {}) {
  const calls = [];
  let keyCounter = 1;
  const timerCallbacks = [];
  let failFirst = options.failFirst || false;

  const api = {
    async submitIntervention(runId, payload) {
      calls.push({ runId, ...payload });
      if (failFirst) {
        failFirst = false;
        throw new Error('Network failure');
      }
      return {
        success: true,
        data: {
          statement: { event_id: 'iv1', ...payload },
          execution: { event_id: 'iv1', status: 'queued' }
        }
      };
    },
    async listInterventions(runId) {
      return {
        success: true,
        data: calls.map(c => ({
          statement: { event_id: 'iv1', content: c.content, idempotency_key: c.idempotency_key },
          execution: { event_id: 'iv1', status: 'published', effective_round: 5 }
        }))
      };
    },
    async cancelIntervention(runId, eventId) {
      return {
        success: true,
        data: { event_id: eventId, status: 'canceled' }
      };
    }
  };

  const state = {
    items: [],
    busy: false,
    error: null,
    pendingKey: null,
    currentRunId: null
  };

  const schedule = (fn, ms) => {
    timerCallbacks.push(fn);
    return timerCallbacks.length;
  };

  const unschedule = (id) => {
    // mock unschedule
  };

  const makeKey = () => `k${keyCounter++}`;

  const controller = createInterventionController({
    api,
    state,
    makeKey,
    schedule,
    unschedule
  });

  return {
    controller,
    api,
    state,
    calls,
    timerCallbacks
  };
}

test('retry keeps the same idempotency key', async () => {
  const f = fixture({ failFirst: true });
  await f.controller.submit('run1', { content: '学校回应' });
  await f.controller.submit('run1', { content: '学校回应' });
  assert.equal(f.calls[0].idempotency_key, f.calls[1].idempotency_key);
  assert.equal(f.state.items.length, 1);
});

test('different content creates new key', async () => {
  const f = fixture();
  await f.controller.submit('run1', { content: '学校回应一' });
  await f.controller.submit('run1', { content: '学校回应二' });
  assert.notEqual(f.calls[0].idempotency_key, f.calls[1].idempotency_key);
  assert.equal(f.calls.length, 2);
});

test('load restores items without re-submitting', async () => {
  const f = fixture();
  f.calls.push({ content: '已存在声明', idempotency_key: 'k_exist' });
  await f.controller.load('run1');
  assert.equal(f.state.items.length, 1);
  assert.equal(f.state.items[0].execution.status, 'published');
});

test('cancel updates execution status', async () => {
  const f = fixture();
  await f.controller.submit('run1', { content: '待取消' });
  await f.controller.cancel('run1', 'iv1');
  const found = f.state.items.find(i => i.statement.event_id === 'iv1');
  assert.equal(found.execution.status, 'canceled');
});

test('late response does not overwrite switched run', async () => {
  const f = fixture();
  let resolveFirst;
  f.api.listInterventions = async (runId) => {
    if (runId === 'run1') {
      await new Promise(r => { resolveFirst = r; });
      return {
        success: true,
        data: [{ statement: { event_id: 'iv_run1' }, execution: { status: 'queued' } }]
      };
    }
    return {
      success: true,
      data: [{ statement: { event_id: 'iv_run2' }, execution: { status: 'published' } }]
    };
  };

  const p1 = f.controller.load('run1');
  const p2 = f.controller.load('run2');
  await p2;
  resolveFirst();
  await p1;

  assert.equal(f.state.items[0].statement.event_id, 'iv_run2');
});
