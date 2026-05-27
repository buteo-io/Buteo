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
  return (
    <>
      <div className="pin-dot" style={{ left: xy.x, top: xy.y }} />
      <div
        className="pin-tip"
        style={{ left: xy.x, top: xy.y }}
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
      >
        <button className="pin-close" onClick={onClose} aria-label="close">×</button>
        <div className="pin-meta">
          {p.speed != null ? `${p.speed.toFixed(0)} km/h` : "—"} ·{" "}
          {p.altitude != null ? `${Math.round(p.altitude)} m` : "—"}
        </div>
        <button className="primary small pin-more" onClick={onMore}>more →</button>
      </div>
    </>
  );
}
