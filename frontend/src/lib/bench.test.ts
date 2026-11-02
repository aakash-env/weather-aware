import { describe, expect, it } from "vitest";
import { decodePolyline6, riskSegments } from "./segments";
import type { Checkpoint, HeatmapPoint } from "../types";

// Generate a synthetic cross-country route polyline and checkpoints
function generateMockRoute(numPoints: number, numCheckpoints: number) {
  // Approximate LA to NY coordinate stream
  const startLat = 34.05;
  const startLon = -118.24;
  const endLat = 40.71;
  const endLon = -74.0;

  const points: [number, number][] = [];
  for (let i = 0; i < numPoints; i++) {
    const fraction = i / (numPoints - 1);
    points.push([
      startLat + (endLat - startLat) * fraction + Math.sin(fraction * 20) * 0.1,
      startLon + (endLon - startLon) * fraction + Math.cos(fraction * 20) * 0.1,
    ]);
  }

  // Encode to polyline6
  // Polyline encoding
  const polyline = encodePolyline6(points);

  const checkpoints: Checkpoint[] = [];
  for (let i = 0; i < numCheckpoints; i++) {
    const fraction = i / (numCheckpoints - 1);
    const p = points[Math.floor(fraction * (numPoints - 1))];
    checkpoints.push({
      idx: i,
      mile: fraction * 2800,
      lat: p[0],
      lon: p[1],
      eta: "2026-11-04T12:00:00Z",
      weather: { wind_mph: 20, rain_in_hr: 0, snow_in_hr: 0 },
      levels: { wind: "LOW", rain: "LOW", snow: "LOW" },
      level: i % 10 === 0 ? "HIGH" : i % 5 === 0 ? "MODERATE" : "LOW",
      segment_mi: 2800 / numCheckpoints,
      reasons: [],
      status: "ok",
    });
  }

  const heatmapPoints: HeatmapPoint[] = checkpoints.map((cp) => ({
    lat: cp.lat,
    lon: cp.lon,
    r: Array.from({ length: 49 }, (_, h) => (h + cp.idx) % 5),
  }));

  return { polyline, checkpoints, heatmapPoints };
}

function encodePolyline6(coords: [number, number][]): string {
  // Simple test polyline encoder for precision 6
  let output = "";
  let prevLat = 0;
  let prevLon = 0;

  for (const [lat, lon] of coords) {
    const dLat = Math.round(lat * 1e6) - prevLat;
    const dLon = Math.round(lon * 1e6) - prevLon;
    prevLat = Math.round(lat * 1e6);
    prevLon = Math.round(lon * 1e6);

    output += encodeSigned(dLat) + encodeSigned(dLon);
  }
  return output;
}

function encodeSigned(num: number): string {
  let sgn = num < 0 ? ~(num << 1) : num << 1;
  let str = "";
  while (sgn >= 0x20) {
    str += String.fromCharCode((0x20 | (sgn & 0x1f)) + 63);
    sgn >>= 5;
  }
  str += String.fromCharCode(sgn + 63);
  return str;
}

function buildFrames(points: HeatmapPoint[]) {
  return Array.from({ length: 49 }, (_, hour) => ({
    type: "FeatureCollection" as const,
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

describe("Frontend Performance Baseline Benchmark", () => {
  it("measures geometry decoding, GeoJSON generation, heap, and slider tick frame time", () => {
    const { polyline, checkpoints, heatmapPoints } = generateMockRoute(12000, 115);

    // 1. Measure polyline decoding
    const t0 = performance.now();
    const decoded = decodePolyline6(polyline);
    const decodeTimeMs = performance.now() - t0;

    // 2. Measure riskSegments (building colored GeoJSON segments)
    const t1 = performance.now();
    const segments = riskSegments(polyline, checkpoints, 2800);
    const segmentsTimeMs = performance.now() - t1;

    // 3. Measure building 49 heatmap frames (fallback mode)
    const t2 = performance.now();
    const frames = buildFrames(heatmapPoints);
    const buildFramesTimeMs = performance.now() - t2;

    // 4. Measure slider frame time (simulating 49 slider ticks)
    const tickTimes: number[] = [];
    for (let h = 0; h < 49; h++) {
      const tickStart = performance.now();
      // Expression mode: O(1) expression evaluation
      const weight = heatmapPoints[0].r[h] >= 0 ? 0.2 + (heatmapPoints[0].r[h] / 4) * 0.8 : 0;
      // Frame mode: accessing prebuilt frame
      const frame = frames[h];
      const tickDuration = performance.now() - tickStart;
      tickTimes.push(tickDuration);
      expect(weight).toBeGreaterThanOrEqual(0);
      expect(frame.features.length).toBeGreaterThan(0);
    }
    const avgTickTimeMs = tickTimes.reduce((a, b) => a + b, 0) / tickTimes.length;
    const maxTickTimeMs = Math.max(...tickTimes);

    // 5. Memory footprint
    const processObj = (
      globalThis as unknown as { process?: { memoryUsage?: () => { heapUsed: number } } }
    ).process;
    const heapUsedMb = processObj?.memoryUsage
      ? processObj.memoryUsage().heapUsed / (1024 * 1024)
      : 0;

    console.log("==================================================================");
    console.log("FRONTEND PERFORMANCE BASELINE RESULTS (Cross-Country 12k vertices):");
    console.log("------------------------------------------------------------------");
    console.log(`- Polyline Decode (${decoded.length} pts):    ${decodeTimeMs.toFixed(3)} ms`);
    console.log(`- GeoJSON Segments (${segments.length} segs):  ${segmentsTimeMs.toFixed(3)} ms`);
    console.log(
      `- Build 49 Heatmap Frames (${heatmapPoints.length} pts): ${buildFramesTimeMs.toFixed(3)} ms`,
    );
    console.log(
      `- Slider Tick (Avg Frame Time):       ${avgTickTimeMs.toFixed(4)} ms (< 16.6 ms target)`,
    );
    console.log(`- Slider Tick (Max Frame Time):       ${maxTickTimeMs.toFixed(4)} ms`);
    console.log(`- JS Heap Used:                       ${heapUsedMb.toFixed(2)} MB`);
    console.log("==================================================================");
  });
});
