"""Match a timestamp to the nearest forecast hour."""

from datetime import UTC, datetime, timedelta


def nearest_hour(times: list[datetime], moment: datetime) -> tuple[int, bool]:
    """Return the index of the closest hour and whether the moment is outside the window.

    Outside means more than 30 minutes before the first hour or after the last hour.
    The index is clamped to the ends when the moment is outside.
    """
    if moment.tzinfo is None:
        raise ValueError("moment must be timezone-aware")
    if not times:
        return 0, True
    if times[0].tzinfo is None:
        raise ValueError("forecast times must be timezone-aware")
    closest = min(range(len(times)), key=lambda index: abs((times[index] - moment).total_seconds()))
    margin = timedelta(minutes=30)
    if moment < times[0] - margin:
        return 0, True
    if moment > times[-1] + margin:
        return len(times) - 1, True
    return closest, False


def forecast_days_for(now: datetime, departure: datetime) -> int:
    """Open-Meteo counts forecast_days from today (UTC), up to 16.

    The request covers through departure + 72 hours so checkpoint ETAs and the
    48-hour heatmap fit. A fixed forecast_days=3 would drop trips that depart later.
    """
    end = departure + timedelta(hours=72)
    today = now.astimezone(UTC).date()
    end_date = end.astimezone(UTC).date()
    days = (end_date - today).days + 1
    return max(1, min(16, days))
