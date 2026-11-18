import test, { before, after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

let server;
before(async () => {
  server = await createServer({ server: { middlewareMode: true, watch: null }, appType: 'custom' });
});
after(async () => { await server?.close(); });

async function render(path, name, props) {
  const module = await server.ssrLoadModule(`/src/${path}.jsx`);
  return renderToStaticMarkup(createElement(module[name], props));
}

test('layout renders its children, header, and a single functional navigation', async () => {
  const html = await render('components/layout/Layout', 'Layout', { children: 'visible-dashboard-content', activePage: 'overview' });
  assert.match(html, /visible-dashboard-content/);
  assert.equal((html.match(/<aside/g) || []).length, 1);
  assert.match(html, /href="#\/new"/);
  assert.match(html, /aria-current="page"/);
  assert.doesNotMatch(html, />LayoutDashboard</);
});

test('StatCard supports zero and an omitted change prop', async () => {
  const html = await render('components/dashboard/StatCard', 'StatCard', { title: 'Session Incidents', value: 0 });
  assert.match(html, />0<\/span>/);
  assert.doesNotMatch(html, /65%/);
});

test('empty alerts show a genuine empty state', async () => {
  const html = await render('components/dashboard/AlertList', 'AlertList', { alerts: [] });
  assert.match(html, /No incidents in this session/);
  assert.doesNotMatch(html, /Riverside|Flood Risk/);
});

test('alerts use actual backend fields and selected incident links', async () => {
  const html = await render('components/dashboard/AlertList', 'AlertList', { alerts: [{ incident_id: 'INC-042', category: 'Medical', priority: 'Critical', location: 'On Maple Street' }] });
  assert.match(html, /href="#\/incidents\/INC-042"/);
  assert.match(html, /Medical/);
  assert.match(html, /On Maple Street/);
  assert.match(html, /Awaiting human review/);
});

test('agent monitor renders recorded failures, not simulated progress', async () => {
  const html = await render('components/agent/AgentMonitor', 'AgentMonitor', {
    agents: { intake: 'failed' }, trace: [{ agent: 'intake', status: 'failed', model: 'test', duration_ms: 1, error: 'Parsing failed' }],
  });
  assert.match(html, /failed/);
  assert.match(html, /Parsing failed/);
  assert.doesNotMatch(html, />Running</);
});

test('incident assessment preserves unknown counts and escapes report markup', async () => {
  const html = await render('components/dashboard/IncidentDetails', 'IncidentDetails', { incident: {
    location: 'Unknown / Unspecified', affected_people: null, injuries_reported: false,
    raw_report: '<script>bad()</script>', missing_information: [], resources: [], action_plan: [], verification: {},
  } });
  assert.match(html, /Affected people: <\/span>Unknown/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /No resources matched/);
});

test('button primitives do not submit forms unless explicitly requested', async () => {
  const html = await render('components/ui/Button', 'Button', { children: 'Refresh' });
  assert.match(html, /type="button"/);
});

test('overview renders weather and OSM while incident data is still unavailable, without SSR network access', async (context) => {
  let requests = 0;
  context.mock.method(globalThis, 'fetch', () => { requests += 1; throw new Error('SSR must not fetch'); });
  const html = await render('pages/Dashboard', 'Dashboard');
  assert.match(html, /Loading session data/);
  assert.match(html, /Environmental map/);
  assert.match(html, /Modelled weather/);
  assert.match(html, /Loading weather for 52\.520000, 13\.410000/);
  assert.match(html, /Berlin example only/);
  assert.match(html, /selected WEATHER location only/);
  assert.match(html, /https:\/\/www\.openstreetmap\.org\/copyright/);
  assert.match(html, /OpenStreetMap contributors/);
  assert.match(html, /Report map issue/);
  assert.match(html, /Selected coordinates are sent via ResQAI to Open-Meteo/);
  assert.match(html, /Map tiles are requested directly from OpenStreetMap/);
  assert.match(html, /Modelled weather context, not an official emergency warning or verified incident conditions\./);
  assert.match(html, /for="weather-latitude"/);
  assert.match(html, /for="weather-longitude"/);
  assert.match(html, /type="submit"[^>]*>Apply location/);
  assert.equal(requests, 0);
});

test('history and agent views do not mount the weather map', async () => {
  for (const view of ['history', 'agents']) {
    const html = await render('pages/Dashboard', 'Dashboard', { view });
    assert.doesNotMatch(html, /Environmental map|weather-latitude/);
  }
});

test('weather readings preserve zero and null, label model coordinates, and use response timezone', async () => {
  const html = await render('components/dashboard/WeatherPanel', 'WeatherReadings', { weather: {
    requested_latitude: 52.52, requested_longitude: 13.41, latitude: 52.5, longitude: 13.4,
    timezone: 'Europe/Berlin', elevation: null, cache_ttl_seconds: 3600,
    current: { time: '2026-07-01T12:00:00Z', temperature_2m: 0, precipitation: 0, wind_speed_10m: null, relative_humidity_2m: null },
    hourly: [{ time: '2026-07-01T13:00:00Z', temperature_2m: null, precipitation_probability: 0 }],
    units: { temperature_2m: '°C', precipitation: 'mm', wind_speed_10m: 'km/h', relative_humidity_2m: '%', precipitation_probability: '%' },
  } });
  assert.match(html, />0 °C</);
  assert.match(html, />0 mm</);
  assert.match(html, />0 %</);
  assert.ok((html.match(/>—</g) || []).length >= 3);
  assert.match(html, /14:00/);
  assert.match(html, /15:00/);
  assert.match(html, /Europe\/Berlin/);
  assert.match(html, /Model timestamp/);
  assert.match(html, /60 minutes/);
  assert.match(html, /Requested: 52\.520000, 13\.410000 · Model grid: 52\.500000, 13\.400000/);
  assert.match(html, /Elevation: —/);
  assert.match(html, /<table/);
  assert.doesNotMatch(html, /NaN|undefined|null/);
});

test('empty hourly forecasts explain that no upcoming data is available', async () => {
  const html = await render('components/dashboard/WeatherPanel', 'WeatherReadings', { weather: {
    requested_latitude: 0, requested_longitude: 0, latitude: 0, longitude: 0,
    timezone: 'UTC', elevation: 0, cache_ttl_seconds: 3600,
    current: { time: '2026-07-01T12:00:00Z', temperature_2m: null, precipitation: null, wind_speed_10m: null, relative_humidity_2m: null },
    hourly: [], units: {},
  } });
  assert.match(html, /No upcoming hourly forecast is available/);
  assert.match(html, /Elevation: 0 m/);
});
