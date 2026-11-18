import { useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';
import { Button } from '../ui/Button';

export function IncidentForm({ onCreated }) {
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const inFlight = useRef(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (inFlight.current) return;
    const report = description.trim();
    if (!report) {
      setError('Enter an incident report before submitting.');
      return;
    }
    inFlight.current = true;
    setSubmitting(true);
    setError('');
    try {
      const incident = await api.createIncident({ report });
      if (!incident?.incident_id) throw new Error('The API did not return an incident ID. Check Incident History before retrying.');
      if (mounted.current) {
        setDescription('');
        onCreated?.(incident);
      }
    } catch (failure) {
      if (mounted.current) setError(failure.message);
    } finally {
      inFlight.current = false;
      if (mounted.current) setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} aria-busy={submitting} className="bg-panel border border-border-default rounded-lg p-4 space-y-4">
      <label htmlFor="incident-report" className="block font-semibold">Incident report</label>
      <textarea id="incident-report" required maxLength={10000}
        aria-describedby="report-help" disabled={submitting}
        className="w-full bg-surface border border-border-default rounded-lg p-3 text-white"
        rows={6} placeholder="Describe what happened, the location, and any reported injuries. Do not guess missing details."
        value={description} onChange={(event) => setDescription(event.target.value)} />
      <p id="report-help" className="text-sm text-text-muted">Only include information needed for this demonstration. Maximum 10,000 characters.</p>
      {error && <p role="alert" className="text-red-300">{error}</p>}
      <Button type="submit" disabled={submitting || !description.trim()}>{submitting ? 'Processing report…' : 'Submit Incident'}</Button>
      {submitting && <p role="status" className="text-sm text-text-muted">Running the five-agent assessment. No emergency services will be dispatched.</p>}
    </form>
  );
}
