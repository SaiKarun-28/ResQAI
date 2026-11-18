// Leave unset for the same-origin Vite proxy; set for a separately hosted API.
const BASE_URL = (import.meta.env?.VITE_API_BASE_URL || '').replace(/\/+$/, '');

async function request(path, { signal, ...options } = {}) {
  const timeout = new AbortController();
  const timer = setTimeout(() => timeout.abort(), 120_000);
  try {
    const response = await fetch(`${BASE_URL}/api${path}`, {
      ...options,
      signal: signal ? AbortSignal.any([signal, timeout.signal]) : timeout.signal,
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers },
    });
    const text = await response.text();
    let data;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      throw new Error(`The API returned an invalid response (HTTP ${response.status}). Check that the backend is running and the API URL is correct.`);
    }
    if (!response.ok) {
      const detail = data?.detail;
      const message = Array.isArray(detail)
        ? detail.map((item) => item.msg || 'Invalid input').join('; ')
        : typeof detail === 'string' ? detail
          : [502, 503, 504].includes(response.status)
            ? `The ResQAI API is unavailable (HTTP ${response.status}). Check that the backend is running and retry.`
            : `Request failed (HTTP ${response.status}).`;
      throw new Error(message);
    }
    return data;
  } catch (error) {
    if (timeout.signal.aborted && !signal?.aborted) {
      throw new Error('The request timed out. Processing may still finish; check Incident History before submitting again.');
    }
    if (error instanceof TypeError) {
      throw new Error('Cannot reach the ResQAI API. Check that the backend is running and try again.');
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  async getIncidents(options) {
    const data = await request('/incidents', options);
    if (!Array.isArray(data)) throw new Error('The API returned an invalid incident list.');
    return data;
  },
  async getWeather(latitude, longitude, options) {
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)
      || latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
      throw new Error('Weather coordinates must be finite numbers: latitude −90 to 90 and longitude −180 to 180.');
    }
    const query = new URLSearchParams({ latitude: String(latitude), longitude: String(longitude) });
    return request(`/weather?${query}`, options);
  },
  getHealth: (options) => request('/health', options),
  createIncident: (data, options) => request('/incidents', { ...options, method: 'POST', body: JSON.stringify(data) }),
  getIncidentDetails: (id, options) => request(`/incidents/${encodeURIComponent(id)}`, options),
  getIncidentTrace: (id, options) => request(`/incidents/${encodeURIComponent(id)}/trace`, options),
  reviewIncident: (id, data, options) => request(`/incidents/${encodeURIComponent(id)}/review`, {
    ...options, method: 'POST', body: JSON.stringify(data),
  }),
};
