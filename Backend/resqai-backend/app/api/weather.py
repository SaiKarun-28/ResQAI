"""Independent weather context endpoint; not part of incident triage."""

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.schemas.weather import WeatherResponse
from app.tools.weather import InvalidWeatherResponse, WeatherUnavailable, weather_service


router = APIRouter(prefix="/api", tags=["Weather context"])


@router.get(
    "/weather",
    response_model=WeatherResponse,
    summary="Get modelled current weather and 24 hourly forecasts",
    responses={
        502: {"description": "Invalid weather provider response"},
        503: {"description": "Weather context temporarily unavailable"},
    },
)
async def get_weather(
    latitude: float = Query(..., ge=-90, le=90, allow_inf_nan=False),
    longitude: float = Query(..., ge=-180, le=180, allow_inf_nan=False),
):
    try:
        return await run_in_threadpool(weather_service.fetch, latitude, longitude)
    except WeatherUnavailable:
        raise HTTPException(503, detail="Weather context is temporarily unavailable.") from None
    except InvalidWeatherResponse:
        raise HTTPException(502, detail="Weather provider returned invalid data.") from None
