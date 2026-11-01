"""Request validation for trip planning and geocoding."""

from rest_framework import serializers


class PlaceField(serializers.Field):
    """Accept a display string or an object with lat, lon, and an optional label."""

    def to_internal_value(self, data):
        if isinstance(data, str):
            query = data.strip()
            if not query:
                raise serializers.ValidationError("Enter a place.")
            return {"query": query}
        if isinstance(data, dict):
            try:
                lat = float(data["lat"])
                lon = float(data["lon"])
            except (KeyError, TypeError, ValueError) as exc:
                raise serializers.ValidationError("A place needs numeric lat and lon.") from exc
            if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise serializers.ValidationError("Coordinates are out of range.")
            label = str(data.get("label") or "")
            return {"lat": lat, "lon": lon, "label": label}
        raise serializers.ValidationError("A place must be a name or a lat/lon object.")

    def to_representation(self, value):
        return value


class PlanRequestSerializer(serializers.Serializer):
    origin = PlaceField()
    destination = PlaceField()
    departure = serializers.DateTimeField()
    load_lbs = serializers.IntegerField(min_value=1, max_value=80_000)
    interval_mi = serializers.ChoiceField(choices=[10, 25, 50], default=25)

    def validate_departure(self, value):
        raw = self.initial_data.get("departure") if hasattr(self, "initial_data") else None
        if isinstance(raw, str) and not _has_explicit_offset(raw):
            raise serializers.ValidationError(
                "Include a timezone offset, for example 2026-11-04T08:00:00-06:00."
            )
        if value.tzinfo is None or value.utcoffset() is None:
            raise serializers.ValidationError(
                "Include a timezone offset, for example 2026-11-04T08:00:00-06:00."
            )
        return value

    def validate(self, attrs):
        origin = attrs["origin"]
        destination = attrs["destination"]
        if "lat" in origin and "lat" in destination:
            same_lat = abs(origin["lat"] - destination["lat"]) < 1e-4
            same_lon = abs(origin["lon"] - destination["lon"]) < 1e-4
            if same_lat and same_lon:
                raise serializers.ValidationError("Origin and destination must be different.")
        if origin.get("query") and origin.get("query") == destination.get("query"):
            raise serializers.ValidationError("Origin and destination must be different.")
        return attrs


def _has_explicit_offset(text: str) -> bool:
    stamp = text.strip()
    if stamp.endswith(("Z", "z")):
        return True
    # The date portion uses dashes, so an offset dash or plus sits after the time.
    time_at = stamp.find("T")
    if time_at < 0:
        return False
    clock = stamp[time_at:]
    return "+" in clock or "-" in clock


def error_detail(errors) -> str:
    """Flatten serializer errors into one sentence a form can show."""
    parts: list[str] = []
    if isinstance(errors, list):
        return " ".join(str(item) for item in errors)
    if isinstance(errors, dict):
        for field, messages in errors.items():
            text = error_detail(messages)
            label = "Form" if field == "non_field_errors" else field
            parts.append(f"{label}: {text}")
    else:
        return str(errors)
    return " ".join(parts)
