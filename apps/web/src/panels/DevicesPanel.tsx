// Devices panel: active device, live/history toggle, and per-mode controls.
// Live mode shows the last fix; history mode shows the range picker.
// Trip-scoped exports live in the Trips panel.

import { useTranslation } from "react-i18next";
import { Device, MAX_ANALYTICS_POINTS, Position } from "../api";
import { Range, getRangePresets } from "../utils/time";

type Mode = "live" | "history";

type Props = {
  devices: Device[];
  device: Device | null;
  onPickDevice: (d: Device) => void;

  latest: Position | null;

  mode: Mode;
  setMode: (m: Mode) => void;

  range: Range;
  setRange: (r: Range | ((prev: Range) => Range)) => void;
  busy: boolean;
  onApplyRange: () => void;
};

export function DevicesPanel(p: Props) {
  const { t } = useTranslation();
  return (
    <div className="devices-panel">
      {p.device ? (
        <>
          <div className="device-head">
            <div className="device-title">{p.device.name}</div>
            <div className="muted small mono">{p.device.imei}</div>
          </div>

          {/* view mode toggle — drives what the rest of the panel shows */}
          <div className="seg">
            <button
              className={p.mode === "live" ? "active" : ""}
              onClick={() => p.setMode("live")}
            >
              {t("devices.live")}
            </button>
            <button
              className={p.mode === "history" ? "active" : ""}
              onClick={() => p.setMode("history")}
            >
              {t("devices.history")}
            </button>
          </div>

          {p.mode === "live" ? (
            <>
              <h4>
                {t("devices.lastFix")}
                {p.latest &&
                  (() => {
                    const hoursAgo =
                      (Date.now() - new Date(p.latest.time_id).getTime()) /
                      (60 * 60 * 1000);
                    return hoursAgo > 2 ? (
                      <span
                        style={{
                          color: "red",
                          marginLeft: 8,
                          fontWeight: "normal",
                        }}
                      >
                        &gt;
                        {t("devices.hoursAgo", { hours: Math.floor(hoursAgo) })}
                      </span>
                    ) : null;
                  })()}
              </h4>
              {p.latest ? (
                <table className="kv">
                  <tbody>
                    <tr>
                      <th>{t("devices.time")}</th>
                      <td>{new Date(p.latest.time_id).toLocaleString()}</td>
                    </tr>
                    <tr>
                      <th>{t("devices.speed")}</th>
                      <td>
                        {p.latest.speed != null
                          ? `${p.latest.speed.toFixed(1)} km/h`
                          : "—"}
                      </td>
                    </tr>
                    <tr>
                      <th>{t("devices.altitude")}</th>
                      <td>
                        {p.latest.altitude != null
                          ? `${Math.round(p.latest.altitude)} m`
                          : "—"}
                      </td>
                    </tr>
                    <tr>
                      <th>{t("devices.satellites")}</th>
                      <td>{p.latest.satellites ?? "—"}</td>
                    </tr>
                  </tbody>
                </table>
              ) : (
                <div className="empty">{t("devices.noFix")}</div>
              )}
            </>
          ) : (
            <div className="range">
              <div className="presets">
                {getRangePresets(t).map((preset) => (
                  <button
                    key={preset.label}
                    onClick={() => p.setRange(preset.calc())}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
              <label>{t("devices.from")}</label>
              <input
                type="datetime-local"
                value={p.range.from}
                onChange={(e) =>
                  p.setRange((r) => ({ ...r, from: e.target.value }))
                }
              />
              <label>{t("devices.to")}</label>
              <input
                type="datetime-local"
                value={p.range.to}
                onChange={(e) =>
                  p.setRange((r) => ({ ...r, to: e.target.value }))
                }
              />
              <button
                className="primary"
                onClick={p.onApplyRange}
                disabled={p.busy}
              >
                {p.busy ? t("common.loading") : t("devices.apply")}
              </button>
              <p className="muted small">
                Analytics + exports cap at{" "}
                {MAX_ANALYTICS_POINTS.toLocaleString()} positions per request.
                Pick a smaller window if you hit the limit.
              </p>
            </div>
          )}
        </>
      ) : (
        <div className="empty">Pick a device below.</div>
      )}

      {/* device switcher */}
      {p.devices.length > 1 && (
        <>
          <h4>Switch device</h4>
          <ul className="list">
            {p.devices.map((d) => (
              <li
                key={d.id}
                className={`device-row ${p.device?.id === d.id ? "active" : ""}`}
                onClick={() => p.onPickDevice(d)}
              >
                <div className="name">{d.name}</div>
                <div className="imei mono">{d.imei}</div>
              </li>
            ))}
          </ul>
        </>
      )}
      {p.devices.length === 0 && (
        <div className="empty">
          No devices yet. Use the CLI to register one.
        </div>
      )}
    </div>
  );
}
