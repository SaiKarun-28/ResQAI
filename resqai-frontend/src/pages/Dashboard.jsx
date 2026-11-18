import { useState, useEffect } from 'react';
import { Activity, AlertTriangle, Users, ClipboardCheck } from 'lucide-react';
import { StatCard } from '../components/dashboard/StatCard';
import { AlertList } from '../components/dashboard/AlertList';
import { CrisisMap } from '../components/dashboard/MapPlaceholder';
import { WeatherPanel } from '../components/dashboard/WeatherPanel';
import { EXAMPLE_WEATHER_LOCATION } from '../components/dashboard/weather';
import { SystemLogs } from '../components/dashboard/SystemLogs';
import { AgentMonitor } from '../components/agent/AgentMonitor';
import { Button } from '../components/ui/Button';
import { api } from '../services/api';

export function Dashboard({ view = 'overview' }) {
  const [incidents, setIncidents] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [weatherLocation, setWeatherLocation] = useState(EXAMPLE_WEATHER_LOCATION);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([api.getIncidents({ signal: controller.signal }), api.getHealth({ signal: controller.signal })])
      .then(([records, status]) => {
        if (controller.signal.aborted) return;
        setIncidents([...records].sort((a, b) => (b.created_at || '').localeCompare(a.created_at || '')));
        setHealth(status);
      })
      .catch((failure) => { if (!controller.signal.aborted) setError(failure.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);

  const title = view === 'history' ? 'Incident History' : view === 'agents' ? 'Agent Monitor' : 'Command Center';
  const reportedPeople = incidents.reduce((sum, incident) => sum + (incident.affected_people ?? 0), 0);
  const unknownCounts = incidents.filter((incident) => incident.affected_people == null).length;

  return (
    <div className="space-y-5 max-w-7xl mx-auto">
      <header className="flex flex-wrap justify-between items-start gap-3">
        <div><h1 className="text-3xl font-bold tracking-tight">{title}</h1><p className="text-text-muted text-sm mt-1">Current backend session · Human review required</p></div>
        <Button variant="secondary" disabled={loading} onClick={() => { setLoading(true); setError(''); setHealth(null); setRevision((value) => value + 1); }}>Refresh</Button>
      </header>
      {loading && <p role="status" className="text-accent-amber">Loading session data…</p>}
      {error && <div role="alert" className="border border-accent-red rounded-lg p-3 text-red-300"><p>{error}</p><p className="text-sm mt-1">Session data is unavailable. Use Refresh to retry.</p></div>}
      {!loading && !error && <>
        <p className="text-xs text-text-muted">API: {health?.status || 'unknown'} · Configured provider: {health?.active_provider || 'unknown'} · {health?.available_resources_count ?? 0} synthetic resources</p>
        {view === 'overview' && <>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
            <StatCard title="Session Incidents" value={incidents.length} icon={Activity} />
            <StatCard title="Reported Affected People" value={reportedPeople} icon={Users} />
            <StatCard title="Critical Assessments" value={incidents.filter((incident) => incident.priority === 'Critical').length} icon={AlertTriangle} />
            <StatCard title="Awaiting Human Review" value={incidents.filter((incident) => !incident.human_review?.reviewed).length} icon={ClipboardCheck} />
          </div>
          <p className="text-xs text-text-muted">Reported people are summed across reports, not deduplicated. {unknownCounts} report(s) have an unknown count. No response-time or live-dispatch metrics are available.</p>
        </>}
      </>}
      {view === 'overview' && <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
        <CrisisMap location={weatherLocation} onLocationChange={setWeatherLocation} />
        <WeatherPanel location={weatherLocation} onLocationChange={setWeatherLocation} />
      </div>}
      {!loading && !error && <>
        {view === 'overview' && <>
          <AlertList alerts={incidents.slice(0, 5)} />
          <SystemLogs incidents={incidents} />
        </>}
        {view === 'history' && <AlertList title="All Session Incidents" alerts={incidents} />}
        {view === 'agents' && (incidents.length === 0 ? <p className="text-text-muted">Submit an incident to view recorded agent results.</p> : <>
          <p className="text-sm">Latest incident: <a href={`#/incidents/${encodeURIComponent(incidents[0].incident_id)}`} className="text-accent-amber underline">{incidents[0].incident_id}</a>. Open any incident from History for its full trace.</p>
          <AgentMonitor agents={incidents[0].agents} trace={incidents[0].trace || []} />
          <SystemLogs incidents={incidents} />
        </>)}
      </>}
    </div>
  );
}
