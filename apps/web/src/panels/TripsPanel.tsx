import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Device, Place, ShareLink, Trip, TripStats } from "../api";
import { EditDeleteActions } from "../components/RowActions";

type Props = {
  trips: Trip[];
  stats: Record<string, TripStats>;
  devices: Device[];
  places: Place[];
  shareLinks: ShareLink[];
  // Currently expanded trip (one at a time). Expanding flies the map to the
  // trip's track; collapsing clears the selection.
  selectedTripId: string | null;
  filterByTrip: boolean;
  onToggleFilterByTrip: () => void;
  onOpen: (t: Trip) => void;
  onToggleExpand: (t: Trip) => void;
  onClose: () => void;
  onFlyToPlace: (p: Place) => void;
  onEdit: (t: Trip) => void | Promise<void>;
  onDelete: (id: string) => void;
  onEnd: (t: Trip) => void;
  onDownload: (t: Trip, fmt: "gpx" | "csv") => void;
  onShare: (t: Trip, shareLinkId?: string) => void;
  onCopyShare: (linkId: string) => void;
};

export function TripsPanel({
  trips,
  stats,
  devices,
  places,
  shareLinks,
  selectedTripId,
  filterByTrip,
  onToggleFilterByTrip,
  onOpen,
  onToggleExpand,
  onClose,
  onFlyToPlace,
  onEdit,
  onDelete,
  onEnd,
  onDownload,
  onShare,
  onCopyShare,
}: Props) {
  const { t } = useTranslation();
  return (
    <div>
      {trips.length === 0 && <div className="empty">{t("trips.noTrips")}</div>}
      <ul className="list">
        {trips.map((t) => {
          const s = stats[t.id];
          const dev = devices.find((d) => d.id === t.device_id);
          const isOpen = t.id === selectedTripId;
          const linked = places.filter((p) => p.trip_ids.includes(t.id));
          const tripShareLinks = shareLinks.filter((link) => link.trip_id === t.id);
          return (
            <li
              key={t.id}
              className={`list-item trip-item${isOpen ? " open" : ""}`}
            >
              <div className="trip-header">
                <button
                  type="button"
                  className="trip-chevron-btn"
                  aria-expanded={isOpen}
                  aria-label={isOpen ? "Collapse trip" : "Expand trip"}
                  onClick={() => (isOpen ? onClose() : onToggleExpand(t))}
                >
                  <span className="chevron" aria-hidden="true">
                    ▸
                  </span>
                </button>
                <button
                  type="button"
                  className="trip-header-main-btn"
                  onClick={() => onOpen(t)}
                >
                  <span className="trip-header-main">
                    <span className="list-title">{t.name}</span>
                    <span className="muted small">
                      {dev ? `${dev.name} · ` : ""}
                      {new Date(t.started_at).toLocaleDateString()} →{" "}
                      {t.ended_at ? (
                        new Date(t.ended_at).toLocaleDateString()
                      ) : (
                        <span className="trip-ongoing">now</span>
                      )}
                    </span>
                  </span>
                </button>
              </div>
              <EditDeleteActions
                onEdit={() => onEdit(t)}
                onDelete={() => onDelete(t.id)}
                confirmDelete={`Delete trip "${t.name}"?`}
              />
              {isOpen && (
                <div className="trip-body">
                  {t.description && (
                    <div className="muted small">{t.description}</div>
                  )}
                  {s ? (
                    <div className="trip-stats">
                      <span>
                        You've travelled{" "}
                        <strong>
                          {s.distance_km.toFixed(s.distance_km < 10 ? 2 : 1)}
                        </strong>{" "}
                        km and had{" "}
                        <strong>
                          {Math.floor(Math.max(0, s.duration_s) / 86400)}
                        </strong>{" "}
                        amazing days!
                      </span>
                    </div>
                  ) : (
                    <div className="muted small">computing…</div>
                  )}
                  {t.ended_at === null && (
                    <div className="row gap" style={{ marginTop: "12px", marginBottom: "12px", flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="ghost small"
                        onClick={() => {
                          if (confirm(`End trip "${t.name}" now?`)) onEnd(t);
                        }}
                      >
                        End trip now
                      </button>
                    </div>
                  )}

                  <TripShareLinks
                    links={tripShareLinks}
                    onManageShare={(linkId) => onShare(t, linkId)}
                    onAddShare={() => onShare(t)}
                    onCopyShare={onCopyShare}
                  />

                  <TripPlaces
                    linked={linked}
                    filterByTrip={filterByTrip}
                    onToggleFilterByTrip={onToggleFilterByTrip}
                    onFlyToPlace={onFlyToPlace}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function TripPlaces({
  linked,
  filterByTrip,
  onToggleFilterByTrip,
  onFlyToPlace,
}: {
  linked: Place[];
  filterByTrip: boolean;
  onToggleFilterByTrip: () => void;
  onFlyToPlace: (p: Place) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="trip-places">
      <div className="row trip-places-head">
        <button
          type="button"
          className="trip-places-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          <span className={`chevron${open ? " open" : ""}`} aria-hidden="true">▸</span>
          <span className="trip-places-label">
            PLACES <span className="muted small">({linked.length})</span>
          </span>
        </button>
      </div>
      {open && (
        <>
          <label className="row gap small trip-filter-label">
            <input
              type="checkbox"
              checked={filterByTrip}
              onChange={onToggleFilterByTrip}
            />
            <span>Show only places linked to this trip</span>
          </label>
          {linked.length === 0 ? (
            <div className="muted small">No places linked yet. Edit a place to link it.</div>
          ) : (
            <ul className="list trip-places-list">
              {linked.map((p) => (
                <li
                  key={p.id}
                  className="list-item"
                  onClick={() => onFlyToPlace(p)}
                >
                  <div className="list-main">
                    <div className="list-title">{p.name}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function TripShareLinks({
  links,
  onManageShare,
  onAddShare,
  onCopyShare,
}: {
  links: ShareLink[];
  onManageShare: (linkId: string) => void;
  onAddShare: () => void;
  onCopyShare: (linkId: string) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <div className="trip-places" style={{ marginTop: "12px", marginBottom: "12px" }}>
      <div className="row trip-places-head">
        <button
          type="button"
          className="trip-places-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          <span className={`chevron${open ? " open" : ""}`} aria-hidden="true">▸</span>
          <span className="trip-places-label">
            {t("share.title").toUpperCase()} <span className="muted small">({links.length})</span>
          </span>
        </button>
      </div>
      {open && (
        <div style={{ marginTop: "8px" }}>
          {links.length > 0 && (
            <ul className="list trip-places-list" style={{ marginBottom: "8px" }}>
              {links.map((link) => (
                <li
                  key={link.id}
                  className="list-item"
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    cursor: "default",
                    padding: "8px 12px",
                    border: "1px solid var(--border-color, #eee)",
                    borderRadius: "4px",
                    marginBottom: "6px",
                    backgroundColor: "var(--bg-card, #fff)",
                  }}
                >
                  <div className="list-main" style={{ flex: 1, minWidth: 0, padding: 0 }}>
                    <div className="list-title" style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap", margin: 0, fontSize: "0.95rem" }}>
                      <span style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{link.name}</span>
                      {!link.is_active && (
                        <span className="share-link-badge" style={{ fontSize: "0.75rem", padding: "1px 6px" }}>
                          {t("share.paused")}
                        </span>
                      )}
                    </div>
                    <div className="muted small" style={{ fontSize: "0.75rem", marginTop: "2px" }}>
                      {t("share.delay")}: {link.delay_hours}h · {t("share.blur")}: {link.blur_meters}m
                    </div>
                  </div>
                  <button
                    type="button"
                    className="icon-btn"
                    style={{ marginLeft: "12px" }}
                    onClick={() => onCopyShare(link.id)}
                    title={t("share.copy")}
                    aria-label={t("share.copy")}
                  >
                    <CopyIcon />
                  </button>
                  <button
                    type="button"
                    className="ghost small"
                    style={{ padding: "4px 8px", marginLeft: "8px", fontSize: "0.8rem" }}
                    onClick={() => onManageShare(link.id)}
                  >
                    {t("share.manage")}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <button
            type="button"
            className="ghost small"
            style={{ width: "100%", justifyContent: "center" }}
            onClick={onAddShare}
          >
            {t("share.addLink")}
          </button>
        </div>
      )}
    </div>
  );
}

const iconProps = {
  width: 14,
  height: 14,
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function CopyIcon() {
  return (
    <svg {...iconProps}>
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}
