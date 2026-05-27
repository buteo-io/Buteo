import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, OvernightSpot, Place, ShareLink, Trip } from "../api";
import { Select } from "../components/Select";

type ShareLinkPayload = Omit<ShareLink, "id" | "created_at" | "updated_at">;
type ShareLinkPatch = Partial<ShareLinkPayload>;

type Props = {
  shareLinks: ShareLink[];
  trips: Trip[];
  onRefresh: () => void;
  onToast: (msg: string) => void;
  prefilledTripId?: string | null;
  onClearPrefill?: () => void;
  prefilledShareLinkId?: string | null;
};

export function SharePanel({
  shareLinks,
  trips,
  onRefresh,
  onToast,
  prefilledTripId,
  onClearPrefill,
  prefilledShareLinkId,
}: Props) {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  useEffect(() => {
    if (prefilledTripId) {
      setCreating(true);
    }
    if (prefilledShareLinkId) {
      setEditingId(prefilledShareLinkId);
    }
  }, [prefilledTripId, prefilledShareLinkId]);

  const translateError = (msg: string): string => {
    if (msg.includes("Share link with this name already exists")) {
      return t("share.errors.duplicateName");
    }
    return msg;
  };

  const handleCancelCreate = () => {
    setCreating(false);
    onClearPrefill?.();
  };

  const handleSaveNew = async (data: ShareLinkPayload) => {
    try {
      const created = await api.createShareLink(data);
      handleCopyLink(created.token, t("share.linkCreatedCopied"));
      setCreating(false);
      onClearPrefill?.();
      onRefresh();
    } catch (e: any) {
      onToast(translateError(e.message));
    }
  };

  const handleEdit = (id: string) => {
    setEditingId(id);
  };

  const handleCancelEdit = () => {
    setEditingId(null);
    onClearPrefill?.();
  };

  const handleSaveEdit = async (id: string, data: ShareLinkPatch) => {
    try {
      await api.updateShareLink(id, data);
      onToast(t("share.linkUpdated"));
      setEditingId(null);
      onClearPrefill?.();
      onRefresh();
    } catch (e: any) {
      onToast(translateError(e.message));
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(t("share.confirmDelete"))) return;
    try {
      await api.deleteShareLink(id);
      onToast(t("share.linkDeleted"));
      if (editingId === id) {
        setEditingId(null);
        onClearPrefill?.();
      }
      onRefresh();
    } catch (e: any) {
      onToast(e.message);
    }
  };

  const handleRotateLink = async (id: string) => {
    try {
      const rotated = await api.rotateShareLink(id);
      handleCopyLink(rotated.token);
      onRefresh();
    } catch (e: any) {
      onToast(e.message);
    }
  };

  const handleCopyLink = (token: string, successToast?: string) => {
    const url = `${window.location.origin}/share/${token}`;
    void navigator.clipboard
      .writeText(url)
      .then(() => onToast(successToast || t("share.linkCopied")))
      .catch(() => onToast(t("share.copyFailed")));
  };

  return (
    <div className="share-panel">

      {creating && (
        <div className="card share-form-card">
          <ShareLinkForm
            trips={trips}
            prefilledTripId={prefilledTripId}
            onSave={(data) => {
              if (!data.trip_id || typeof data.is_active !== "boolean") {
                onToast("Missing required fields for new link");
                return;
              }
              void handleSaveNew(data as ShareLinkPayload);
            }}
            onCancel={handleCancelCreate}
          />
        </div>
      )}

      {shareLinks.length === 0 && !creating && (
        <div className="empty">{t("share.noLinks")}</div>
      )}

      <ul className="list share-links-list">
        {shareLinks.map((link) => {
          const trip = trips.find((t) => t.id === link.trip_id);
          const isEditing = editingId === link.id;

          if (isEditing) {
            return (
              <li key={link.id} className="list-item share-link-item share-link-item-edit">
                <ShareLinkForm
                  link={link}
                  trips={trips}
                  onSave={(data) => handleSaveEdit(link.id, data)}
                  onCancel={handleCancelEdit}
                  onDelete={handleDelete}
                />
              </li>
            );
          }

          return (
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
                  </div>
                <div className="share-link-meta">{t("share.trip")}: {trip?.name || t("share.unknown")}</div>
                {link.description && <div className="share-link-desc">{link.description}</div>}
                <div className="share-link-stats">
                  {t("share.delay")}: {link.delay_hours}h · {t("share.blur")}: {link.blur_meters}m · {t("share.places")}: {link.place_ids.length} · {t("share.overnights")}: {link.overnight_spot_ids.length}
                </div>
              </div>

              <div className="actions share-link-actions">
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => handleRotateLink(link.id)}
                  title="Copy link"
                  aria-label="Copy link"
                >
                  <CopyIcon />
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => handleEdit(link.id)}
                  title="Edit"
                  aria-label="Edit"
                >
                  <EditIcon />
                </button>
                <button
                  type="button"
                  className="icon-btn icon-btn-danger"
                  onClick={() => handleDelete(link.id)}
                  title="Delete"
                  aria-label="Delete"
                >
                  <DeleteIcon />
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

type FormProps = {
  link?: ShareLink;
  trips: Trip[];
  prefilledTripId?: string | null;
  onSave: (data: ShareLinkPayload | ShareLinkPatch) => void;
  onCancel: () => void;
  onDelete?: (id: string) => void;
};

function ShareLinkForm({ link, trips, prefilledTripId, onSave, onCancel, onDelete }: FormProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(
    link?.name ||
      (prefilledTripId
        ? `Share - ${trips.find((t) => t.id === prefilledTripId)?.name || ""}`
        : "")
  );
  const [description, setDescription] = useState(link?.description || "");
  const [tripId, setTripId] = useState(link?.trip_id || prefilledTripId || trips[0]?.id || "");
  const [useDelay, setUseDelay] = useState(link ? link.delay_hours > 0 : true);
  const [delayHours, setDelayHours] = useState<number | "">(link?.delay_hours ?? 72);
  const [useBlur, setUseBlur] = useState(link ? link.blur_meters > 0 : true);
  const [blurMeters, setBlurMeters] = useState(link?.blur_meters ?? 500);
  const [isActive, setIsActive] = useState(link?.is_active ?? true);
  const [places, setPlaces] = useState<Place[]>([]);
  const [placesLoading, setPlacesLoading] = useState(false);
  const [shareAllPlaces, setShareAllPlaces] = useState(link ? link.place_ids.length > 0 : false);
  const [selectedPlaceIds, setSelectedPlaceIds] = useState<Set<string>>(
    new Set(link?.place_ids ?? [])
  );
  const [overnightSpots, setOvernightSpots] = useState<OvernightSpot[]>([]);
  const [overnightSpotsLoading, setOvernightSpotsLoading] = useState(false);
  const [shareAllOvernightSpots, setShareAllOvernightSpots] = useState(link ? link.overnight_spot_ids.length > 0 : false);
  const [selectedOvernightSpotIds, setSelectedOvernightSpotIds] = useState<Set<string>>(
    new Set(link?.overnight_spot_ids ?? [])
  );
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  const effectiveTripId = link?.trip_id ?? tripId;

  useEffect(() => {
    if (!effectiveTripId) {
      setPlaces([]);
      return;
    }
    setPlacesLoading(true);
    api.tripPlaces(effectiveTripId)
      .then(setPlaces)
      .catch(() => setPlaces([]))
      .finally(() => setPlacesLoading(false));

    setOvernightSpotsLoading(true);
    api.tripOvernightSpots(effectiveTripId)
      .then(setOvernightSpots)
      .catch(() => setOvernightSpots([]))
      .finally(() => setOvernightSpotsLoading(false));
  }, [effectiveTripId]);

  const selectedTrip = trips.find((t) => t.id === effectiveTripId);

  const toInt = (value: string, fallback: number) => {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const placeIds = shareAllPlaces
      ? places.map((p) => p.id)
      : Array.from(selectedPlaceIds);
    const spotIds = shareAllOvernightSpots
      ? overnightSpots.map((s) => s.id)
      : Array.from(selectedOvernightSpotIds);
    const payload: ShareLinkPayload | ShareLinkPatch = {
      name,
      description: description || null,
      delay_hours: useDelay ? (delayHours === "" ? 72 : delayHours) : 0,
      blur_meters: useBlur ? blurMeters : 0,
      place_ids: placeIds,
      overnight_spot_ids: spotIds,
    };

    payload.trip_id = tripId;
    payload.is_active = isActive;

    onSave(payload);
  };

  const togglePlace = (placeId: string) => {
    const next = new Set(selectedPlaceIds);
    if (next.has(placeId)) {
      next.delete(placeId);
    } else {
      next.add(placeId);
    }
    setSelectedPlaceIds(next);
  };

  const toggleAll = () => {
    if (allSelected) {
      setSelectedPlaceIds(new Set());
    } else {
      setSelectedPlaceIds(new Set(places.map((p) => p.id)));
    }
  };

  const toggleEnablePlaces = () => {
    setShareAllPlaces(!shareAllPlaces);
    if (!shareAllPlaces) {
      setSelectedPlaceIds(new Set(places.map((p) => p.id)));
    }
  };

  const toggleOvernightSpot = (spotId: string) => {
    const next = new Set(selectedOvernightSpotIds);
    if (next.has(spotId)) {
      next.delete(spotId);
    } else {
      next.add(spotId);
    }
    setSelectedOvernightSpotIds(next);
  };

  const toggleAllOvernightSpots = () => {
    if (allOvernightSpotsSelected) {
      setSelectedOvernightSpotIds(new Set());
    } else {
      setSelectedOvernightSpotIds(new Set(overnightSpots.map((s) => s.id)));
    }
  };

  const toggleEnableOvernightSpots = () => {
    setShareAllOvernightSpots(!shareAllOvernightSpots);
    if (!shareAllOvernightSpots) {
      setSelectedOvernightSpotIds(new Set(overnightSpots.map((s) => s.id)));
    }
  };

  const allSelected = places.length > 0 && places.every((p) => selectedPlaceIds.has(p.id));
  const allOvernightSpotsSelected = overnightSpots.length > 0 && overnightSpots.every((s) => selectedOvernightSpotIds.has(s.id));

  return (
    <form onSubmit={handleSubmit} className="share-form">
      <div className="field">
        <label className="field-label">
          {t("share.name")} <span style={{ color: "var(--bad)" }}>*</span>
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          maxLength={200}
          placeholder={t("share.namePlaceholder")}
        />
      </div>

      <div className="field">
        <label className="field-label">{t("share.description")}</label>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={2000}
          rows={3}
          placeholder={t("share.descriptionPlaceholder")}
        />
      </div>

      <div className="field">
        <label className="field-label">
          {t("share.trip")} <span style={{ color: "var(--bad)" }}>*</span>
        </label>
        <Select
          value={tripId}
          onChange={(val) => setTripId(val)}
          options={trips.map((t) => ({ value: t.id, label: t.name }))}
        />
      </div>

      <div className="card share-privacy-card">
        <label className="share-inline-check">
          <input
            type="checkbox"
            checked={useDelay}
            onChange={(e) => setUseDelay(e.target.checked)}
          />
          <span>{t("share.delayData")}</span>
        </label>

        {useDelay && (
          <div className="field share-delay-field">
            <label className="field-label">{t("share.hours")}</label>
            <input
              type="number"
              value={delayHours}
              onChange={(e) => {
                const val = e.target.value;
                if (val === "") {
                  setDelayHours("");
                } else {
                  const parsed = Number.parseInt(val, 10);
                  if (Number.isFinite(parsed)) {
                    setDelayHours(parsed);
                  }
                }
              }}
              min={0}
              placeholder="72"
            />
            <div className="field-hint">{t("share.delayHint")}</div>
          </div>
        )}
      </div>

      <div className="card share-privacy-card">
        <label className="share-inline-check">
          <input
            type="checkbox"
            checked={useBlur}
            onChange={(e) => setUseBlur(e.target.checked)}
          />
          <span>{t("share.blurLocation")}</span>
        </label>

        {useBlur && (
          <div className="field share-delay-field">
            <label className="field-label">{t("share.blur")}</label>
            <Select
              value={String(blurMeters)}
              onChange={(val) => setBlurMeters(toInt(val, blurMeters))}
              options={[
                { value: "500", label: "500m" },
                { value: "2000", label: "2km" },
              ]}
            />
            <div className="field-hint">{t("share.blurHint")}</div>
          </div>
        )}
      </div>

      <div className="card share-privacy-card">
        <label className="share-inline-check">
          <input
            type="checkbox"
            checked={shareAllPlaces}
            onChange={toggleEnablePlaces}
          />
          <span>{t("share.shareConnectedPlaces")}</span>
        </label>

        {(shareAllPlaces || selectedPlaceIds.size > 0) && places.length > 0 && (
          <div className="share-places-tree">
            <label className="share-place-all">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={toggleAll}
              />
              <span>{t("share.allPlaces")} ({places.length})</span>
            </label>
            <div className="share-place-group-items" style={{ paddingLeft: "1.5rem", marginTop: "0.5rem" }}>
              {places.map((place) => (
                <label key={place.id} className="share-place-item" style={{ display: "flex", gap: "0.5rem", marginBottom: "0.25rem" }}>
                  <input
                    type="checkbox"
                    checked={selectedPlaceIds.has(place.id)}
                    onChange={() => togglePlace(place.id)}
                  />
                  <span>{place.name}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {placesLoading && (
          <div className="muted small">{t("share.loadingPlaces")}</div>
        )}
        {!placesLoading && places.length === 0 && (
          <div className="muted small">{t("share.noPlacesConnected")}</div>
        )}
      </div>

      <div className="card share-privacy-card">
        <label className="share-inline-check">
          <input
            type="checkbox"
            checked={shareAllOvernightSpots}
            onChange={toggleEnableOvernightSpots}
          />
          <span>{t("share.shareOvernightSpots")}</span>
        </label>

        {(shareAllOvernightSpots || selectedOvernightSpotIds.size > 0) && overnightSpots.length > 0 && (
          <div className="share-places-tree">
            <label className="share-place-all">
              <input
                type="checkbox"
                checked={allOvernightSpotsSelected}
                onChange={toggleAllOvernightSpots}
              />
              <span>{t("share.allOvernightSpots")} ({overnightSpots.length})</span>
            </label>
            <div className="share-place-group-items">
              {overnightSpots.map((spot) => (
                <label key={spot.id} className="share-place-item">
                  <input
                    type="checkbox"
                    checked={selectedOvernightSpotIds.has(spot.id)}
                    onChange={() => toggleOvernightSpot(spot.id)}
                  />
                  <span>{spot.name}</span>
                </label>
              ))}
            </div>
          </div>
        )}

        {overnightSpotsLoading && (
          <div className="muted small">{t("share.loadingOvernightSpots")}</div>
        )}
        {!overnightSpotsLoading && overnightSpots.length === 0 && (
          <div className="muted small">{t("share.noOvernightSpots")}</div>
        )}
      </div>

      <div className="card share-active-card">
        <label className="share-inline-check">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
          />
          <span>{t("share.active")}</span>
        </label>
      </div>

      <div className="share-form-actions">
        <button type="submit" className="primary">
          {link ? t("share.updateLink") : t("share.createLink")}
        </button>
        {link && onDelete && (
          <button
            type="button"
            className="danger ghost"
            style={{ color: "var(--bad)" }}
            onClick={() => onDelete(link.id)}
          >
            {t("common.delete")}
          </button>
        )}
        <button type="button" className="ghost" onClick={onCancel}>
          {t("common.cancel")}
        </button>
      </div>
    </form>
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

function DeleteIcon() {
  return (
    <svg {...iconProps}>
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    </svg>
  );
}
