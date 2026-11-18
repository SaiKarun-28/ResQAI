"""Public, metric-only Open-Meteo weather context contract."""

from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class WeatherModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class CurrentWeather(WeatherModel):
    time: AwareDatetime
    temperature_2m: float | None
    relative_humidity_2m: float | None
    precipitation: float | None
    weather_code: float | None
    wind_speed_10m: float | None


class HourlyWeather(WeatherModel):
    time: AwareDatetime
    temperature_2m: float | None
    precipitation_probability: float | None


class WeatherUnits(WeatherModel):
    temperature_2m: Literal["°C"] = "°C"
    relative_humidity_2m: Literal["%"] = "%"
    precipitation: Literal["mm"] = "mm"
    wind_speed_10m: Literal["km/h"] = "km/h"
    precipitation_probability: Literal["%"] = "%"


class WeatherResponse(WeatherModel):
    source: Literal["Open-Meteo"] = "Open-Meteo"
    source_url: Literal["https://open-meteo.com/"] = "https://open-meteo.com/"
    requested_latitude: float = Field(ge=-90, le=90)
    requested_longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    elevation: float | None
    timezone: str
    utc_offset_seconds: int
    cache_ttl_seconds: Literal[3600] = 3600
    current: CurrentWeather
    hourly: list[HourlyWeather] = Field(min_length=24, max_length=24)
    units: WeatherUnits = Field(default_factory=WeatherUnits)
    disclaimer: Literal[
        "Modelled weather context, not an official emergency warning or verified incident conditions."
    ] = "Modelled weather context, not an official emergency warning or verified incident conditions."
