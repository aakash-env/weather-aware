import { encode } from "@mapbox/polyline";
import { describe, expect, it } from "vitest";

import { cumulativeMiles, sliceByMiles } from "./geo";
import { levelColor } from "./colors";
import { segmentBounds } from "./segments";
import { riskSegments } from "./segments";
import { localInputToIso } from "./time";
import type { Checkpoint } from "../types";

describe("sliceByMiles edge cases", () => {
  it("handles empty and single coordinate inputs", () => {
    expect(sliceByMiles([], [], 0, 10)).toEqual([]);
    expect(sliceByMiles([[0, 0]], [0], 0, 10)).toHaveLength(2);
  });

  it("handles boundaries at mile 0, total mile, and out of range", () => {
    const coords: [number, number][] = [
      [-100, 40],
      [-100, 41],
      [-100, 42],
    ];
    const cum = cumulativeMiles(coords);
    const total = cum[cum.length - 1];

    // Mile 0 to 0
    const zero = sliceByMiles(coords, cum, 0, 0);
    expect(zero).toHaveLength(2);
    expect(zero[0]).toEqual([-100, 40]);

    // Mile 0 to total
    const full = sliceByMiles(coords, cum, 0, total);
    expect(full.length).toBeGreaterThanOrEqual(3);
    expect(full[0]).toEqual([-100, 40]);
    expect(full[full.length - 1]).toEqual([-100, 42]);

    // Negative and out-of-range miles clamp gracefully
    const clamped = sliceByMiles(coords, cum, -10, total + 100);
    expect(clamped[0]).toEqual([-100, 40]);
    expect(clamped[clamped.length - 1]).toEqual([-100, 42]);
  });
});

describe("segment bounds", () => {
  it("covers the route from mile 0 to the end", () => {
    const bounds = segmentBounds([0, 25, 50, 100]);
    expect(bounds[0][0]).toBe(0);
    expect(bounds[bounds.length - 1][1]).toBe(100);
    const length = bounds.reduce((sum, [start, end]) => sum + (end - start), 0);
    expect(length).toBeCloseTo(100);
  });
});

describe("risk segments", () => {
  it("colors each checkpoint stretch", () => {
    const encoded = encode(
      [
        [40, -100],
        [41, -100],
      ],
      6,
    );
    const checkpoints: Checkpoint[] = [checkpoint(0, "LOW"), checkpoint(30, "HIGH")];
    const segments = riskSegments(encoded, checkpoints, 69);
    expect(segments).toHaveLength(2);
    expect(segments[0].level).toBe("LOW");
    expect(segments[1].level).toBe("HIGH");
    expect(segments[0].coordinates.length).toBeGreaterThan(1);
  });
});

describe("colors and departure", () => {
  it("maps levels to distinct colors", () => {
    expect(levelColor("NO_TRAVEL")).not.toBe(levelColor("LOW"));
    expect(levelColor("UNKNOWN")).toBe("#8b9098");
  });

  it("adds a numeric offset to a datetime-local value", () => {
    const iso = localInputToIso("2026-11-04T08:00");
    expect(iso.startsWith("2026-11-04T08:00:00")).toBe(true);
    expect(/[+-]\d{2}:\d{2}$/.test(iso)).toBe(true);
  });
});

function checkpoint(mile: number, level: Checkpoint["level"]): Checkpoint {
  return {
    idx: 0,
    mile,
    lat: 40,
    lon: -100,
    eta: "2026-11-04T08:00:00-06:00",
    weather: { wind_mph: 10, rain_in_hr: 0, snow_in_hr: 0 },
    levels: { wind: level, rain: "LOW", snow: "LOW" },
    level,
    segment_mi: 10,
    reasons: [],
    status: "ok",
  };
}
