// Time-range helpers shared by sidebar presets and modals.

export type Range = { from: string; to: string };

export function toLocalInput(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function toIsoZ(local: string): string {
  if (!local) return "";
  return new Date(local).toISOString();
}

export function defaultRange(): Range {
  const now = new Date();
  const from = new Date(now);
  from.setDate(from.getDate() - 1);
  return { from: toLocalInput(from), to: toLocalInput(now) };
}

function rangeDaysBack(days: number): Range {
  const now = new Date();
  const start = new Date(now);
  start.setDate(start.getDate() - days);
  return { from: toLocalInput(start), to: toLocalInput(now) };
}

export type Preset = { label: string; calc: () => Range };

export function getRangePresets(t: (key: string) => string): Preset[] {
  return [
    {
      label: t("dateRange.today"),
      calc: () => {
        const now = new Date();
        const start = new Date(now);
        start.setHours(0, 0, 0, 0);
        return { from: toLocalInput(start), to: toLocalInput(now) };
      },
    },
    {
      label: t("dateRange.24h"),
      calc: () => {
        const now = new Date();
        const start = new Date(now.getTime() - 24 * 3600 * 1000);
        return { from: toLocalInput(start), to: toLocalInput(now) };
      },
    },
    { label: t("dateRange.7d"), calc: () => rangeDaysBack(7) },
    { label: "30 d", calc: () => rangeDaysBack(30) },
  ];
}

export const RANGE_PRESETS: Preset[] = [
  {
    label: "Today",
    calc: () => {
      const now = new Date();
      const start = new Date(now);
      start.setHours(0, 0, 0, 0);
      return { from: toLocalInput(start), to: toLocalInput(now) };
    },
  },
  {
    label: "24 h",
    calc: () => {
      const now = new Date();
      const start = new Date(now.getTime() - 24 * 3600 * 1000);
      return { from: toLocalInput(start), to: toLocalInput(now) };
    },
  },
  { label: "7 d", calc: () => rangeDaysBack(7) },
  { label: "30 d", calc: () => rangeDaysBack(30) },
];
