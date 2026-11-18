export const EXAMPLE_WEATHER_LOCATION = { latitude: 52.52, longitude: 13.41, isExample: true };
export const WEATHER_DISCLAIMER = 'Modelled weather context, not an official emergency warning or verified incident conditions.';

export function coordinatesAreValid(latitude, longitude) {
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    && latitude >= -90 && latitude <= 90 && longitude >= -180 && longitude <= 180;
}

export function parseCoordinates(latitude, longitude) {
  if (String(latitude).trim() === '' || String(longitude).trim() === '') {
    throw new Error('Enter both latitude and longitude.');
  }
  const numericInput = (value) => typeof value === 'number'
    || (typeof value === 'string' && /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value.trim()));
  if (!numericInput(latitude) || !numericInput(longitude)) {
    throw new Error('Enter finite numeric latitude and longitude values.');
  }
  const location = { latitude: Number(latitude), longitude: Number(longitude), isExample: false };
  if (!coordinatesAreValid(location.latitude, location.longitude)) {
    throw new Error('Latitude must be between −90 and 90; longitude between −180 and 180. Enter finite numbers.');
  }
  return location;
}

export function normalizeMapCoordinates(latitude, longitude) {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  const wrapped = longitude >= -180 && longitude <= 180
    ? longitude : ((longitude + 180) % 360 + 360) % 360 - 180;
  return {
    latitude: Number(Math.max(-90, Math.min(90, latitude)).toFixed(6)),
    longitude: Number(wrapped.toFixed(6)),
    isExample: false,
  };
}

export function formatWeatherValue(value, unit = '') {
  if (!Number.isFinite(value)) return '—';
  return `${new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 }).format(value)}${unit ? ` ${unit}` : ''}`;
}

function isUtcTime(value) {
  return typeof value === 'string' && /(?:Z|\+00:00)$/.test(value) && Number.isFinite(Date.parse(value));
}

export function formatWeatherTime(value, timezone) {
  if (!isUtcTime(value) || !timezone) return '—';
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: timezone, day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short',
    }).format(new Date(value));
  } catch {
    return '—';
  }
}

export function nextForecastHours(hourly, currentTime, limit = 6) {
  const start = Date.parse(currentTime);
  if (!Number.isFinite(start)) return [];
  return hourly.filter((hour) => isUtcTime(hour.time) && Date.parse(hour.time) >= start)
    .sort((a, b) => Date.parse(a.time) - Date.parse(b.time)).slice(0, limit);
}

// Reject malformed payloads instead of silently substituting weather readings.
export function validateWeather(data) {
  const nullableNumber = (value) => value === null || Number.isFinite(value);
  const currentFields = ['temperature_2m', 'relative_humidity_2m', 'precipitation', 'weather_code', 'wind_speed_10m'];
  const expectedUnits = { temperature_2m: '°C', relative_humidity_2m: '%', precipitation: 'mm', wind_speed_10m: 'km/h', precipitation_probability: '%' };
  if (!data || !coordinatesAreValid(data.requested_latitude, data.requested_longitude)
    || !coordinatesAreValid(data.latitude, data.longitude) || !nullableNumber(data.elevation)
    || typeof data.timezone !== 'string' || !Number.isFinite(data.utc_offset_seconds)
    || !Number.isFinite(data.cache_ttl_seconds) || data.cache_ttl_seconds < 0
    || !data.current || !isUtcTime(data.current.time)
    || formatWeatherTime(data.current.time, data.timezone) === '—'
    || !currentFields.every((field) => nullableNumber(data.current[field]))
    || !Array.isArray(data.hourly) || !data.hourly.every((hour) => hour && isUtcTime(hour.time)
      && nullableNumber(hour.temperature_2m) && nullableNumber(hour.precipitation_probability))
    || !Object.entries(expectedUnits).every(([field, unit]) => data.units?.[field] === unit)) {
    throw new Error('The weather API returned invalid data. Retry to request a new forecast.');
  }
  return data;
}
