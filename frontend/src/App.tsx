import { useRef, useState } from "react";

import { ApiError, planTrip } from "./api/client";
import { HeatmapDock, type DockHandle } from "./components/HeatmapDock";
import { MapView, type MapHandle } from "./components/MapView";
import { RouteCards } from "./components/RouteCards";
import { TripForm } from "./components/TripForm";
import type { PlanRequest, PlanResponse } from "./types";

export default function App() {
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);
  const mapRef = useRef<MapHandle>(null);
  const dockRef = useRef<DockHandle>(null);

  async function onSubmit(request: PlanRequest) {
    setLoading(true);
    setError(null);
    setSlow(false);
    const timer = window.setTimeout(() => setSlow(true), 8000);
    try {
      const result = await planTrip(request);
      setPlan(result);
      setSelectedId(result.recommended_route_id);
      window.setTimeout(() => dockRef.current?.reset(), 0);
    } catch (caught) {
      const message =
        caught instanceof ApiError ? caught.message : "The trip could not be planned.";
      setError(message);
    } finally {
      window.clearTimeout(timer);
      setLoading(false);
      setSlow(false);
    }
  }

  return (
    <div className="app">
      <aside className="panel">
        <header className="brand">
          <p className="eyebrow">Weather-aware routing</p>
          <h1>Choose the safer road</h1>
          <p className="lede">
            Three driving options, sampled against the forecast at the hour the truck would arrive.
          </p>
        </header>
        <TripForm loading={loading} onSubmit={onSubmit} />
        {slow && loading && (
          <p className="hint">The server may be waking up. A free host can take up to a minute.</p>
        )}
        {error && <p className="banner error">{error}</p>}
        {plan && (
          <section className="results">
            {plan.meta.notices.map((notice) => (
              <p key={notice} className="banner">
                {notice}
              </p>
            ))}
            {plan.meta.warnings.map((warning) => (
              <p key={warning} className="banner warn">
                {warning}
              </p>
            ))}
            <p className="meta-line">
              Times are shown in your timezone. Routing: {plan.meta.routing_source}. Weather:{" "}
              {plan.meta.weather_source}.
            </p>
            <RouteCards plan={plan} selectedId={selectedId} onSelect={setSelectedId} />
          </section>
        )}
      </aside>
      <section className="stage">
        <MapView ref={mapRef} plan={plan} selectedId={selectedId} onSelect={setSelectedId} />
        {plan && (
          <HeatmapDock
            ref={dockRef}
            startIso={plan.heatmap.start}
            onHour={(hour) => mapRef.current?.setHour(hour)}
            onVisible={(visible) => mapRef.current?.setHeatmapVisible(visible)}
          />
        )}
      </section>
    </div>
  );
}
