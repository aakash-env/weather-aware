import { LEVEL_COLOR, LEVEL_LABEL } from "../lib/colors";
import { formatDuration, formatWhen } from "../lib/time";
import type { Level, PlanResponse, RoutePlan } from "../types";

interface RouteCardsProps {
  plan: PlanResponse;
  selectedId: string | null;
  onSelect: (routeId: string) => void;
}

export function RouteCards({ plan, selectedId, onSelect }: RouteCardsProps) {
  const why = new Map(plan.ranking.map((entry) => [entry.route_id, entry.why]));
  return (
    <div className="cards">
      {plan.routes.map((route) => (
        <article key={route.id} className={route.id === selectedId ? "card selected" : "card"}>
          <button type="button" className="card-hit" onClick={() => onSelect(route.id)}>
            <header>
              <h2>{route.label}</h2>
              {route.id === plan.recommended_route_id && <span className="badge">Recommended</span>}
            </header>
            <p className="stats">
              {route.distance_mi.toFixed(0)} mi · {formatDuration(route.duration_min)}
              <br />
              Arrives {formatWhen(route.arrival_eta)}
            </p>
            <Bar route={route} />
            <dl>
              <div>
                <dt>Severe</dt>
                <dd>{route.summary.severe_mi.toFixed(1)} mi</dd>
              </div>
              <div>
                <dt>High</dt>
                <dd>{route.summary.high_mi.toFixed(1)} mi</dd>
              </div>
              <div>
                <dt>Moderate</dt>
                <dd>{route.summary.moderate_mi.toFixed(1)} mi</dd>
              </div>
              <div>
                <dt>Avg risk</dt>
                <dd>{route.summary.avg_risk === null ? "—" : route.summary.avg_risk.toFixed(2)}</dd>
              </div>
            </dl>
            {route.summary.unknown_mi > 0 && (
              <p className="hint">Forecast gaps: {route.summary.unknown_mi.toFixed(1)} mi</p>
            )}
            {route.summary.blocked && <p className="hint error">Includes No Travel conditions.</p>}
            <p className="why">{why.get(route.id)}</p>
          </button>
        </article>
      ))}
    </div>
  );
}

function Bar({ route }: { route: RoutePlan }) {
  const parts: { level: Level; miles: number }[] = [
    { level: "NO_TRAVEL", miles: route.summary.no_travel_mi },
    { level: "SEVERE", miles: route.summary.severe_mi },
    { level: "HIGH", miles: route.summary.high_mi },
    { level: "MODERATE", miles: route.summary.moderate_mi },
    { level: "LOW", miles: route.summary.low_mi },
    { level: "UNKNOWN", miles: route.summary.unknown_mi },
  ];
  const total = parts.reduce((sum, part) => sum + part.miles, 0) || 1;
  return (
    <div className="bar" aria-hidden="true">
      {parts.map((part) =>
        part.miles > 0 ? (
          <span
            key={part.level}
            style={{ width: `${(part.miles / total) * 100}%`, background: LEVEL_COLOR[part.level] }}
            title={`${LEVEL_LABEL[part.level]} ${part.miles.toFixed(1)} mi`}
          />
        ) : null,
      )}
    </div>
  );
}
