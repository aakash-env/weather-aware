import polyline from "@mapbox/polyline";

import { cumulativeMiles, sliceByMiles } from "./geo";
import type { Checkpoint, Level } from "../types";

export interface RiskSegment {
  level: Level;
  coordinates: [number, number][];
}

export function decodePolyline6(encoded: string): [number, number][] {
  return polyline.decode(encoded, 6).map(([lat, lon]) => [lon, lat]);
}

export function segmentBounds(miles: number[]): [number, number][] {
  if (miles.length === 0) return [];
  const total = miles[miles.length - 1];
  return miles.map((mile, index) => {
    const start = index === 0 ? 0 : (miles[index - 1] + mile) / 2;
    const end = index === miles.length - 1 ? total : (mile + miles[index + 1]) / 2;
    return [start, end];
  });
}

export function riskSegments(
  encoded: string,
  checkpoints: Checkpoint[],
  distanceMi: number,
): RiskSegment[] {
  const coordinates = decodePolyline6(encoded);
  if (coordinates.length < 2 || checkpoints.length === 0) return [];
  const geometryMiles = cumulativeMiles(coordinates);
  const geometryTotal = geometryMiles[geometryMiles.length - 1] || distanceMi || 1;
  const scale = distanceMi > 0 ? geometryTotal / distanceMi : 1;
  const bounds = segmentBounds(checkpoints.map((checkpoint) => checkpoint.mile));
  return checkpoints.map((checkpoint, index) => {
    const [start, end] = bounds[index];
    return {
      level: checkpoint.level,
      coordinates: sliceByMiles(coordinates, geometryMiles, start * scale, end * scale),
    };
  });
}
