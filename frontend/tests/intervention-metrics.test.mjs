import test from 'node:test';
import assert from 'node:assert/strict';
import { loadMetricView } from '../src/features/intervention/metrics-controller.js';

test('missing heat is not rendered as zero', async () => {
  const api = {
    getInterventionMetrics: async () => ({
      success: true,
      data: {
        run_id: 'run1',
        rounds: [
          { round_num: 1, heat: 5, status: 'complete' },
          { round_num: 2, heat: null, status: 'missing' }
        ],
        cooling: { status: 'incomplete' }
      }
    }),
    listInterventions: async () => ({
      success: true,
      data: [
        {
          statement: { event_id: 'iv1', content: '学校声明', platform: 'twitter' },
          execution: { status: 'published', effective_round: 1 }
        }
      ]
    })
  };

  const view = await loadMetricView(api, 'run1');
  assert.equal(view.bundle.rounds[0].heat, 5);
  assert.equal(view.bundle.rounds[1].heat, null);
  assert.equal(view.markers.length, 1);
  assert.equal(view.markers[0].round, 1);
});

test('not_configured metrics status is handled gracefully', async () => {
  const api = {
    getInterventionMetrics: async () => ({
      success: true,
      data: { status: 'not_configured' }
    }),
    listInterventions: async () => ({
      success: true,
      data: []
    })
  };

  const view = await loadMetricView(api, 'run1');
  assert.equal(view.bundle, null);
  assert.equal(view.configured, false);
});
