export function IncidentDetails({ incident }) {
  const verification = incident.verification || {};
  const findings = [
    ['Verification flags', verification.flags],
    ['Unsupported claims', verification.unsupported_claims],
    ['Missing evidence', verification.missing_evidence],
    ['Contradictions', verification.contradictions],
  ];
  return (
    <div className="space-y-4 min-w-0">
      <section className="bg-panel border border-border-default rounded-lg p-4 space-y-3">
        <h2 className="text-lg font-semibold text-accent-amber">Incident Assessment</h2>
        <p><span className="text-text-muted">Location: </span>{incident.location}</p>
        <p><span className="text-text-muted">Affected people: </span>{incident.affected_people ?? 'Unknown'}</p>
        <p><span className="text-text-muted">Injuries reported: </span>{incident.injuries_reported ? 'Yes' : 'Not reported / not confirmed'}</p>
        <h3 className="font-semibold">Original report</h3>
        <p className="text-sm whitespace-pre-wrap">{incident.raw_report || 'Not available'}</p>
        <h3 className="font-semibold">Missing information</h3>
        {incident.missing_information?.length ? <ul className="list-disc pl-4 text-sm text-text-muted space-y-1">{incident.missing_information.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p className="text-sm text-text-muted">No gaps recorded. Human verification is still required.</p>}
      </section>
      <section className="bg-panel border border-border-default rounded-lg p-4 space-y-3">
        <h2 className="text-lg font-semibold text-accent-amber">Matched Demonstration Resources</h2>
        <p className="text-xs text-text-muted">Fictional dataset, not live facilities or availability.</p>
        {(incident.resources || []).map((resource) => <div key={resource.resource_id} className="bg-surface rounded-lg p-3 text-sm space-y-1">
          <h3 className="font-semibold">{resource.name}</h3>
          <p>{resource.resource_id} · {resource.resource_type}</p>
          <p className="text-text-muted">{resource.location}</p>
          <p className="text-text-muted">Dataset status: {resource.availability_status}</p>
          {resource.match_reason && <p>{resource.match_reason}</p>}
          {resource.source && <p className="text-xs text-text-muted">Source: {resource.source}</p>}
        </div>)}
        {!incident.resources?.length && <p className="text-sm text-text-muted">No resources matched.</p>}
      </section>
      <section className="bg-panel border border-border-default rounded-lg p-4 space-y-3">
        <h2 className="text-lg font-semibold text-accent-amber">Proposed Action Plan</h2>
        <p className="text-xs text-text-muted">Unverified decision support. Professional actions require trained personnel and human authorization; this app dispatches nobody.</p>
        <ol className="space-y-3">{(incident.action_plan || []).map((action, index) => <li key={`${action.step}-${index}`} className="bg-surface rounded-lg p-3 text-sm space-y-2">
          <p className="text-accent-amber text-xs">{action.action_type === 'safety_guidance' ? 'Public safety guidance' : 'Professional judgment required'} · {action.target}</p>
          <p className="font-semibold">{action.step}. {action.action}</p>
          <p className="text-text-muted">Rationale: {action.rationale}</p>
          {action.assigned_resource_id && <p className="text-xs text-text-muted">Demonstration resource: {action.assigned_resource_id}</p>}
        </li>)}</ol>
        {!incident.action_plan?.length && <p className="text-sm text-text-muted">No action plan recorded.</p>}
      </section>
      <section className="bg-panel border border-border-default rounded-lg p-4 space-y-3">
        <h2 className="text-lg font-semibold text-accent-amber">Verification Audit</h2>
        <p className="text-sm">Pipeline status: {(verification.status || 'unknown').replaceAll('_', ' ')}</p>
        {findings.map(([title, items]) => items?.length > 0 && <div key={title}><h3 className="font-semibold text-sm">{title}</h3><ul className="list-disc pl-4 text-sm text-text-muted space-y-1">{items.map((item, index) => <li key={index}>{item}</li>)}</ul></div>)}
      </section>
    </div>
  );
}
