import type { GeocodeHit, PlanRequest, PlanResponse } from "../types";

const base = (import.meta.env.VITE_API_URL ?? "").trim();

function resolveUrl(path: string): string {
  if (!base) return path;
  const cleanBase = base.replace(/\/+$/, "");
  if (cleanBase.endsWith("/api") && path.startsWith("/api")) {
    return cleanBase + path.slice(4);
  }
  return `${cleanBase}${path}`;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function planTrip(body: PlanRequest): Promise<PlanResponse> {
  return request<PlanResponse>("/api/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function geocode(query: string): Promise<GeocodeHit[]> {
  const payload = await request<GeocodeHit[] | { detail: string }>(
    `/api/geocode?q=${encodeURIComponent(query)}`,
  );
  if (!Array.isArray(payload)) {
    throw new ApiError(502, payload.detail || "Geocoding failed.");
  }
  return payload;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(resolveUrl(path), init);
  } catch {
    throw new ApiError(0, "The server could not be reached.");
  }
  const text = await response.text();
  const payload = text ? (JSON.parse(text) as T & { detail?: string }) : ({} as T);
  if (!response.ok) {
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof payload.detail === "string"
        ? payload.detail
        : "";
    throw new ApiError(response.status, detail || `Request failed (${response.status}).`);
  }
  return payload;
}
