/**
 * Controller for loading and structuring intervention discussion heat metrics.
 */

export async function loadMetricView(api, runId) {
  try {
    const [metricsRes, interventionsRes] = await Promise.all([
      api.getInterventionMetrics(runId),
      api.listInterventions ? api.listInterventions(runId) : Promise.resolve({ data: [] })
    ]);

    const data = metricsRes?.data;
    if (!data || data.status === 'not_configured') {
      return {
        configured: false,
        computing: false,
        bundle: null,
        markers: []
      };
    }

    if (data.status === 'computing') {
      return {
        configured: true,
        computing: true,
        bundle: null,
        markers: []
      };
    }

    const interventions = interventionsRes?.data || [];
    const markers = interventions
      .filter((item) => item.execution?.status === 'published' && item.execution?.effective_round != null)
      .map((item) => ({
        round: item.execution.effective_round,
        eventId: item.statement?.event_id,
        content: item.statement?.content,
        platform: item.statement?.platform
      }));

    return {
      configured: true,
      computing: false,
      bundle: data,
      markers
    };
  } catch (err) {
    return {
      configured: false,
      computing: false,
      bundle: null,
      markers: [],
      error: err?.message || String(err)
    };
  }
}
