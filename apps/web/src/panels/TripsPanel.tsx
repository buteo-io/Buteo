import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Device, Place, ShareLink, Trip, TripStats } from "../api";

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
  onEnd: (t: Trip) => void;
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
  onEnd,
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
          const tripShareLinks = shareLinks.filter(
            (link) => link.trip_id === t.id,
          );
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
                    <span className="muted small">{dev?.name}</span>
                    <span className="muted small">
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
              <button
                className="icon-btn trip-edit-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(t);
                }}
                title="Edit"
                aria-label="Edit"
              >
                <svg
                  viewBox="0 0 24 24"
                  width="14"
                  height="14"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 20h9" />
                  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
                </svg>
              </button>
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
                    <div
                      className="row gap"
                      style={{
                        marginTop: "12px",
                        marginBottom: "12px",
                        flexWrap: "wrap",
                      }}
                    >
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
                    onEditShare={(linkId) => onShare(t, linkId)}
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
          <span className={`chevron${open ? " open" : ""}`} aria-hidden="true">
            ▸
          </span>
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
            <div className="muted small">
              No places linked yet. Edit a place to link it.
            </div>
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
  onEditShare,
  onAddShare,
  onCopyShare,
}: {
  links: ShareLink[];
  onEditShare: (linkId: string) => void;
  onAddShare: () => void;
  onCopyShare: (linkId: string) => void;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <div
      className="trip-places"
      style={{ marginTop: "12px", marginBottom: "12px" }}
    >
      <div className="row trip-places-head">
        <button
          type="button"
          className="trip-places-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
        >
          <span className={`chevron${open ? " open" : ""}`} aria-hidden="true">
            ▸
          </span>
          <span className="trip-places-label">
            {t("share.title").toUpperCase()}{" "}
            <span className="muted small">({links.length})</span>
          </span>
        </button>
      </div>
      {open && (
        <div style={{ marginTop: "8px" }}>
          {links.length > 0 && (
            <ul
              className="list trip-places-list"
              style={{ marginBottom: "8px" }}
            >
              {links.map((link) => (
                <li key={link.id} className="list-item share-link-item">
                  <div className="share-link-main">
                    <div className="share-link-title-row">
                      <strong>{link.name}</strong>
                      {link.is_active ? (
                        <span className="share-link-badge share-link-badge-active">
                          {t("share.enabled")}
                        </span>
                      ) : (
                        <span className="share-link-badge share-link-badge-disabled">
                          {t("share.disabled")}
                        </span>
                      )}
                      {link.has_password && (
                        <span className="share-link-badge share-link-badge-locked">
                          🔒
                        </span>
                      )}
                    </div>
                    <div className="share-link-stats">
                      {t("share.delay")}: {link.delay_hours}h ·{" "}
                      {t("share.blur")}: {link.blur_meters}m
                    </div>
                  </div>
                  <div className="actions share-link-actions">
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => onCopyShare(link.id)}
                      title={t("share.copy")}
                      aria-label={t("share.copy")}
                    >
                      <CopyIcon />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      onClick={() => onEditShare(link.id)}
                      title={t("share.edit")}
                      aria-label={t("share.edit")}
                    >
                      <EditIcon />
                    </button>
                  </div>
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
  viewBox: "0 0 24 24",
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

function EditIcon() {
  return (
    <svg {...iconProps}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z" />
    </svg>
  );
}
