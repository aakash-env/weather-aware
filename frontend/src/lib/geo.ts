const EARTH_RADIUS_M = 6_371_000;
const METERS_PER_MILE = 1609.344;

export function haversineMiles(a: [number, number], b: [number, number]): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const phi1 = (lat1 * Math.PI) / 180;
  const phi2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLam = ((lon2 - lon1) * Math.PI) / 180;
  const h = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLam / 2) ** 2;
  return (2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)))) / METERS_PER_MILE;
}

export function cumulativeMiles(coordinates: [number, number][]): number[] {
  const totals = [0];
  for (let index = 1; index < coordinates.length; index += 1) {
    totals.push(totals[index - 1] + haversineMiles(coordinates[index - 1], coordinates[index]));
  }
  return totals;
}

export function sliceByMiles(
  coordinates: [number, number][],
  cumulative: number[],
  startMile: number,
  endMile: number,
): [number, number][] {
  if (coordinates.length === 0) return [];
  const start = pointAt(coordinates, cumulative, startMile);
  const end = pointAt(coordinates, cumulative, endMile);
  const middle = coordinates.filter((_, index) => {
    const mile = cumulative[index];
    return mile > startMile && mile < endMile;
  });
  return [start, ...middle, end];
}

function pointAt(
  coordinates: [number, number][],
  cumulative: number[],
  mile: number,
): [number, number] {
  if (mile <= 0) return coordinates[0];
  const total = cumulative[cumulative.length - 1];
  if (mile >= total) return coordinates[coordinates.length - 1];
  for (let index = 1; index < cumulative.length; index += 1) {
    if (cumulative[index] >= mile) {
      const span = cumulative[index] - cumulative[index - 1];
      const fraction = span <= 0 ? 0 : (mile - cumulative[index - 1]) / span;
      const [lon1, lat1] = coordinates[index - 1];
      const [lon2, lat2] = coordinates[index];
      return [lon1 + (lon2 - lon1) * fraction, lat1 + (lat2 - lat1) * fraction];
    }
  }
  return coordinates[coordinates.length - 1];
}
