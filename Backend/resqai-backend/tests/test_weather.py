"""Weather regressions use SDK-shaped stubs and an in-memory HTTP transport only."""

import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import Mock

import httpx
import numpy as np
import pytest
import requests
from fastapi.testclient import TestClient
from urllib3.response import HTTPResponse

from app.api import weather as weather_api
from app.main import app
from app.tools import weather


START = int(datetime(2025, 1, 15, 12, tzinfo=timezone.utc).timestamp())
CURRENT = START + 900
PARAMS = {"latitude": 52.52, "longitude": 13.41}


def provider_response():
    response = Mock()
    response.Latitude.return_value = np.float32(52.512604)
    response.Longitude.return_value = np.float32(13.419517)
    response.Elevation.return_value = np.float32(38)
    response.Timezone.return_value = b"Europe/Berlin"
    response.UtcOffsetSeconds.return_value = np.int32(3600)
    current = response.Current.return_value
    current.Time.return_value = np.int64(CURRENT)
    current.VariablesLength.return_value = 5
    current._variables = [Mock() for _ in range(5)]
    for variable, value in zip(current._variables, (9.7955, 79, 0, 2, 19.063)):
        variable.Value.return_value = np.float32(value)
    current.Variables.side_effect = current._variables.__getitem__
    hourly = response.Hourly.return_value
    hourly.Time.return_value = np.int64(START)
    hourly.TimeEnd.return_value = np.int64(START + 24 * 3600)
    hourly.Interval.return_value = np.int32(3600)
    hourly.VariablesLength.return_value = 2
    hourly._variables = [Mock(), Mock()]
    hourly._variables[0].ValuesAsNumpy.return_value = np.arange(24, dtype=np.float32)
    hourly._variables[1].ValuesAsNumpy.return_value = np.arange(24, dtype=np.float32) * 2
    hourly.Variables.side_effect = hourly._variables.__getitem__
    return response


@pytest.fixture(autouse=True)
def offline_weather(monkeypatch):
    def forbidden_network(*args, **kwargs):
        raise AssertionError("Weather tests must never access the network")

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", forbidden_network)
    service = weather.WeatherService()
    sdk = Mock()
    sdk.weather_api.return_value = [provider_response()]
    factory = Mock(return_value=sdk)
    monkeypatch.setattr(weather.openmeteo_requests, "Client", factory)
    monkeypatch.setattr(weather_api, "weather_service", service)
    yield service, sdk, factory
    service._discard_client()


def test_success_contract_and_metric_request(offline_weather):
    service, sdk, factory = offline_weather
    result = TestClient(app).get("/api/weather", params=PARAMS)
    assert result.status_code == 200
    body = result.json()
    assert set(body) == {
        "source", "source_url", "requested_latitude", "requested_longitude",
        "latitude", "longitude", "elevation", "timezone", "utc_offset_seconds",
        "cache_ttl_seconds", "current", "hourly", "units", "disclaimer",
    }
    assert body["source"] == "Open-Meteo"
    assert body["source_url"] == "https://open-meteo.com/"
    assert body["requested_latitude"] == PARAMS["latitude"]
    assert body["requested_longitude"] == PARAMS["longitude"]
    assert body["latitude"] == pytest.approx(52.512604)
    assert body["longitude"] == pytest.approx(13.419517)
    assert body["elevation"] == 38
    assert body["timezone"] == "Europe/Berlin"
    assert body["utc_offset_seconds"] == 3600
    assert body["cache_ttl_seconds"] == 3600
    assert body["current"] == {
        "time": "2025-01-15T12:15:00Z",
        "temperature_2m": pytest.approx(9.7955),
        "relative_humidity_2m": 79,
        "precipitation": 0,
        "weather_code": 2,
        "wind_speed_10m": pytest.approx(19.063),
    }
    assert len(body["hourly"]) == 24
    assert body["hourly"][0] == {
        "time": "2025-01-15T12:00:00Z", "temperature_2m": 0, "precipitation_probability": 0,
    }
    assert body["hourly"][-1] == {
        "time": "2025-01-16T11:00:00Z", "temperature_2m": 23, "precipitation_probability": 46,
    }
    assert body["units"] == {
        "temperature_2m": "°C", "relative_humidity_2m": "%", "precipitation": "mm",
        "wind_speed_10m": "km/h", "precipitation_probability": "%",
    }
    assert body["disclaimer"] == (
        "Modelled weather context, not an official emergency warning or verified incident conditions."
    )
    sdk.weather_api.assert_called_once_with(
        weather.FORECAST_URL,
        params={
            **PARAMS,
            "current": list(weather.CURRENT_VARIABLES),
            "hourly": list(weather.HOURLY_VARIABLES),
            "forecast_hours": 24, "timezone": "auto", "temperature_unit": "celsius",
            "wind_speed_unit": "kmh", "precipitation_unit": "mm",
        },
        timeout=10, allow_redirects=False,
    )
    factory.assert_called_once_with(session=service._session)
    assert service._session.headers["User-Agent"] == "ResQAI/1.0 weather-integration"
    assert service._session.settings.expire_after == 3600
    assert not service._session.settings.stale_if_error
    retries = service._session.get_adapter(weather.FORECAST_URL).max_retries
    assert retries.total == retries.connect == retries.read == 2
    assert retries.backoff_factor == 0.2
    assert not retries.respect_retry_after_header
    assert retries.allowed_methods == frozenset({"GET"})


@pytest.mark.parametrize("zone,offset", [
    (b"Europe/Berlin", 3600), (b"Asia/Kolkata", 19800), (b"America/New_York", -18000),
    (b"GMT", 0),
])
def test_provider_epochs_are_utc_not_local_wall_time(offline_weather, zone, offset):
    _, sdk, _ = offline_weather
    provider = sdk.weather_api.return_value[0]
    provider.Timezone.return_value = zone
    provider.UtcOffsetSeconds.return_value = offset
    result = TestClient(app).get("/api/weather", params=PARAMS).json()
    assert result["timezone"] == zone.decode()
    assert result["utc_offset_seconds"] == offset
    assert datetime.fromisoformat(result["current"]["time"].replace("Z", "+00:00")).timestamp() == CURRENT
    for index, point in enumerate(result["hourly"]):
        timestamp = datetime.fromisoformat(point["time"].replace("Z", "+00:00"))
        assert timestamp.utcoffset() == timedelta(0)
        assert timestamp.timestamp() == START + index * 3600


@pytest.mark.parametrize("params", [
    {}, {"latitude": 0}, {"longitude": 0},
    {"latitude": 90.001, "longitude": 0}, {"latitude": -90.001, "longitude": 0},
    {"latitude": 0, "longitude": 180.001}, {"latitude": 0, "longitude": -180.001},
    *[{**PARAMS, key: value} for key in PARAMS for value in (
        "NaN", "nan", "Inf", "+Infinity", "-inf", "1e999", "nope", "",
    )],
])
def test_coordinates_are_required_finite_and_bounded(offline_weather, params):
    _, sdk, factory = offline_weather
    response = TestClient(app).get("/api/weather", params=params)
    assert response.status_code == 422
    sdk.weather_api.assert_not_called()
    factory.assert_not_called()


@pytest.mark.parametrize("latitude,longitude", [(0, 0), (-90, -180), (90, 180)])
def test_coordinate_boundaries_are_accepted(latitude, longitude):
    result = TestClient(app).get("/api/weather", params={"latitude": latitude, "longitude": longitude})
    assert result.status_code == 200
    assert result.json()["requested_latitude"] == latitude
    assert result.json()["requested_longitude"] == longitude


@pytest.mark.parametrize("missing", [None, np.nan, np.inf, -np.inf, np.float32("nan")])
def test_missing_or_nonfinite_measurements_are_json_null(offline_weather, missing):
    _, sdk, _ = offline_weather
    provider = sdk.weather_api.return_value[0]
    provider.Elevation.return_value = missing
    for variable in provider.Current()._variables:
        variable.Value.return_value = missing
    for variable in provider.Hourly()._variables:
        variable.ValuesAsNumpy.return_value = np.array([missing] * 24)
    result = TestClient(app).get("/api/weather", params=PARAMS)
    assert result.status_code == 200

    def forbidden_constant(value):
        raise AssertionError(f"Non-JSON numeric constant: {value}")

    body = json.loads(result.text, parse_constant=forbidden_constant)
    assert body["elevation"] is None
    assert all(value is None for key, value in body["current"].items() if key != "time")
    assert body["current"]["time"]
    assert all(point["temperature_2m"] is None and point["precipitation_probability"] is None
               for point in body["hourly"])


@pytest.mark.parametrize("path,value", [
    ("Latitude", np.nan), ("Latitude", 91), ("Latitude", None),
    ("Longitude", np.inf), ("Longitude", -181),
    ("Timezone", None), ("Timezone", b""), ("Timezone", b"not/a-zone"),
    ("Timezone", b"\xff"), ("Timezone", b"/etc/passwd"),
    ("UtcOffsetSeconds", 90000), ("UtcOffsetSeconds", np.nan),
    ("Current", None), ("Hourly", None),
    ("Current.VariablesLength", 4), ("Current.VariablesLength", 6),
    ("Hourly.VariablesLength", 1), ("Hourly.VariablesLength", 3),
    ("Current.Time", None), ("Current.Time", 0), ("Current.Time", -1),
    ("Current.Time", START - 1), ("Current.Time", START + 24 * 3600),
    ("Current.Time", float(CURRENT)), ("Current.Time", 10**20),
    ("Hourly.Time", 0), ("Hourly.TimeEnd", 0), ("Hourly.TimeEnd", START),
    ("Hourly.TimeEnd", START + 23 * 3600), ("Hourly.TimeEnd", START + 25 * 3600),
    ("Hourly.Interval", 0), ("Hourly.Interval", -3600), ("Hourly.Interval", 1800),
])
def test_malformed_metadata_is_rejected_and_next_request_recovers(offline_weather, path, value):
    service, sdk, factory = offline_weather
    provider = sdk.weather_api.return_value[0]
    parts = path.split(".")
    target = provider
    for part in parts[:-1]:
        target = getattr(target, part)()
    getattr(target, parts[-1]).return_value = value
    client = TestClient(app)
    result = client.get("/api/weather", params=PARAMS)
    assert result.status_code == 502
    assert result.json() == {"detail": "Weather provider returned invalid data."}
    assert service._session is service._client is None
    sdk.weather_api.return_value = [provider_response()]
    assert client.get("/api/weather", params=PARAMS).status_code == 200
    assert factory.call_count == 2


@pytest.mark.parametrize("values", [[], [0] * 23, [0] * 25, [[0] * 24], 0, None, ["bad"] * 24])
def test_hourly_array_mismatch_and_invalid_measurements(offline_weather, values):
    _, sdk, _ = offline_weather
    sdk.weather_api.return_value[0].Hourly()._variables[1].ValuesAsNumpy.return_value = values
    result = TestClient(app).get("/api/weather", params=PARAMS)
    assert result.status_code == 502
    assert result.json() == {"detail": "Weather provider returned invalid data."}


@pytest.mark.parametrize("block", ["Current", "Hourly"])
def test_missing_variable_object_is_not_invented(offline_weather, block):
    _, sdk, _ = offline_weather
    getattr(sdk.weather_api.return_value[0], block)()._variables[0] = None
    assert TestClient(app).get("/api/weather", params=PARAMS).status_code == 502


@pytest.mark.parametrize("payload", [[], [None], [None, None], None])
def test_missing_or_multiple_provider_responses_are_rejected(offline_weather, payload):
    _, sdk, _ = offline_weather
    sdk.weather_api.return_value = payload
    assert TestClient(app).get("/api/weather", params=PARAMS).status_code == 502


@pytest.mark.parametrize("error", [requests.Timeout, requests.ConnectionError, RuntimeError])
def test_provider_failures_are_generic_and_recoverable(offline_weather, error):
    service, sdk, _ = offline_weather
    sdk.weather_api.side_effect = error("https://private.invalid/?key=secret internals")
    client = TestClient(app)
    result = client.get("/api/weather", params=PARAMS)
    assert result.status_code == 503
    assert result.json() == {"detail": "Weather context is temporarily unavailable."}
    assert service._session is service._client is None
    sdk.weather_api.side_effect = None
    assert client.get("/api/weather", params=PARAMS).status_code == 200


def test_factory_failure_is_generic(offline_weather):
    _, _, factory = offline_weather
    factory.side_effect = RuntimeError("private initialization details")
    response = TestClient(app).get("/api/weather", params=PARAMS)
    assert response.status_code == 503
    assert response.json() == {"detail": "Weather context is temporarily unavailable."}


@pytest.fixture
def cached_transport(monkeypatch, offline_weather):
    """Exercise real requests-cache without opening a socket or using provider fixtures."""
    service, sdk, factory = offline_weather
    state = {"calls": 0, "body": b"good", "status": 200}
    bad_provider = provider_response()
    bad_provider.Hourly()._variables[0].ValuesAsNumpy.return_value = np.zeros(23)

    def send(adapter, request, **kwargs):
        state["calls"] += 1
        response = requests.Response()
        response.status_code = state["status"]
        response.url = request.url
        response.request = request
        response._content = state["body"]
        response.raw = HTTPResponse(body=BytesIO(state["body"]), preload_content=False)
        return response

    def fetch(url, *, params, **kwargs):
        session = factory.call_args.kwargs["session"]
        response = session.get(url, params=params, **kwargs)
        response.raise_for_status()
        if response.content == b"decode-error":
            raise RuntimeError("SDK decode error with private upstream details")
        return [bad_provider if response.content == b"bad" else provider_response()]

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)
    sdk.weather_api.side_effect = fetch
    return service, state


def test_http_cache_ttl_expiry_and_coordinate_keys(cached_transport):
    service, state = cached_transport
    client = TestClient(app)
    first = client.get("/api/weather", params=PARAMS)
    assert first.status_code == 200
    second = client.get("/api/weather", params=PARAMS)
    assert second.json() == first.json()
    assert state["calls"] == 1
    cache = service._session.cache
    assert len(cache.responses) == 1
    for key, entry in list(cache.responses.items()):
        assert (entry.expires - entry.created_at).total_seconds() == pytest.approx(3600, abs=1)
        entry.expires = datetime.now(timezone.utc) - timedelta(seconds=1)
        cache.responses[key] = entry
    assert client.get("/api/weather", params=PARAMS).status_code == 200
    assert state["calls"] == 2
    other = client.get("/api/weather", params={**PARAMS, "latitude": 12.5})
    assert other.status_code == 200
    assert other.json()["requested_latitude"] == 12.5
    assert state["calls"] == 3


@pytest.mark.parametrize("body,status,expected", [
    (b"bad", 200, 502), (b"decode-error", 200, 503), (b"good", 503, 503),
])
def test_failed_or_malformed_http_responses_do_not_poison_cache(cached_transport, body, status, expected):
    service, state = cached_transport
    state.update(body=body, status=status)
    client = TestClient(app)
    assert client.get("/api/weather", params=PARAMS).status_code == expected
    assert service._session is None
    state.update(body=b"good", status=200)
    assert client.get("/api/weather", params=PARAMS).status_code == 200
    assert state["calls"] == 2
    assert client.get("/api/weather", params=PARAMS).status_code == 200
    assert state["calls"] == 2


def test_startup_and_non_weather_routes_do_not_initialize_client(offline_weather):
    service, _, factory = offline_weather
    assert service._session is None
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").status_code == 200
    factory.assert_not_called()


def test_weather_does_not_block_incidents_or_event_loop(offline_weather):
    _, sdk, _ = offline_weather
    entered, release = threading.Event(), threading.Event()
    event_loop_thread = threading.get_ident()

    def blocked_provider(*args, **kwargs):
        assert threading.get_ident() != event_loop_thread
        entered.set()
        if not release.wait(timeout=10):
            raise TimeoutError("Test did not release weather provider")
        return [provider_response()]

    sdk.weather_api.side_effect = blocked_provider

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            weather_request = asyncio.create_task(client.get("/api/weather", params=PARAMS))
            try:
                assert await asyncio.to_thread(entered.wait, 2)
                assert not weather_request.done()
                # Excess weather calls fail fast instead of occupying incident workers.
                others = await asyncio.wait_for(asyncio.gather(*[
                    client.get("/api/weather", params=PARAMS) for _ in range(48)
                ]), timeout=3)
                assert all(response.status_code == 503 for response in others)
                health = await asyncio.wait_for(client.get("/api/health"), timeout=2)
                assert health.status_code == 200
                incident = await asyncio.wait_for(client.post(
                    "/api/incidents", json={"report": "Medical emergency at 123 Main Street."},
                ), timeout=3)
                assert incident.status_code == 201
                assert not weather_request.done()
            finally:
                release.set()
                response = await weather_request
            assert response.status_code == 200
            assert sdk.weather_api.call_count == 1

    asyncio.run(scenario())
