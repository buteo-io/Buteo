// Display formatters used across the app.

export function fmtKm(km: number): string {
  if (km < 1) return `${Math.round(km * 1000)} m`;
  return `${km.toFixed(km < 10 ? 2 : 1)} km`;
}

export function fmtHm(s: number): string {
  const total = Math.max(0, Math.round(s / 60));
  const h = Math.floor(total / 60);
  const m = total - h * 60;
  return `${h}h ${m}m`;
}

export function fmtDuration(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)} min`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s - h * 3600) / 60);
  return `${h}h ${m}m`;
}
