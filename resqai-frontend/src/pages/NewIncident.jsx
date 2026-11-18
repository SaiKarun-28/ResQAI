import { IncidentForm } from '../components/dashboard/IncidentForm';

export default function NewIncident() {
  return (
    <section className="max-w-2xl mx-auto space-y-4">
      <h1 className="text-3xl font-bold text-accent-amber">Report New Incident</h1>
      <p className="text-text-muted text-sm">ResQAI is a demonstration decision-support tool. If this is a real emergency, contact your local emergency services immediately. Do not wait for this prototype.</p>
      <IncidentForm onCreated={(incident) => { window.location.hash = `/incidents/${encodeURIComponent(incident.incident_id)}`; }} />
    </section>
  );
}
