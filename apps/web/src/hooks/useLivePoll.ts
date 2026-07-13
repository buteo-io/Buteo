import { useEffect, useState } from "react";
import { api, Position } from "../api";
import type { MapHandle } from "../components/Map";

const POLL_LIVE_MS = 5000;

type Args = {
  deviceId: string | null;
  deviceName: string | null;
  imei?: string;
  enabled: boolean;
  map: React.MutableRefObject<MapHandle | null>;
  onError?: (msg: string | null) => void;
};

/** Poll `/devices/:id/positions/latest` every 5s while enabled. Pushes the
 *  fix onto the map and fits the view on first arrival. */
export function useLivePoll({
  deviceId,
  deviceName,
  imei,
  enabled,
  map,
  onError,
}: Args) {
  const [latest, setLatest] = useState<Position | null>(null);

  useEffect(() => {
    if (!deviceId || !deviceName || !enabled) return;
    let cancelled = false;
    let firstFit = true;
    const tick = async () => {
      try {
        const p = await api.latest(deviceId);
        if (cancelled) return;
        setLatest(p);
        onError?.(null);
        if (p && map.current) {
          map.current.setDevice({ name: deviceName, imei, position: p });
          if (firstFit) {
            map.current.flyTo(p.lon, p.lat, 14);
            firstFit = false;
          }
        }
      } catch (e: unknown) {
        onError?.(e instanceof Error ? e.message : "live fetch failed");
      }
    };
    void tick();
    const id = setInterval(tick, POLL_LIVE_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [deviceId, deviceName, imei, enabled, map, onError]);

  return latest;
}
