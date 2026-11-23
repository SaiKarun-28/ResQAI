import { useEffect, useRef, useState } from 'react';
import { AgentMonitor } from '../components/agent/AgentMonitor';
import { IncidentDetails as IncidentAssessment } from '../components/dashboard/IncidentDetails';
import { Button } from '../components/ui/Button';
import { api } from '../services/api';

export default function IncidentDetails({ incidentId }) {
  const [incident, setIncident] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [decision, setDecision] = useState('');
  const [reviewerId, setReviewerId] = useState('');
  const [notes, setNotes] = useState('');
  const [reviewError, setReviewError] = useState('');
  const [reviewMessage, setReviewMessage] = useState('');
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    api.getIncidentDetails(incidentId, { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        if (!data?.incident_id) throw new Error('The API returned an invalid incident record.');
        setIncident(data);
      })
      .catch((failure) => { if (!controller.signal.aborted) setError(failure.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [incidentId, revision]);

  async function submitReview(event) {
    event.preventDefault();
    if (inFlight.current || !decision || !reviewerId.trim()) return;
    inFlight.current = true;
    setSaving(true);
    setReviewError('');
    setReviewMessage('');
    try {
      const result = await api.reviewIncident(incidentId, { decision, reviewer_id: reviewerId.trim(), reviewer_notes: notes.trim() });
      if (!result?.human_review?.reviewed) throw new Error('The API did not confirm the review. Refresh the incident before retrying.');
      setIncident((current) => ({ ...current, human_review: result.human_review }));
      setReviewMessage(result.disclaimer || 'Human review recorded. No dispatch is authorized.');
    } catch (failure) {
      setReviewError(failure.message);
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }

  const rescuePlan = incident?.rescue_plan;
  const dispatchRequests = incident?.dispatch_requests || [];
  const approved = incident?.human_review?.reviewed && incident.human_review.decision === 'approve';

  return (
    <div className="max-w-7xl mx-auto space-y-4 [overflow-wrap:anywhere]">
      <a href="#/history" className="text-sm text-accent-amber underline">Back to Incident History</a>
      {loading && <p role="status">Loading incident…</p>}
      {error && <div role="alert" className="space-y-3"><p className="text-red-300">{error}</p><Button onClick={() => { setLoading(true); setError(''); setRevision((value) => value + 1); }}>Retry</Button></div>}
      {!loading && !error && incident && <>
        <header className="space-y-2">
          <h1 className="text-3xl font-bold">{incident.incident_id}</h1>
          <p className="text-accent-amber">{incident.category} · {incident.priority} (provisional)</p>
          {incident.created_at && <p className="text-xs text-text-muted">Created: {new Date(incident.created_at).toLocaleString()}</p>}
          <p className="text-sm text-text-muted">{incident.disclaimer}</p>
        </header>
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-4 items-start">
          <div className="xl:col-span-2 min-w-0 space-y-4">
            <IncidentAssessment incident={incident} />
            <RescuePlanSection plan={rescuePlan} />
          </div>
          <div className="space-y-4 min-w-0">
            <AgentMonitor agents={incident.agents} trace={incident.trace || []} />
            <section className="bg-panel border border-border-default rounded-lg p-4 space-y-3">
              <h2 className="text-lg font-semibold text-accent-amber">Human Review</h2>
              <p className="text-xs text-text-muted">Approval records an advisory assessment only. It does not authorize emergency dispatch.</p>
              {incident.human_review?.reviewed && <div className="text-sm bg-surface rounded-lg p-3 space-y-1">
                <p>Recorded decision: <strong>{incident.human_review.decision}</strong></p>
                <p>Reviewer: {incident.human_review.reviewer_id}</p>
                <p>{incident.human_review.reviewer_notes}</p>
                {incident.human_review.reviewed_at && <p className="text-xs text-text-muted">{new Date(incident.human_review.reviewed_at).toLocaleString()}</p>}
              </div>}
              <form onSubmit={submitReview} className="space-y-3" aria-busy={saving}>
                <label className="block text-sm">Decision
                  <select required value={decision} disabled={saving} onChange={(event) => setDecision(event.target.value)} className="block w-full bg-surface rounded-lg p-2 mt-1">
                    <option value="">Choose a decision</option><option value="approve">Approve assessment</option><option value="reject">Reject assessment</option>
                  </select>
                </label>
                <label className="block text-sm">Reviewer ID
                  <input required maxLength={100} value={reviewerId} disabled={saving} onChange={(event) => setReviewerId(event.target.value)} className="block w-full bg-surface rounded-lg p-2 mt-1" />
                </label>
                <label className="block text-sm">Review notes
                  <textarea rows={3} maxLength={5000} value={notes} disabled={saving} onChange={(event) => setNotes(event.target.value)} className="block w-full bg-surface rounded-lg p-2 mt-1" />
                </label>
                <Button type="submit" disabled={saving || !decision || !reviewerId.trim()}>{saving ? 'Saving…' : 'Record Review'}</Button>
              </form>
              {reviewError && <p role="alert" className="text-sm text-red-300">{reviewError}</p>}
              {reviewMessage && <p role="status" className="text-sm text-emerald-300">{reviewMessage}</p>}
            </section>
            <DispatchSection requests={dispatchRequests} approved={approved} />
          </div>
        </div>
      </>}
    </div>
  );
}

function RescuePlanSection({ plan }) {
  if (!plan) return null;
  return (
    <section className="bg-panel border border-border-default rounded-lg p-4 space-y-3">
      <h2 className="text-lg font-semibold text-accent-amber">Rescue Plan</h2>
      <div className="text-sm text-text-muted space-y-1">
        <p>Plan ID: {plan.id} · Version {plan.version}</p>
        {plan.created_at && <p className="text-xs">Created: {new Date(plan.created_at).toLocaleString()}</p>}
      </div>
      {Array.isArray(plan.plan_json?.actions) && plan.plan_json.actions.length > 0 && (
        <ol className="space-y-2 text-sm">
          {plan.plan_json.actions.map((action, index) => (
            <li key={index} className="bg-surface rounded-lg p-3 space-y-1">
              <p className="font-medium">{action.step}. {action.action}</p>
              {action.rationale && <p className="text-text-muted">{action.rationale}</p>}
              <p className="text-xs text-text-muted">
                Type: {action.action_type}
                {action.assigned_resource_id ? ` · Resource: ${action.assigned_resource_id}` : ''}
              </p>
            </li>
          ))}
        </ol>
      )}
      {plan.verification_result && (
        <p className="text-xs text-text-muted">
          Verification status: <strong>{plan.verification_result.status}</strong>
        </p>
      )}
    </section>
  );
}

function DispatchSection({ requests, approved }) {
  if (!requests.length) return null;
  const label = (status) =>
    status === 'approved_simulated' ? 'Approved (simulated)' : status === 'created_simulated' ? 'Awaiting approval' : status;
  return (
    <section className="bg-panel border border-border-default rounded-lg p-4 space-y-3">
      <h2 className="text-lg font-semibold text-accent-amber">Simulated Dispatch Requests</h2>
      <p className="text-xs text-text-muted">
        Records of proposed responder requests. Never a live dispatch — all simulated.
        {approved ? '' : ' Awaiting human approval to confirm.'}
      </p>
      <ul className="space-y-2 text-sm">
        {requests.map((req) => (
          <li key={req.id} className="bg-surface rounded-lg p-3 space-y-1">
            <p className="font-medium">{req.resource_category} × {req.quantity}</p>
            <p className="text-xs text-text-muted">{req.rationale}</p>
            <p className="text-xs">
              <span className={req.status === 'approved_simulated' ? 'text-emerald-300' : 'text-amber-300'}>
                {label(req.status)}
              </span>
            </p>
          </li>
        ))}
      </ul>
    </section>
  );
}