/**
 * Pure controller for intervention statement planning, live submission, cancellation, and polling lifecycle.
 */

export function createInterventionController({
  api,
  state,
  makeKey = () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)),
  schedule = (fn, ms) => setTimeout(fn, ms),
  unschedule = (id) => clearTimeout(id)
}) {
  let pollingTimer = null;
  let currentRunId = null;
  let lastContent = null;
  let currentKey = null;

  async function load(runId) {
    currentRunId = runId;
    state.currentRunId = runId;
    try {
      state.busy = true;
      const res = await api.listInterventions(runId);
      if (currentRunId === runId && res.success && res.data) {
        state.items = res.data;
        state.error = null;
      }
    } catch (err) {
      if (currentRunId === runId) {
        state.error = err.message || 'Failed to load interventions';
      }
    } finally {
      if (currentRunId === runId) {
        state.busy = false;
      }
    }
  }

  async function submit(runId, payload) {
    currentRunId = runId;
    state.currentRunId = runId;

    // Preserve key on retry with identical content; generate new key on new content
    if (!currentKey || payload.content !== lastContent) {
      currentKey = makeKey();
      lastContent = payload.content;
    }

    const submissionPayload = {
      ...payload,
      idempotency_key: currentKey
    };

    try {
      state.busy = true;
      state.error = null;
      const res = await api.submitIntervention(runId, submissionPayload);
      if (currentRunId === runId && res.success && res.data) {
        const item = res.data;
        const existingIdx = state.items.findIndex(
          i => i.statement.event_id === item.statement.event_id
        );
        if (existingIdx >= 0) {
          state.items[existingIdx] = item;
        } else {
          state.items.push(item);
        }
        currentKey = null;
        lastContent = null;
        return item;
      }
    } catch (err) {
      if (currentRunId === runId) {
        state.error = err.message || 'Submission failed';
      }
      return null;
    } finally {
      if (currentRunId === runId) {
        state.busy = false;
      }
    }
  }

  async function cancel(runId, eventId) {
    try {
      state.busy = true;
      const res = await api.cancelIntervention(runId, eventId);
      if (res.success && res.data) {
        const item = state.items.find(i => i.statement.event_id === eventId);
        if (item) {
          item.execution.status = 'canceled';
        }
      }
    } catch (err) {
      state.error = err.message || 'Failed to cancel intervention';
      throw err;
    } finally {
      state.busy = false;
    }
  }

  function startPolling(runId, intervalMs = 2000) {
    stopPolling();
    currentRunId = runId;
    const poll = async () => {
      if (currentRunId === runId) {
        try {
          await load(runId);
        } catch (_) {}
        pollingTimer = schedule(poll, intervalMs);
      }
    };
    pollingTimer = schedule(poll, intervalMs);
  }

  function stopPolling() {
    if (pollingTimer) {
      unschedule(pollingTimer);
      pollingTimer = null;
    }
  }

  return {
    load,
    submit,
    cancel,
    startPolling,
    stopPolling
  };
}
