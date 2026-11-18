export function SystemLogs({ incidents = [] }) {
  const logs = incidents.slice(0, 5).flatMap((incident) => (incident.trace || []).map((item) => ({ ...item, incidentId: incident.incident_id })));
  return (
    <section className="bg-panel border border-border-default rounded-lg p-4">
      <h2 className="text-accent-amber font-semibold mb-3">Recorded Agent Activity</h2>
      {logs.length === 0 ? <p className="text-sm text-text-muted">No recorded agent activity yet.</p> : (
        <ul className="font-mono text-xs text-text-muted space-y-2">
          {logs.map((log, index) => <li key={`${log.incidentId}-${log.agent}-${index}`} className="break-words">
            [{log.incidentId}] {log.agent}: {log.status} · {log.duration_ms.toFixed(1)} ms — {log.summary}
          </li>)}
        </ul>
      )}
    </section>
  );
}
