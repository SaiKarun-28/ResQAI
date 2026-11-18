export function AlertList({ alerts = [], title = 'Recent Incidents' }) {
  return (
    <section className="bg-panel border border-border-default rounded-lg p-4">
      <h2 className="text-lg font-semibold text-accent-amber mb-3">{title}</h2>
      {alerts.length === 0 ? <p className="text-sm text-text-muted">No incidents in this session. <a href="#/new" className="text-accent-amber underline">Submit a report</a> to begin.</p> : (
        <ul className="space-y-2">
          {alerts.map((incident) => (
            <li key={incident.incident_id}>
              <a href={`#/incidents/${encodeURIComponent(incident.incident_id)}`} className="flex items-start gap-3 p-3 bg-surface rounded-xl hover:bg-surface-2">
                <span aria-hidden="true" className={`w-2 h-2 shrink-0 rounded-full mt-1.5 ${['Critical', 'High'].includes(incident.priority) ? 'bg-accent-red' : 'bg-accent-amber'}`} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{incident.incident_id} · {incident.category}</p>
                  <p className="text-xs text-text-muted break-words mt-1">{incident.location}</p>
                  <p className="text-xs text-accent-amber mt-1">{incident.priority} (provisional) · {incident.human_review?.reviewed ? `Reviewed: ${incident.human_review.decision}` : 'Awaiting human review'}</p>
                  {incident.created_at && <time dateTime={incident.created_at} className="block text-xs text-text-muted mt-1">{new Date(incident.created_at).toLocaleString()}</time>}
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
