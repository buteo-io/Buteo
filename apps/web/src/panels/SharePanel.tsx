import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, OvernightSpot, Place, ShareLink, Trip } from "../api";
import { Select } from "../components/Select";

type ShareLinkPayload = Omit<ShareLink, "id" | "created_at" | "updated_at"> & {
  password?: string | null;
};
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

  const isModalOpen = creating || editingId !== null;

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
    if (msg.includes("Rate limit exceeded")) {
      return t("share.errors.rateLimit");
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
    } catch (e: unknown) {
      onToast(translateError(e instanceof Error ? e.message : String(e)));
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
    } catch (e: unknown) {
      onToast(translateError(e instanceof Error ? e.message : String(e)));
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
    } catch (e: unknown) {
      onToast(e instanceof Error ? e.message : String(e));
    }
  };

  const handleRotateLink = async (id: string) => {
    try {
      const rotated = await api.rotateShareLink(id);
      handleCopyLink(rotated.token);
      onRefresh();
    } catch (e: unknown) {
      onToast(e instanceof Error ? e.message : String(e));
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
      {isModalOpen && (
        <div className="modal-backdrop">
          <div className="modal share-modal">
            <div className="modal-header">
              <h3>{editingId ? t("share.editLink") : t("share.newLink")}</h3>
              <button
                type="button"
                className="modal-close"
                onClick={editingId ? handleCancelEdit : handleCancelCreate}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              {creating && (
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
              )}
              {editingId && (
                <ShareLinkForm
                  link={shareLinks.find((l) => l.id === editingId)}
                  trips={trips}
                  onSave={(data) => handleSaveEdit(editingId, data)}
                  onCancel={handleCancelEdit}
                  onDelete={handleDelete}
                />
              )}
            </div>
          </div>
        </div>
      )}

      {shareLinks.length === 0 && !isModalOpen && (
        <div className="empty">{t("share.noLinks")}</div>
      )}

      <ul className="list share-links-list">
        {shareLinks.map((link) => {
          const trip = trips.find((t) => t.id === link.trip_id);

          return (
            <li key={link.id} className="list-item share-link-item">
              <div className="share-link-main">
                <div className="share-link-title-content">
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
                <div className="share-link-meta">
                  {t("share.trip")}: {trip?.name || t("share.unknown")}
                </div>
                {link.description && (
                  <div className="share-link-desc">{link.description}</div>
                )}
                <div className="share-link-stats">
                  {t("share.delay")}: {link.delay_hours}h · {t("share.blur")}:{" "}
                  {link.blur_meters}m · {t("share.places")}:{" "}
                  {link.place_ids.length} · {t("share.overnights")}:{" "}
                  {link.overnight_spot_ids.length}
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

function ShareLinkForm({
  link,
  trips,
  prefilledTripId,
  onSave,
  onCancel,
  onDelete,
}: FormProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(
    link?.name ||
      (prefilledTripId
        ? `Share - ${trips.find((t) => t.id === prefilledTripId)?.name || ""}`
        : ""),
  );
  const [description, setDescription] = useState(link?.description || "");
  const [tripId, setTripId] = useState(
    link?.trip_id || prefilledTripId || trips[0]?.id || "",
  );
  const [useDelay, setUseDelay] = useState(link ? link.delay_hours > 0 : true);
  const [delayHours, setDelayHours] = useState<number | "">(
    link?.delay_hours ?? 72,
  );
  const [useBlur, setUseBlur] = useState(link ? link.blur_meters > 0 : true);
  const [blurMeters, setBlurMeters] = useState(link?.blur_meters ?? 500);
  const [isActive, setIsActive] = useState(link?.is_active ?? true);
  const [usePassword, setUsePassword] = useState(!!link?.has_password);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [places, setPlaces] = useState<Place[]>([]);
  const [placesLoading, setPlacesLoading] = useState(false);
  const [shareAllPlaces, setShareAllPlaces] = useState(
    link ? link.place_ids.length > 0 : false,
  );
  const [selectedPlaceIds, setSelectedPlaceIds] = useState<Set<string>>(
    new Set(link?.place_ids ?? []),
  );
  const [overnightSpots, setOvernightSpots] = useState<OvernightSpot[]>([]);
  const [overnightSpotsLoading, setOvernightSpotsLoading] = useState(false);
  const [shareAllOvernightSpots, setShareAllOvernightSpots] = useState(
    link ? link.overnight_spot_ids.length > 0 : false,
  );
  const [selectedOvernightSpotIds, setSelectedOvernightSpotIds] = useState<
    Set<string>
  >(new Set(link?.overnight_spot_ids ?? []));
  const effectiveTripId = link?.trip_id ?? tripId;

  useEffect(() => {
    if (!effectiveTripId) {
      setPlaces([]);
      return;
    }
    setPlacesLoading(true);
    api
      .tripPlaces(effectiveTripId)
      .then(setPlaces)
      .catch(() => setPlaces([]))
      .finally(() => setPlacesLoading(false));

    setOvernightSpotsLoading(true);
    api
      .tripOvernightSpots(effectiveTripId)
      .then(setOvernightSpots)
      .catch(() => setOvernightSpots([]))
      .finally(() => setOvernightSpotsLoading(false));
  }, [effectiveTripId]);

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

    if (usePassword) {
      if (password) {
        payload.password = password;
      }
    } else if (link?.has_password) {
      payload.password = "";
    }

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

  const allSelected =
    places.length > 0 && places.every((p) => selectedPlaceIds.has(p.id));
  const allOvernightSpotsSelected =
    overnightSpots.length > 0 &&
    overnightSpots.every((s) => selectedOvernightSpotIds.has(s.id));

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
            checked={usePassword}
            onChange={(e) => {
              setUsePassword(e.target.checked);
              if (!e.target.checked) {
                setPassword("");
              }
            }}
          />
          <span>{t("share.passwordProtect")}</span>
        </label>

        {usePassword && (
          <div className="field share-delay-field">
            <label className="field-label">
              {link?.has_password
                ? t("share.newPassword")
                : t("share.password")}
            </label>
            <div className="password-input-wrapper">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={
                  link?.has_password
                    ? "•••••••• (leave blank to keep)"
                    : "Enter password"
                }
                maxLength={256}
              />
              <button
                type="button"
                className="password-toggle-btn"
                onClick={() => setShowPassword(!showPassword)}
                title={showPassword ? "Hide password" : "Show password"}
                aria-label={showPassword ? "Hide password" : "Show password"}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {link?.has_password && (
              <div
                className="field-hint"
                style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}
              >
                This link currently has password protection enabled. Enter a new
                password to change it, or uncheck password protection to remove
                it.
              </div>
            )}
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
              <span>
                {t("share.allPlaces")} ({places.length})
              </span>
            </label>
            <div
              className="share-place-group-items"
              style={{ paddingLeft: "1.5rem", marginTop: "0.5rem" }}
            >
              {places.map((place) => (
                <label
                  key={place.id}
                  className="share-place-item"
                  style={{
                    display: "flex",
                    gap: "0.5rem",
                    marginBottom: "0.25rem",
                  }}
                >
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

        {(shareAllOvernightSpots || selectedOvernightSpotIds.size > 0) &&
          overnightSpots.length > 0 && (
            <div className="share-places-tree">
              <label className="share-place-all">
                <input
                  type="checkbox"
                  checked={allOvernightSpotsSelected}
                  onChange={toggleAllOvernightSpots}
                />
                <span>
                  {t("share.allOvernightSpots")} ({overnightSpots.length})
                </span>
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

function EyeIcon() {
  return (
    <svg {...iconProps}>
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg {...iconProps}>
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}
