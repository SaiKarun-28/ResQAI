import test, { afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { api } from '../src/services/api.js';
import {
  EXAMPLE_WEATHER_LOCATION, WEATHER_DISCLAIMER, coordinatesAreValid, parseCoordinates,
  normalizeMapCoordinates, formatWeatherValue, formatWeatherTime, nextForecastHours, validateWeather,
} from '../src/components/dashboard/weather.js';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
const weather = () => ({
  source: 'Open-Meteo', source_url: 'https://open-meteo.com/',
  requested_latitude: 52.52, requested_longitude: 13.41, latitude: 52.5, longitude: 13.4,
  elevation: null, timezone: 'Europe/Berlin', utc_offset_seconds: 7200, cache_ttl_seconds: 3600,
  current: { time: '2026-07-01T12:15:00+00:00', temperature_2m: 0, relative_humidity_2m: null, precipitation: 0, weather_code: 0, wind_speed_10m: null },
  hourly: [
    { time: '2026-07-01T12:00:00Z', temperature_2m: 0, precipitation_probability: null },
    { time: '2026-07-01T13:00:00Z', temperature_2m: null, precipitation_probability: 0 },
    { time: '2026-07-01T14:00:00Z', temperature_2m: 1, precipitation_probability: 30 },
  ],
  units: { temperature_2m: '°C', relative_humidity_2m: '%', precipitation: 'mm', wind_speed_10m: 'km/h', precipitation_probability: '%' },
  disclaimer: WEATHER_DISCLAIMER,
});

test('Berlin sample is explicitly an example, not a detected location', () => {
  assert.deepEqual(EXAMPLE_WEATHER_LOCATION, { latitude: 52.52, longitude: 13.41, isExample: true });
});

test('coordinate validation accepts numeric zero and boundary coordinates only within range', () => {
  for (const pair of [[0, 0], [-90, -180], [90, 180], [52.52, 13.41]]) assert.equal(coordinatesAreValid(...pair), true);
  for (const pair of [[90.01, 0], [0, 180.01], [-90.01, 0], [0, -180.01], [NaN, 0], [0, Infinity], ['0', 0], [null, 0]]) {
    assert.equal(coordinatesAreValid(...pair), false);
  }
});

test('keyboard coordinate parsing rejects empty, non-numeric and out-of-range input without changing locations', () => {
  assert.deepEqual(parseCoordinates(' 0 ', '-0'), { latitude: 0, longitude: -0, isExample: false });
  assert.deepEqual(parseCoordinates('-90', '1.8e2'), { latitude: -90, longitude: 180, isExample: false });
  for (const pair of [['', '0'], [' ', '13'], ['no', '0'], ['0x10', '0'], ['NaN', '0'], ['0', 'Infinity'], ['91', '0'], ['0', '-181'], [null, '0'], [false, 0]]) {
    assert.throws(() => parseCoordinates(...pair), /Enter|Latitude/);
  }
});

test('map selections clamp latitude and wrap longitude, never returning invalid coordinates', () => {
  assert.deepEqual(normalizeMapCoordinates(95, 190), { latitude: 90, longitude: -170, isExample: false });
  assert.deepEqual(normalizeMapCoordinates(-95, -190), { latitude: -90, longitude: 170, isExample: false });
  assert.equal(normalizeMapCoordinates(0, 1080).longitude, 0);
  assert.equal(normalizeMapCoordinates(0, 180).longitude, 180);
  assert.equal(normalizeMapCoordinates(0, -180).longitude, -180);
  assert.equal(normalizeMapCoordinates(NaN, 10), null);
  assert.equal(normalizeMapCoordinates(10, Infinity), null);
});

test('weather values distinguish zero from missing readings and never fabricate values', () => {
  assert.equal(formatWeatherValue(0, 'mm'), '0 mm');
  assert.equal(formatWeatherValue(0, '%'), '0 %');
  assert.equal(formatWeatherValue(-2.5, '°C'), '-2.5 °C');
  for (const value of [null, undefined, NaN, Infinity, '0', false]) assert.equal(formatWeatherValue(value, '°C'), '—');
});

test('timestamps use the response timezone, including DST, not the browser timezone', () => {
  assert.match(formatWeatherTime('2026-07-01T12:00:00Z', 'Europe/Berlin'), /14:00/);
  assert.match(formatWeatherTime('2026-07-01T12:00:00+00:00', 'UTC'), /12:00/);
  assert.match(formatWeatherTime('2026-03-29T00:30:00Z', 'Europe/Berlin'), /01:30/);
  assert.match(formatWeatherTime('2026-03-29T01:30:00Z', 'Europe/Berlin'), /03:30/);
  assert.equal(formatWeatherTime('2026-07-01T12:00:00', 'Europe/Berlin'), '—');
  assert.equal(formatWeatherTime('bad', 'UTC'), '—');
  assert.equal(formatWeatherTime('2026-07-01T12:00:00Z', 'invalid-zone'), '—');
  assert.equal(formatWeatherTime('2026-07-01T12:00:00Z'), '—');
});

test('next forecast hours are chronological, bounded, and relative to the model timestamp', () => {
  const data = weather();
  const reversed = [...data.hourly].reverse();
  assert.deepEqual(nextForecastHours(reversed, data.current.time), data.hourly.slice(1));
  assert.deepEqual(nextForecastHours(reversed, data.current.time, 1), data.hourly.slice(1, 2));
  assert.equal(reversed[0].time, data.hourly[2].time);
  assert.deepEqual(nextForecastHours([], data.current.time), []);
  assert.deepEqual(nextForecastHours(data.hourly, 'invalid'), []);
});

test('response validation preserves nulls and snapped coordinates and rejects malformed weather', () => {
  const data = weather();
  assert.equal(validateWeather(data), data);
  assert.notEqual(data.latitude, data.requested_latitude);
  assert.equal(validateWeather({ ...data, hourly: [] }).hourly.length, 0);
  for (const invalid of [
    null, {}, { ...data, latitude: 100 }, { ...data, timezone: 'bad-zone' },
    { ...data, current: { ...data.current, precipitation: '0' } },
    { ...data, current: { ...data.current, time: '2026-07-01T12:00:00' } },
    { ...data, hourly: null }, { ...data, hourly: [null] },
    { ...data, hourly: [{ ...data.hourly[0], temperature_2m: Infinity }] },
    { ...data, units: { ...data.units, temperature_2m: '°F' } },
  ]) assert.throws(() => validateWeather(invalid), /weather API returned invalid data/);
});

test('getWeather sends the exact numeric query contract, preserves options and returns model data', async () => {
  const controller = new AbortController();
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/weather?latitude=0&longitude=-180');
    assert.equal(options.signal.aborted, false);
    assert.equal(options.method, undefined);
    assert.equal(options.headers['X-Test'], 'weather');
    return json(weather());
  };
  assert.deepEqual(await api.getWeather(0, -180, { signal: controller.signal, headers: { 'X-Test': 'weather' } }), weather());
});

test('getWeather rejects invalid coordinates without sending any network requests', async () => {
  globalThis.fetch = async () => { assert.fail('Invalid coordinates must not fetch'); };
  for (const pair of [['52.52', 13.41], [null, 0], [NaN, 0], [0, Infinity], [91, 0], [0, -181]]) {
    await assert.rejects(api.getWeather(...pair), /Weather coordinates must be finite/);
  }
});

test('weather HTTP failures use existing readable error handling and can be retried', async () => {
  globalThis.fetch = async () => json({ detail: 'Open-Meteo is unavailable. Please retry.' }, 503);
  await assert.rejects(api.getWeather(52.52, 13.41), /Open-Meteo is unavailable/);
  globalThis.fetch = async () => json(weather());
  assert.equal((await api.getWeather(52.52, 13.41)).current.precipitation, 0);
});

test('weather request cancellation aborts the in-flight fetch before another location is requested', async () => {
  const controller = new AbortController();
  let signal;
  globalThis.fetch = async (_url, options) => new Promise((_resolve, reject) => {
    signal = options.signal;
    options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
  });
  const request = api.getWeather(52.52, 13.41, { signal: controller.signal });
  const assertion = assert.rejects(request, { name: 'AbortError' });
  controller.abort();
  await assertion;
  assert.equal(signal.aborted, true);
  globalThis.fetch = async () => json(weather());
  assert.equal((await api.getWeather(0, 0)).source, 'Open-Meteo');
});

test('map implementation uses approved tiles, modest viewport buffering and client-only Leaflet', async () => {
  const source = await readFile(new URL('../src/components/dashboard/MapPlaceholder.jsx', import.meta.url), 'utf8');
  assert.match(source, /https:\/\/tile\.openstreetmap\.org\/\{z\}\/\{x\}\/\{y\}\.png/);
  assert.match(source, /keepBuffer: 1/);
  assert.match(source, /import\('leaflet'\)/);
  assert.doesNotMatch(source, /from ['"]leaflet['"]|navigator\.geolocation|L\.marker\(/);
  assert.match(source, /L\.circleMarker\(/);
  assert.match(source, /tiles\.on\('tileerror'/);
  assert.match(source, /Retry map tiles/);
  assert.match(source, /observer\?\.disconnect\(\)/);
  assert.match(source, /map\?\.remove\(\)/);
});
