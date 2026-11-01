import {
  GeoJSONSource,
  LngLatBounds,
  Map as MlMap,
  NavigationControl,
  Popup,
  type ExpressionSpecification,
} from "maplibre-gl";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

import { LEVEL_COLOR, LEVEL_LABEL } from "../lib/colors";
import { decodePolyline6, riskSegments } from "../lib/segments";
import { formatWhen } from "../lib/time";
import type { HeatmapPoint, Level, PlanResponse } from "../types";

const STYLE = "https://tiles.openfreemap.org/styles/positron";

export interface MapHandle {
  setHour: (hour: number) => void;
  setHeatmapVisible: (visible: boolean) => void;
}

interface MapViewProps {
  plan: PlanResponse | null;
  selectedId: string | null;
  onSelect: (routeId: string) => void;
}

type HeatMode = "expression" | "frames";

export const MapView = forwardRef<MapHandle, MapViewProps>(function MapView(
  { plan, selectedId, onSelect },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const readyRef = useRef(false);
  const onSelectRef = useRef(onSelect);
  const planRef = useRef(plan);
  const selectedRef = useRef(selectedId);

  useImperativeHandle(ref, () => ({
    setHour(hour: number) {
      const map = mapRef.current;
      if (!map || !map.getLayer("corridor-heat")) return;
      if (heatState.mode === "expression") {
        map.setPaintProperty("corridor-heat", "heatmap-weight", weightExpression(hour));
        return;
      }
      const frame = heatState.frames[hour];
      if (!frame) return;
      requestAnimationFrame(() => {
        const source = map.getSource("corridor-heat") as GeoJSONSource | undefined;
        source?.setData(frame);
      });
    },
    setHeatmapVisible(visible: boolean) {
      const map = mapRef.current;
      if (!map?.getLayer("corridor-heat")) return;
      map.setLayoutProperty("corridor-heat", "visibility", visible ? "visible" : "none");
    },
  }));

  function draw(map: MlMap) {
    const current = planRef.current;
    drawLayers(map, current);
  }

  function drawLayers(map: MlMap, current: PlanResponse | null) {
    clearLayers(map);
    if (!current || current.routes.length === 0) return;

    const other = current.routes.filter((route) => route.id !== selectedRef.current);
    const selected =
      current.routes.find((route) => route.id === selectedRef.current) ?? current.routes[0];
    const bounds = new LngLatBounds();

    map.addSource("routes-other", { type: "geojson", data: otherRoutes(other) });
    map.addLayer({
      id: "routes-other",
      type: "line",
      source: "routes-other",
      paint: { "line-color": "#8d93a0", "line-width": 4, "line-opacity": 0.85 },
    });

    const selectedFeatures = riskSegments(
      selected.geometry,
      selected.checkpoints,
      selected.distance_mi,
    );
    map.addSource("route-selected", {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features: selectedFeatures.map((segment) => ({
          type: "Feature" as const,
          properties: { color: LEVEL_COLOR[segment.level] },
          geometry: { type: "LineString" as const, coordinates: segment.coordinates },
        })),
      },
    });
    map.addLayer({
      id: "route-selected",
      type: "line",
      source: "route-selected",
      paint: { "line-color": ["get", "color"], "line-width": 6 },
    });

    const checkpoints = {
      type: "FeatureCollection" as const,
      features: selected.checkpoints.map((checkpoint) => ({
        type: "Feature" as const,
        properties: {
          color: LEVEL_COLOR[checkpoint.level],
          popup: popupHtml(checkpoint),
        },
        geometry: { type: "Point" as const, coordinates: [checkpoint.lon, checkpoint.lat] },
      })),
    };
    map.addSource("checkpoints", { type: "geojson", data: checkpoints });
    map.addLayer({
      id: "checkpoints",
      type: "circle",
      source: "checkpoints",
      paint: {
        "circle-radius": 6,
        "circle-color": ["get", "color"],
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2,
      },
    });

    for (const route of current.routes) {
      for (const checkpoint of route.checkpoints) {
        bounds.extend([checkpoint.lon, checkpoint.lat]);
      }
    }
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: 48, duration: 0 });
    }

    addHeat(map, current.heatmap.points);
  }

  useEffect(() => {
    onSelectRef.current = onSelect;
    planRef.current = plan;
    selectedRef.current = selectedId;
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const map = new MlMap({
      container,
      style: STYLE,
      center: [-98.5, 39.5],
      zoom: 3.4,
    });
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      readyRef.current = true;
      map.resize();
      bindClicks(map);
      draw(map);
    });
    mapRef.current = map;
    return () => {
      readyRef.current = false;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) draw(map);
  }, [plan, selectedId]);

  return (
    <div className="map-wrap">
      <div ref={containerRef} className="map" />
      <ul className="legend">
        {(Object.keys(LEVEL_COLOR) as Level[]).map((level) => (
          <li key={level}>
            <span style={{ background: LEVEL_COLOR[level] }} />
            {LEVEL_LABEL[level]}
          </li>
        ))}
      </ul>
    </div>
  );

  function bindClicks(map: MlMap) {
    const popup = new Popup({ closeButton: true, maxWidth: "280px" });
    map.on("click", "checkpoints", (event) => {
      const feature = event.features?.[0];
      const html = feature?.properties?.popup;
      if (!html) return;
      popup.setLngLat(event.lngLat).setHTML(String(html)).addTo(map);
    });
    map.on("click", "routes-other", (event) => {
      const routeId = event.features?.[0]?.properties?.routeId;
      if (routeId) onSelectRef.current(String(routeId));
    });
    map.on("mouseenter", "checkpoints", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "checkpoints", () => {
      map.getCanvas().style.cursor = "";
    });
    map.on("mouseenter", "routes-other", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "routes-other", () => {
      map.getCanvas().style.cursor = "";
    });
  }
});

function clearLayers(map: MlMap) {
  for (const id of ["corridor-heat", "checkpoints", "route-selected", "routes-other"]) {
    if (map.getLayer(id)) map.removeLayer(id);
    if (map.getSource(id)) map.removeSource(id);
  }
}

function otherRoutes(routes: PlanResponse["routes"]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: routes.map((route) => ({
      type: "Feature",
      properties: { routeId: route.id },
      geometry: { type: "LineString", coordinates: decodePolyline6(route.geometry) },
    })),
  };
}

function addHeat(map: MlMap, points: HeatmapPoint[]) {
  const expressionData: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features: points.map((point) => ({
      type: "Feature",
      properties: { r: point.r },
      geometry: { type: "Point", coordinates: [point.lon, point.lat] },
    })),
  };
  try {
    map.addSource("corridor-heat", { type: "geojson", data: expressionData });
    map.addLayer(
      {
        id: "corridor-heat",
        type: "heatmap",
        source: "corridor-heat",
        paint: {
          "heatmap-weight": weightExpression(0),
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 3, 0.7, 8, 1.5],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 3, 10, 6, 24, 9, 42],
          "heatmap-opacity": 0.8,
          "heatmap-color": heatColor(),
        },
      },
      "routes-other",
    );
    heatState.mode = "expression";
  } catch {
    if (map.getLayer("corridor-heat")) map.removeLayer("corridor-heat");
    if (map.getSource("corridor-heat")) map.removeSource("corridor-heat");
    const frames = buildFrames(points);
    heatState.frames = frames;
    map.addSource("corridor-heat", { type: "geojson", data: frames[0] });
    map.addLayer(
      {
        id: "corridor-heat",
        type: "heatmap",
        source: "corridor-heat",
        paint: {
          "heatmap-weight": ["get", "w"],
          "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 3, 0.7, 8, 1.5],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 3, 10, 6, 24, 9, 42],
          "heatmap-opacity": 0.8,
          "heatmap-color": heatColor(),
        },
      },
      "routes-other",
    );
    heatState.mode = "frames";
  }
}

const heatState: { mode: HeatMode; frames: GeoJSON.FeatureCollection[] } = {
  mode: "expression",
  frames: [],
};

function weightExpression(hour: number): ExpressionSpecification {
  return [
    "case",
    ["<", ["at", hour, ["get", "r"]], 0],
    0,
    ["interpolate", ["linear"], ["at", hour, ["get", "r"]], 0, 0.2, 4, 1],
  ];
}

function heatColor(): ExpressionSpecification {
  return [
    "interpolate",
    ["linear"],
    ["heatmap-density"],
    0,
    "rgba(0,0,0,0)",
    0.15,
    "rgba(47,125,90,0.5)",
    0.35,
    "rgba(196,146,10,0.7)",
    0.55,
    "rgba(212,101,26,0.8)",
    0.75,
    "rgba(192,57,43,0.88)",
    1,
    "rgba(109,63,160,0.95)",
  ];
}

function buildFrames(points: HeatmapPoint[]): GeoJSON.FeatureCollection[] {
  return Array.from({ length: 49 }, (_, hour) => ({
    type: "FeatureCollection",
    features: points.map((point) => {
      const value = point.r[hour] ?? -1;
      const weight = value < 0 ? 0 : 0.2 + (value / 4) * 0.8;
      return {
        type: "Feature" as const,
        properties: { w: weight },
        geometry: { type: "Point" as const, coordinates: [point.lon, point.lat] },
      };
    }),
  }));
}

function popupHtml(checkpoint: PlanResponse["routes"][number]["checkpoints"][number]): string {
  const weather = checkpoint.weather
    ? `Wind ${checkpoint.weather.wind_mph} mph (${LEVEL_LABEL[checkpoint.levels.wind]})<br>
       Rain ${checkpoint.weather.rain_in_hr} in/hr (${LEVEL_LABEL[checkpoint.levels.rain]})<br>
       Snow ${checkpoint.weather.snow_in_hr} in/hr (${LEVEL_LABEL[checkpoint.levels.snow]})`
    : "Forecast unavailable";
  const reasons = checkpoint.reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("");
  return `<strong>Mile ${checkpoint.mile.toFixed(1)}</strong><br>
    ETA ${escapeHtml(formatWhen(checkpoint.eta))}<br>
    ${weather}<br>
    Level: ${LEVEL_LABEL[checkpoint.level]}
    ${reasons ? `<ul>${reasons}</ul>` : ""}`;
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
