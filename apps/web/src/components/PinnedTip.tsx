import { useTranslation } from "react-i18next";
import { Position } from "../api";

type Props = {
  position: Position;
  xy: { x: number; y: number };
  onMore: () => void;
  onClose: () => void;
};

/** Pin + small floating tooltip anchored to a clicked history point. */
export function PinnedTip({ position, xy, onMore, onClose }: Props) {
  const p = position;
  const { t } = useTranslation();
  return (
    <>
      <div className="pin-dot" style={{ left: xy.x, top: xy.y }} />
      <div
        className="pin-tip"
        style={{ left: xy.x, top: xy.y }}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="pin-close" onClick={onClose} aria-label="close">
          ×
        </button>
        <div className="pin-time">{new Date(p.time_id).toLocaleString()}</div>
        <div className="pin-meta">
          <strong>{t("popup.speed")}:</strong> {p.speed != null ? `${p.speed.toFixed(0)} km/h` : "—"}
        </div>
        <div className="pin-meta">
          <strong>{t("popup.altitude")}:</strong> {p.altitude != null ? `${Math.round(p.altitude)} m` : "—"}
        </div>
        <button className="primary small pin-more" onClick={onMore}>
          {t("common.more") || "more"} →
        </button>
      </div>
    </>
  );
}
