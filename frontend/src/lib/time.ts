export function localInputToIso(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new Error("Departure is not a valid date.");
  }
  const pad = (part: number) => String(Math.trunc(Math.abs(part))).padStart(2, "0");
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const hours = pad(Math.floor(Math.abs(offsetMinutes) / 60));
  const minutes = pad(Math.abs(offsetMinutes) % 60);
  const stamp = value.length === 16 ? `${value}:00` : value;
  return `${stamp}${sign}${hours}:${minutes}`;
}

export function defaultDepartureValue(): string {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(8, 0, 0, 0);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function isPast(value: string): boolean {
  const date = new Date(value);
  return !Number.isNaN(date.getTime()) && date.getTime() < Date.now() - 60_000;
}

export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours <= 0) return `${rest} min`;
  return `${hours} h ${rest} min`;
}

export function formatWhen(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function formatHourLabel(startIso: string, hour: number): string {
  const start = new Date(startIso);
  if (Number.isNaN(start.getTime())) return `+${hour}h`;
  const at = new Date(start.getTime() + hour * 3_600_000);
  const clock = new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  }).format(at);
  return `${clock} · +${hour}h`;
}
