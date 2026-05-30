import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, Place, OvernightSpot, MediaItem, Trip } from "../api";
import { Modal, Field } from "../components/Modal";
import { PlaceTypeIcon } from "../components/PlaceTypeIcon";

export type EntityDetailsModalState =
  | null
  | { type: "place"; place: Place }
  | { type: "overnight-spot"; spot: OvernightSpot };

type Props = {
  state: EntityDetailsModalState;
  trips: Trip[];
  onClose: () => void;
  onEdit?: (entity: Place | OvernightSpot, type: "place" | "overnight-spot") => void;
  onDelete?: (id: string) => Promise<void> | void;
  onMediaClick?: (media: MediaItem[], initialIdx: number) => void;
};

export function EntityDetailsModal({
  state,
  trips,
  onClose,
  onEdit,
  onDelete,
  onMediaClick,
}: Props) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  if (!state) return null;

  const isPlace = state.type === "place";
  const entity = isPlace ? state.place : state.spot;

  const handleCopyCoords = () => {
    const text = `${entity.lat.toFixed(6)}, ${entity.lon.toFixed(6)}`;
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getMediaUrl = (id: string) => api.serveMedia(id);

  // Find linked trips for Places or Overnight Spots
  const linkedTrips = isPlace
    ? trips.filter((tr) => (state.place.trip_ids ?? []).includes(tr.id))
    : trips.filter((tr) => state.spot.trip_id === tr.id);

  const title = isPlace ? entity.name : `${entity.name || t("entityModal.titleEdit_overnight-spot")}`;

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      footer={
        <div style={{ display: "flex", justifyContent: "space-between", width: "100%", gap: "8px" }}>
          <div>
            {isPlace && onDelete && (
              <button
                className="danger outline"
                onClick={() => {
                  if (confirm(t("places.confirmDelete", { name: entity.name }))) {
                    onDelete(entity.id);
                  }
                }}
              >
                {t("common.delete")}
              </button>
            )}
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button className="ghost" onClick={onClose}>
              {t("common.close")}
            </button>
            {onEdit && (
              <button
                className="primary"
                onClick={() => onEdit(entity, state.type)}
              >
                {t("common.edit")}
              </button>
            )}
          </div>
        </div>
      }
    >
      <div className="entity-details">
        {/* Category Header */}
        <div style={{ marginBottom: "8px" }}>
          {isPlace ? (
            <div className="type-chip active" style={{ cursor: "default", display: "inline-flex", gap: "6px", alignItems: "center" }}>
              <PlaceTypeIcon type={state.place.place_category} size={16} />
              <span style={{ fontSize: "13px", fontWeight: 500 }}>
                {t(`places.categories.${state.place.place_category}`)}
              </span>
            </div>
          ) : (
            <div className="type-chip active" style={{ cursor: "default", display: "inline-flex", gap: "6px", alignItems: "center", background: "#6366f1" }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
              <span style={{ fontSize: "13px", fontWeight: 500 }}>
                {t("overnightSpot.nights", { count: state.spot.nights_count })}
              </span>
            </div>
          )}
        </div>

        {/* Connected Trips (Section 1) */}
        <Field label={t("places.fields.trips")}>
          {linkedTrips.length === 0 ? (
            <div className="muted italic small" style={{ background: "var(--bg-card)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border)", textAlign: "center" }}>
              {t("common.none")}
            </div>
          ) : (
            <div className="tag-picker" style={{ gap: "4px" }}>
              {linkedTrips.map((tr) => (
                <span
                  key={tr.id}
                  className="chip active"
                  style={{ fontSize: "12px", cursor: "default" }}
                >
                  {tr.name}
                </span>
              ))}
            </div>
          )}
        </Field>

        {/* Position Details (Section 2) */}
        <Field label={t("detailsModal.title")}>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px", background: "var(--bg-card)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border)" }}>
            {/* Created At (2a) */}
            {!isPlace && (entity as OvernightSpot).created_at && (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "13px" }}>
                  <span className="muted">{t("detailsModal.createdAt")}</span>
                  <span className="mono" style={{ fontWeight: 500 }}>
                    {new Date((entity as OvernightSpot).created_at!).toLocaleString()}
                  </span>
                </div>
                
                {/* Divider */}
                <div style={{ height: "1px", background: "var(--line)" }} />
              </>
            )}

            {/* Coordinates (2b) */}
            <div style={{ display: "flex", gap: "12px", alignItems: "center", justifyContent: "space-between" }}>
              <span className="muted" style={{ fontSize: "13px" }}>{t("detailsModal.coordinates")}</span>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <span className="mono" style={{ fontSize: "13px", fontWeight: 500 }}>
                  {entity.lat.toFixed(6)}, {entity.lon.toFixed(6)}
                </span>
                <button
                  type="button"
                  className="ghost small"
                  onClick={handleCopyCoords}
                  style={{ 
                    padding: "4px 8px", 
                    display: "inline-flex", 
                    alignItems: "center", 
                    gap: "6px",
                    minWidth: "auto"
                  }}
                  title={copied ? t("share.copied") : t("share.copy")}
                >
                  {copied ? (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--good)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                  )}
                  <span style={{ fontSize: "12px" }}>
                    {copied ? t("share.copied") : t("share.copy")}
                  </span>
                </button>
              </div>
            </div>
          </div>
        </Field>

        {/* Comments (Section 3) */}
        <Field label={t("entityModal.comments")}>
          {entity.notes ? (
            <div className="entity-notes" style={{ whiteSpace: "pre-wrap", background: "var(--bg-card)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border)", fontSize: "14px", lineHeight: "1.5" }}>
              {entity.notes}
            </div>
          ) : (
            <div className="muted italic small" style={{ background: "var(--bg-card)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border)", textAlign: "center" }}>
              {t("entityModal.commentsPlaceholder")} ({t("common.none").toLowerCase()})
            </div>
          )}
        </Field>

        {/* Media (Section 4) */}
        {entity.media && entity.media.length > 0 && (
          <Field label={t("entityModal.media")}>
            <div className="media-grid">
              {entity.media.map((m, i) => (
                <div
                  key={m.id}
                  className="media-item"
                  style={{ cursor: onMediaClick ? "pointer" : "default" }}
                  onClick={() => onMediaClick?.(entity.media!, i)}
                >
                  {m.media_type === "image" ? (
                    <img src={getMediaUrl(m.id)} alt={m.filename_original} />
                  ) : (
                    <video src={getMediaUrl(m.id)} />
                  )}
                </div>
              ))}
            </div>
          </Field>
        )}
      </div>
    </Modal>
  );
}
