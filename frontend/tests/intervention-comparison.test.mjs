import test from 'node:test';
import assert from 'node:assert/strict';
import { createComparisonController } from '../src/features/intervention/comparison-controller.js';

function createFixture() {
  const starts = [];
  const runsCreated = [];

  const api = {
    createInterventionExperiment: async (payload) => ({
      success: true,
      data: {
        experiment_id: 'exp1',
        scene: { scene_id: 's1' },
        variants: [
          { variant_id: 'control', name: '不干预', statements: [] },
          { variant_id: 'early', name: '早回应', statements: [{ trigger: { round: 5 } }] },
          { variant_id: 'late', name: '晚回应', statements: [{ trigger: { round: 15 } }] }
        ]
      }
    }),
    createInterventionExperimentRun: async (experimentId, payload) => {
      const run = {
        run_id: `run_${payload.variant_id}_${payload.replicate_id}`,
        simulation_id: `run_${payload.variant_id}_${payload.replicate_id}`,
        experiment_id: experimentId,
        variant_id: payload.variant_id,
        replicate_id: payload.replicate_id,
        status: 'ready'
      };
      runsCreated.push(run);
      return { success: true, data: run };
    },
    startInterventionExperimentRun: async (experimentId, runId) => {
      starts.push(runId);
      return { success: true, data: { run_id: runId, status: 'running' } };
    },
    getInterventionComparison: async (experimentId) => ({
      success: true,
      data: {
        experiment_id: experimentId,
        runs: [
          {
            variant_id: 'control',
            run: { run_id: 'run_ctrl' },
            bundle: { rounds: [{ round_num: 1, heat: 10 }], cooling: { duration_rounds: null } }
          },
          {
            variant_id: 'early',
            run: { run_id: 'run_early' },
            bundle: { rounds: [{ round_num: 1, heat: 10 }], cooling: { duration_rounds: 3 } }
          }
        ],
        incompatible_runs: [
          { variant_id: 'late', reason: 'metric_config_mismatch' }
        ],
        limitations: ['存在随机方差']
      }
    })
  };

  const state = {
    experiment: null,
    runs: [],
    comparison: null,
    busy: false,
    error: null
  };

  const controller = createComparisonController({ api, state, makeKey: () => 'idem_key' });

  const payload = {
    source_simulation_id: 'src1',
    topic_id: 'top1',
    early_round: 5,
    late_round: 15
  };

  return { api, state, controller, payload, starts, runsCreated };
}

test('creating a comparison does not start simulations', async () => {
  const f = createFixture();
  await f.controller.create(f.payload);
  assert.deepEqual(f.starts, []);
  assert.equal(f.state.experiment.variants.length, 3);
});

test('repeated start reuses run', async () => {
  const f = createFixture();
  await f.controller.create(f.payload);
  const run1 = await f.controller.createRun('early', 1, 42);
  await f.controller.start(run1.run_id);
  assert.equal(f.starts.length, 1);
  assert.equal(f.starts[0], run1.run_id);
});

test('failed and incompatible runs are preserved in comparison', async () => {
  const f = createFixture();
  await f.controller.load('exp1');
  assert.equal(f.state.comparison.runs.length, 2);
  assert.equal(f.state.comparison.incompatible_runs.length, 1);
  assert.equal(f.state.comparison.incompatible_runs[0].variant_id, 'late');
  // null cooling duration is not formatted to 0
  assert.equal(f.state.comparison.runs[0].bundle.cooling.duration_rounds, null);
});
