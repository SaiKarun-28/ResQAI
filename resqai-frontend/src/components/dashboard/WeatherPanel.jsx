import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { Button } from '../ui/Button';
import { WEATHER_DISCLAIMER, formatWeatherTime, formatWeatherValue, nextForecastHours, parseCoordinates, validateWeather } from './weather';

export function WeatherReadings({ weather }) {
  const { current, units, timezone } = weather;
  const hours = nextForecastHours(weather.hourly, current.time);
  const readings = [
    ['Temperature', current.temperature_2m, units.temperature_2m],
    ['Precipitation', current.precipitation, units.precipitation],
    ['Wind speed', current.wind_speed_10m, units.wind_speed_10m],
    ['Humidity', current.relative_humidity_2m, units.relative_humidity_2m],
  ];
  return (
    <div className="space-y-3">
      <p className="text-xs text-text-muted">Model timestamp: <time dateTime={current.time}>{formatWeatherTime(current.time, timezone)}</time></p>
      <dl className="grid grid-cols-2 gap-2">
        {readings.map(([label, value, unit]) => <div key={label} className="bg-surface rounded-md p-3">
          <dt className="text-xs text-text-muted">{label}</dt>
          <dd className="text-xl font-semibold mt-1">{formatWeatherValue(value, unit)}</dd>
        </div>)}
      </dl>
      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <caption className="text-left font-semibold pb-2">Next forecast hours <span className="font-normal text-xs text-text-muted">· {timezone}</span></caption>
          <thead className="text-xs text-text-muted border-b border-border-default"><tr>
            <th scope="col" className="py-2 pr-2">Time</th>
            <th scope="col" className="py-2 px-2">Temp.</th>
            <th scope="col" className="py-2 pl-2">Precip. chance</th>
          </tr></thead>
          <tbody>{hours.map((hour) => <tr key={hour.time} className="border-b border-border-default">
            <th scope="row" className="py-2 pr-2 font-normal text-xs"><time dateTime={hour.time}>{formatWeatherTime(hour.time, timezone)}</time></th>
            <td className="py-2 px-2 whitespace-nowrap">{formatWeatherValue(hour.temperature_2m, units.temperature_2m)}</td>
            <td className="py-2 pl-2 whitespace-nowrap">{formatWeatherValue(hour.precipitation_probability, units.precipitation_probability)}</td>
          </tr>)}</tbody>
        </table>
        {hours.length === 0 && <p className="text-sm text-text-muted py-2">No upcoming hourly forecast is available.</p>}
      </div>
      <div className="text-xs text-text-muted space-y-1">
        <p>Hours shown from the current model timestamp. All times use {timezone}, not your browser timezone. — means unavailable, not zero.</p>
        <p>Requested: {weather.requested_latitude.toFixed(6)}, {weather.requested_longitude.toFixed(6)} · Model grid: {weather.latitude.toFixed(6)}, {weather.longitude.toFixed(6)} (may differ). Elevation: {formatWeatherValue(weather.elevation, 'm')}.</p>
        <p>Forecasts may be cached for {formatWeatherValue(weather.cache_ttl_seconds / 60, 'minutes')} by the API. Not a live sensor reading.</p>
      </div>
    </div>
  );
}

function WeatherLocationForm({ location, onLocationChange }) {
  const [latitude, setLatitude] = useState(String(location.latitude));
  const [longitude, setLongitude] = useState(String(location.longitude));
  const [inputError, setInputError] = useState('');
  const applyLocation = (event) => {
    event.preventDefault();
    try {
      const next = parseCoordinates(latitude, longitude);
      setInputError('');
      onLocationChange(next);
    } catch (failure) {
      setInputError(failure.message);
    }
  };
  return (
    <form onSubmit={applyLocation} noValidate className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label htmlFor="weather-latitude" className="block text-xs text-text-muted mb-1">Latitude (−90 to 90)</label>
          <input id="weather-latitude" type="number" min="-90" max="90" step="any" required value={latitude} onChange={(event) => setLatitude(event.target.value)} aria-invalid={Boolean(inputError)} aria-describedby={inputError ? 'weather-input-error' : undefined} className="w-full min-w-0 bg-surface border border-border-default rounded-md px-3 py-2 text-sm" />
        </div>
        <div>
          <label htmlFor="weather-longitude" className="block text-xs text-text-muted mb-1">Longitude (−180 to 180)</label>
          <input id="weather-longitude" type="number" min="-180" max="180" step="any" required value={longitude} onChange={(event) => setLongitude(event.target.value)} aria-invalid={Boolean(inputError)} aria-describedby={inputError ? 'weather-input-error' : undefined} className="w-full min-w-0 bg-surface border border-border-default rounded-md px-3 py-2 text-sm" />
        </div>
      </div>
      {inputError && <p id="weather-input-error" role="alert" className="text-sm text-red-300">{inputError}</p>}
      <Button type="submit" size="sm">Apply location</Button>
    </form>
  );
}

export function WeatherPanel({ location, onLocationChange }) {
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    api.getWeather(location.latitude, location.longitude, { signal: controller.signal })
      .then(validateWeather)
      .then((data) => {
        if (!controller.signal.aborted) setResult({ location, revision, data });
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setResult({ location, revision, error: failure.message || 'Weather is unavailable. Please retry.' });
      });
    return () => controller.abort();
  }, [location, revision]);

  // Identity matters: returning to the same coordinates must not reveal an older request.
  const activeResult = result?.location === location && result?.revision === revision ? result : null;
  const loading = !activeResult;

  return (
    <section aria-labelledby="weather-panel-title" className="bg-panel border border-border-default rounded-lg p-4 min-w-0 space-y-3">
      <header className="flex flex-wrap justify-between items-start gap-2">
        <div>
          <h2 id="weather-panel-title" className="font-semibold">Modelled weather</h2>
          <a href="https://open-meteo.com/" target="_blank" rel="noreferrer" className="text-xs text-accent-amber underline">Source: Open-Meteo</a>
        </div>
        <Button variant="secondary" size="sm" disabled={loading} onClick={() => setRevision((value) => value + 1)}>{activeResult?.error ? 'Retry weather' : 'Refresh weather'}</Button>
      </header>
      <p className="text-xs text-text-muted">Selected coordinates are sent via ResQAI to Open-Meteo to retrieve a forecast. This does not change any incident location.</p>
      {location.isExample && <p className="text-xs text-accent-amber">Berlin example only (52.52, 13.41). Apply coordinates or click the map to choose another location.</p>}
      <WeatherLocationForm key={`${location.latitude},${location.longitude}`} location={location} onLocationChange={onLocationChange} />
      <div aria-busy={loading}>
        {loading && <p role="status" className="text-sm text-accent-amber">Loading weather for {location.latitude.toFixed(6)}, {location.longitude.toFixed(6)}…</p>}
        {activeResult?.error && <div role="alert" className="text-sm text-red-300 space-y-1"><p>{activeResult.error}</p><p>Use Retry weather or choose another location. The map works independently.</p></div>}
        {activeResult?.data && <WeatherReadings weather={activeResult.data} />}
      </div>
      <p className="text-xs text-accent-amber border-t border-border-default pt-3">{WEATHER_DISCLAIMER}</p>
    </section>
  );
}
