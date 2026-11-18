"""Bounded synchronous Open-Meteo access; call from a worker, never the event loop."""

from datetime import datetime, timezone
from threading import Lock
from zoneinfo import ZoneInfo

import numpy as np
import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

from app.schemas.weather import CurrentWeather, HourlyWeather, WeatherResponse


FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_TTL_SECONDS = 3600
REQUEST_TIMEOUT_SECONDS = 10
FORECAST_HOURS = 24
CURRENT_VARIABLES = (
    "temperature_2m", "relative_humidity_2m", "precipitation",
    "weather_code", "wind_speed_10m",
)
HOURLY_VARIABLES = ("temperature_2m", "precipitation_probability")


class WeatherUnavailable(Exception):
    """The provider is unavailable or the weather worker is already occupied."""


class InvalidWeatherResponse(Exception):
    """Provider data cannot safely be represented as weather context."""


def _number(value):
    """Convert SDK/numpy measurements to JSON-safe Python scalars."""
    if isinstance(value, np.generic):
        value = value.item()
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Invalid numeric measurement")
    value = float(value)
    return value if np.isfinite(value) else None


def _integer(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Invalid integer metadata")
    return value


def _coordinate(value, limit):
    value = _number(value)
    if value is None or not -limit <= value <= limit:
        raise ValueError("Invalid coordinates")
    return value


def _timestamp(value):
    # FlatBuffers uses zero when a timestamp is absent. Do not invent a time.
    value = _integer(value)
    if value <= 0:
        raise ValueError("Missing timestamp")
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _parse_response(response, latitude, longitude):
    grid_latitude = _coordinate(response.Latitude(), 90)
    grid_longitude = _coordinate(response.Longitude(), 180)
    zone = response.Timezone()
    if isinstance(zone, bytes):
        zone = zone.decode("utf-8")
    if not isinstance(zone, str) or not zone or len(zone) > 128:
        raise ValueError("Missing timezone")
    ZoneInfo(zone)  # Reject unknown/malformed IANA zones rather than claiming UTC.
    utc_offset = _integer(response.UtcOffsetSeconds())
    if not -43200 <= utc_offset <= 50400:
        raise ValueError("Invalid UTC offset")

    current = response.Current()
    hourly = response.Hourly()
    if current is None or current.VariablesLength() != len(CURRENT_VARIABLES):
        raise ValueError("Missing current variables")
    if hourly is None or hourly.VariablesLength() != len(HOURLY_VARIABLES):
        raise ValueError("Missing hourly variables")

    current_time = _timestamp(current.Time())
    start = _timestamp(hourly.Time())
    end = _timestamp(hourly.TimeEnd())
    interval = _integer(hourly.Interval())
    if interval != 3600 or (end - start).total_seconds() != FORECAST_HOURS * interval:
        raise ValueError("Invalid hourly time range")
    if not start <= current_time < end:
        raise ValueError("Current timestamp outside forecast range")

    # SDK epochs are already UTC. Applying UtcOffsetSeconds again shifts the data.
    times = pd.date_range(
        start=start, end=end, freq=pd.Timedelta(seconds=interval), inclusive="left",
    )
    arrays = []
    for index in range(len(HOURLY_VARIABLES)):
        variable = hourly.Variables(index)
        if variable is None:
            raise ValueError("Missing hourly variable")
        values = np.asarray(variable.ValuesAsNumpy())
        if values.ndim != 1 or len(values) != len(times):
            raise ValueError("Hourly array length mismatch")
        arrays.append(values)

    current_values = {}
    for index, name in enumerate(CURRENT_VARIABLES):
        variable = current.Variables(index)
        if variable is None:
            raise ValueError("Missing current variable")
        current_values[name] = _number(variable.Value())

    return WeatherResponse(
        requested_latitude=latitude,
        requested_longitude=longitude,
        latitude=grid_latitude,
        longitude=grid_longitude,
        elevation=_number(response.Elevation()),
        timezone=zone,
        utc_offset_seconds=utc_offset,
        current=CurrentWeather(time=current_time, **current_values),
        hourly=[
            HourlyWeather(
                time=time.to_pydatetime(),
                **{name: _number(arrays[index][row]) for index, name in enumerate(HOURLY_VARIABLES)},
            )
            for row, time in enumerate(times)
        ],
    )


class WeatherService:
    def __init__(self):
        self._lock = Lock()
        self._session = None
        self._client = None

    def _get_client(self):
        # Lazy initialization: importing the app/startup never contacts the provider.
        if self._client is None:
            self._session = requests_cache.CachedSession(
                backend="memory", expire_after=CACHE_TTL_SECONDS,
                allowable_codes=(200,), allowable_methods=("GET",),
                stale_if_error=False,
            )
            self._session.headers.update({"User-Agent": "ResQAI/1.0 weather-integration"})
            session = retry(
                self._session, retries=2, backoff_factor=0.2,
                status_to_retry=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
                respect_retry_after_header=False,
            )
            self._client = openmeteo_requests.Client(session=session)
        return self._client

    def _discard_client(self):
        # A HTTP 200 can contain malformed data already cached by requests-cache.
        # Drop that in-memory cache on *any* failure, including SDK decoding errors.
        session = self._session
        self._session = self._client = None
        if session is not None:
            try:
                session.cache.clear()
                session.close()
            except Exception:
                pass  # Cleanup must not replace a sanitized provider error.

    def fetch(self, latitude: float, longitude: float) -> WeatherResponse:
        latitude = _coordinate(latitude, 90)
        longitude = _coordinate(longitude, 180)
        # Never queue weather requests behind a shared requests.Session lock:
        # waiting workers could exhaust the pool used by incident processing.
        if not self._lock.acquire(blocking=False):
            raise WeatherUnavailable() from None
        try:
            try:
                responses = self._get_client().weather_api(
                    FORECAST_URL,
                    params={
                        "latitude": latitude,
                        "longitude": longitude,
                        "current": list(CURRENT_VARIABLES),
                        "hourly": list(HOURLY_VARIABLES),
                        "forecast_hours": FORECAST_HOURS,
                        "timezone": "auto",
                        "temperature_unit": "celsius",
                        "wind_speed_unit": "kmh",
                        "precipitation_unit": "mm",
                    },
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    allow_redirects=False,
                )
            except Exception:
                self._discard_client()
                raise WeatherUnavailable() from None
            try:
                if len(responses) != 1:
                    raise ValueError("Expected one weather response")
                return _parse_response(responses[0], latitude, longitude)
            except Exception:
                self._discard_client()
                raise InvalidWeatherResponse() from None
        finally:
            self._lock.release()


weather_service = WeatherService()
