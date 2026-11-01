import type { Level } from "../types";

export const LEVEL_COLOR: Record<Level, string> = {
  LOW: "#2f7d5a",
  MODERATE: "#c4920a",
  HIGH: "#d4651a",
  SEVERE: "#c0392b",
  NO_TRAVEL: "#6d3fa0",
  UNKNOWN: "#8b9098",
};

export const LEVEL_LABEL: Record<Level, string> = {
  LOW: "Low",
  MODERATE: "Moderate",
  HIGH: "High",
  SEVERE: "Severe",
  NO_TRAVEL: "No Travel",
  UNKNOWN: "Unknown",
};

export function levelColor(level: Level): string {
  return LEVEL_COLOR[level];
}
