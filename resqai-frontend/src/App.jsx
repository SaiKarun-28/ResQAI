import { useEffect, useState } from 'react';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './pages/Dashboard';
import NewIncident from './pages/NewIncident';
import IncidentDetails from './pages/IncidentDetails';

function App() {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || '/');
  useEffect(() => {
    const onHashChange = () => setRoute(window.location.hash.slice(1) || '/');
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const detailMatch = route.match(/^\/incidents\/([^/]+)$/);
  const activePage = detailMatch ? 'history' : ({ '/': 'overview', '/new': 'new', '/history': 'history', '/agents': 'agents', '/about': 'about' })[route];
  let content;
  if (detailMatch) {
    content = <IncidentDetails key={detailMatch[1]} incidentId={detailMatch[1]} />;
  } else if (route === '/new') {
    content = <NewIncident />;
  } else if (['/', '/history', '/agents'].includes(route)) {
    content = <Dashboard key={route} view={activePage} />;
  } else if (route === '/about') {
    content = (
      <section className="max-w-3xl mx-auto space-y-4">
        <h1 className="text-3xl font-bold">About ResQAI</h1>
        <p>ResQAI is an experimental decision-support prototype. Intake, triage, resource matching, planning, and verification agents turn reports into provisional assessments for human review.</p>
        <p className="text-accent-amber">This is not an emergency dispatch system. For a real emergency, contact your local emergency services immediately. Do not wait for this prototype.</p>
        <p className="text-text-muted">Resources are fictional demonstration records, not live availability. Incidents and reviews are held in backend memory and are lost when the server restarts. Agent status is retrieved after processing, not streamed live. A deterministic fallback is available when an AI provider is unavailable.</p>
        <p className="text-text-muted">The overview uses <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer" className="text-accent-amber underline">© OpenStreetMap contributors</a> map data and <a href="https://open-meteo.com/" target="_blank" rel="noreferrer" className="text-accent-amber underline">Open-Meteo</a> forecasts. The initial Berlin coordinates are an example only. The map marker selects a weather location, not an incident or responder. No incident geocoding or live dispatch is provided.</p>
        <p className="text-text-muted">Selected coordinates are sent via the ResQAI API to Open-Meteo; map tiles are requested directly from OpenStreetMap. No browser geolocation permission or automatic GPS is used. Model grid coordinates may differ from your selection and forecasts may be cached for one hour. Weather context is separate from synthetic emergency resources.</p>
        <p className="text-accent-amber">Modelled weather context, not an official emergency warning or verified incident conditions.</p>
      </section>
    );
  } else {
    content = <section><h1 className="text-2xl font-bold">Page not found</h1><a href="#/" className="text-accent-amber underline">Return to overview</a></section>;
  }

  return <Layout activePage={activePage}>{content}</Layout>;
}

export default App;
