import { useState, type FormEvent } from "react";

import { PlaceField } from "./PlaceField";
import { defaultDepartureValue, isPast, localInputToIso } from "../lib/time";
import type { PlaceInput, PlanRequest } from "../types";

interface TripFormProps {
  loading: boolean;
  onSubmit: (request: PlanRequest) => void;
}

export function TripForm({ loading, onSubmit }: TripFormProps) {
  const [origin, setOrigin] = useState<PlaceInput | null>(null);
  const [destination, setDestination] = useState<PlaceInput | null>(null);
  const [departure, setDeparture] = useState(defaultDepartureValue);
  const [load, setLoad] = useState("34000");
  const [interval, setInterval] = useState<10 | 25 | 50>(25);
  const [formError, setFormError] = useState<string | null>(null);
  const past = isPast(departure);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!origin || !destination) {
      setFormError("Choose an origin and a destination from the suggestions.");
      return;
    }
    const loadLbs = Number(load);
    if (!Number.isInteger(loadLbs) || loadLbs < 1 || loadLbs > 80_000) {
      setFormError("Load weight must be a whole number from 1 to 80,000 lb.");
      return;
    }
    setFormError(null);
    onSubmit({
      origin,
      destination,
      departure: localInputToIso(departure),
      load_lbs: loadLbs,
      interval_mi: interval,
    });
  }

  return (
    <form className="trip-form" onSubmit={submit}>
      <PlaceField label="Origin" value={origin} onChange={setOrigin} />
      <PlaceField label="Destination" value={destination} onChange={setDestination} />
      <div className="field">
        <label htmlFor="departure">Departure</label>
        <input
          id="departure"
          type="datetime-local"
          value={departure}
          onChange={(event) => setDeparture(event.target.value)}
          required
        />
        {past && (
          <p className="hint">This departure is in the past. The forecast may no longer match.</p>
        )}
      </div>
      <div className="split">
        <div className="field">
          <label htmlFor="load">Load (lb)</label>
          <input
            id="load"
            inputMode="numeric"
            value={load}
            onChange={(event) => setLoad(event.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="interval">Checkpoint interval</label>
          <select
            id="interval"
            value={interval}
            onChange={(event) => setInterval(Number(event.target.value) as 10 | 25 | 50)}
          >
            <option value={10}>10 miles</option>
            <option value={25}>25 miles</option>
            <option value={50}>50 miles</option>
          </select>
        </div>
      </div>
      {formError && <p className="hint error">{formError}</p>}
      <button className="primary" type="submit" disabled={loading}>
        {loading ? "Planning…" : "Compare routes"}
      </button>
    </form>
  );
}
