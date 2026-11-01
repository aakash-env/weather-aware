export type Level = "LOW" | "MODERATE" | "HIGH" | "SEVERE" | "NO_TRAVEL" | "UNKNOWN";

export interface PlaceInput {
  lat: number;
  lon: number;
  label: string;
}

export interface PlanRequest {
  origin: PlaceInput;
  destination: PlaceInput;
  departure: string;
  load_lbs: number;
  interval_mi: 10 | 25 | 50;
}

export interface GeocodeHit {
  label: string;
  lat: number;
  lon: number;
}

export interface Checkpoint {
  idx: number;
  mile: number;
  lat: number;
  lon: number;
  eta: string;
  weather: { wind_mph: number; rain_in_hr: number; snow_in_hr: number } | null;
  levels: { wind: Level; rain: Level; snow: Level };
  level: Level;
  segment_mi: number;
  reasons: string[];
  status: "ok" | "unknown" | "beyond_forecast";
}

export interface RouteSummary {
  severe_mi: number;
  high_mi: number;
  moderate_mi: number;
  low_mi: number;
  no_travel_mi: number;
  unknown_mi: number;
  avg_risk: number | null;
  max_level: Level;
  blocked: boolean;
}

export interface RoutePlan {
  id: string;
  label: string;
  geometry: string;
  distance_mi: number;
  duration_min: number;
  arrival_eta: string;
  summary: RouteSummary;
  checkpoints: Checkpoint[];
}

export interface RankingEntry {
  route_id: string;
  rank: number;
  why: string;
}

export interface HeatmapPoint {
  lat: number;
  lon: number;
  r: number[];
}

export interface PlanResponse {
  routes: RoutePlan[];
  recommended_route_id: string | null;
  ranking: RankingEntry[];
  heatmap: { hours: number; start: string; points: HeatmapPoint[] };
  meta: {
    assumptions: string[];
    weather_source: string;
    routing_source: string;
    generated_at: string;
    notices: string[];
    warnings: string[];
    origin: PlaceInput;
    destination: PlaceInput;
  };
}
