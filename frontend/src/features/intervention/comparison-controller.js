/**
 * Controller for managing intervention experiment creation, runs, and comparison views.
 */

export function createComparisonController({ api, state, makeKey = () => `idem_${Date.now()}` }) {
  async function create(payload) {
    state.busy = true;
    state.error = null;
    try {
      const res = await api.createInterventionExperiment(payload);
      state.experiment = res.data;
      return res.data;
    } catch (err) {
      state.error = err?.message || String(err);
      throw err;
    } finally {
      state.busy = false;
    }
  }

  async function createRun(variantId, replicateId = 1, seed = 42) {
    if (!state.experiment) return null;
    state.busy = true;
    state.error = null;
    try {
      const idempotencyKey = makeKey ? makeKey() : `idem_${variantId}_${replicateId}`;
      const res = await api.createInterventionExperimentRun(state.experiment.experiment_id, {
        variant_id: variantId,
        replicate_id: replicateId,
        seed,
        idempotency_key: idempotencyKey
      });
      const run = res.data;
      const idx = state.runs.findIndex((r) => r.run_id === run.run_id);
      if (idx >= 0) {
        state.runs[idx] = run;
      } else {
        state.runs.push(run);
      }
      return run;
    } catch (err) {
      state.error = err?.message || String(err);
      throw err;
    } finally {
      state.busy = false;
    }
  }

  async function start(runId) {
    if (!state.experiment) return null;
    state.busy = true;
    state.error = null;
    try {
      const res = await api.startInterventionExperimentRun(state.experiment.experiment_id, runId);
      const run = res.data;
      const idx = state.runs.findIndex((r) => r.run_id === runId);
      if (idx >= 0) {
        state.runs[idx] = { ...state.runs[idx], status: run.status };
      }
      return run;
    } catch (err) {
      state.error = err?.message || String(err);
      throw err;
    } finally {
      state.busy = false;
    }
  }

  async function load(experimentId) {
    state.busy = true;
    state.error = null;
    try {
      const res = await api.getInterventionComparison(experimentId);
      state.comparison = res.data;
      return res.data;
    } catch (err) {
      state.error = err?.message || String(err);
      throw err;
    } finally {
      state.busy = false;
    }
  }

  return {
    create,
    createRun,
    start,
    load
  };
}
