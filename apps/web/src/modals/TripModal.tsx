import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Device, OvernightSpot, Trip } from "../api";
import { Field, Modal } from "../components/Modal";
import { toLocalInput } from "../utils/time";

export type TripModalState =
  | null
  | { mode: "create"; from: string; to: string }
  | { mode: "edit"; trip: Trip };

type Props = {
  state: TripModalState;
  device: Device | null;
  overnightSpots: OvernightSpot[];
  onClose: () => void;
  onSubmit: (body: Omit<Trip, "id">, id?: string) => Promise<void> | void;
  onDelete?: (id: string) => Promise<void> | void;
};

export function TripModal({
  state,
  device,
  overnightSpots,
  onClose,
  onSubmit,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  // ongoing == true => no end date; trip is "open".
  const [ongoing, setOngoing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!state) return;
    setSubmitError(null);
    if (state.mode === "create") {
      setName("");
      setDescription("");
      setFrom(state.from);
      setTo(state.to);
      setOngoing(false);
    } else {
      setName(state.trip.name);
      setDescription(state.trip.description ?? "");
      setFrom(toLocalInput(new Date(state.trip.started_at)));
      setTo(
        state.trip.ended_at
          ? toLocalInput(new Date(state.trip.ended_at))
          : toLocalInput(new Date()),
      );
      setOngoing(state.trip.ended_at === null);
    }
  }, [state]);

  if (!state || !device) return null;
  const isEdit = state.mode === "edit";
  const id = isEdit ? state.trip.id : undefined;
  const deviceId = isEdit ? state.trip.device_id : device.id;

  const submit = async () => {
    if (!name.trim()) {
      setSubmitError(t("trips.errors.nameRequired"));
      return;
    }
    const fromDate = new Date(from);
    if (!from || isNaN(fromDate.getTime()) || fromDate.getFullYear() > 9999) {
      setSubmitError(t("trips.errors.invalidDate"));
      return;
    }
    const fromIso = fromDate.toISOString();
    let endedAt: string | null = null;
    if (!ongoing) {
      const toDate = new Date(to);
      if (!to || isNaN(toDate.getTime()) || toDate.getFullYear() > 9999) {
        setSubmitError(t("trips.errors.invalidToDate"));
        return;
      }
      const toIso = toDate.toISOString();
      if (toDate <= fromDate) {
        setSubmitError(t("trips.errors.toAfterFrom"));
        return;
      }
      endedAt = toIso;
    }
    // Warn if narrowing the window would remove spots that have media
    if (state && state.mode === "edit") {
      const origStart = new Date(state.trip.started_at);
      const origEnd = state.trip.ended_at
        ? new Date(state.trip.ended_at)
        : null;
      const newStart = new Date(fromIso);
      const newEnd = endedAt ? new Date(endedAt) : null;
      const isNarrower =
        newStart > origStart ||
        (origEnd === null && newEnd !== null) ||
        (origEnd !== null && newEnd !== null && newEnd < origEnd);
      if (isNarrower) {
        const spotsWithMediaOutside = overnightSpots.filter((s) => {
          if (!s.media || s.media.length === 0) return false;
          const stayAt = s.last_stay_at ? new Date(s.last_stay_at) : null;
          if (!stayAt) return false;
          return stayAt < newStart || (newEnd !== null && stayAt > newEnd);
        });
        if (spotsWithMediaOutside.length > 0) {
          const ok = window.confirm(
            t("trips.errors.narrowWindowMediaLoss", {
              count: spotsWithMediaOutside.length,
            }),
          );
          if (!ok) return;
        }
      }
    }
    setSaving(true);
    setSubmitError(null);
    try {
      await onSubmit(
        {
          device_id: deviceId,
          name: name.trim(),
          description: description.trim() || null,
          started_at: fromIso,
          ended_at: endedAt,
        },
        id,
      );
    } catch (e: unknown) {
      setSubmitError(
        e instanceof Error ? e.message : t("trips.errors.saveFailed"),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? t("trips.edit") : t("trips.new")}
      error={submitError}
      footer={
        <>
          {isEdit && onDelete && (
            <button
              className="ghost icon-btn-danger"
              style={{ marginRight: "auto" }}
              onClick={() => {
                if (
                  window.confirm(
                    t("trip.confirmDelete", { name: state.trip.name }),
                  )
                ) {
                  void onDelete(state.trip.id);
                  onClose();
                }
              }}
            >
              {t("common.delete")}
            </button>
          )}
          <button className="ghost" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button
            className="primary"
            onClick={submit}
            disabled={saving || !name.trim()}
          >
            {saving
              ? t("common.saving")
              : isEdit
                ? t("common.saveChanges")
                : t("trips.new")}
          </button>
        </>
      }
    >
      <Field label={t("trips.fields.name")}>
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("trips.fields.namePlaceholder")}
        />
      </Field>
      <Field label={t("trips.fields.description")}>
        <textarea
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("trips.fields.descriptionPlaceholder")}
        />
      </Field>
      <div style={{ marginBottom: "12px" }}>
        <span
          className="muted small"
          style={{ display: "block", marginBottom: "6px" }}
        >
          {t("dateRange.quickPresets")}:
        </span>
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          <button
            type="button"
            className="chip"
            onClick={() => {
              const start = new Date();
              start.setHours(0, 0, 0, 0);
              const end = new Date();
              end.setHours(23, 59, 59, 999);
              setFrom(toLocalInput(start));
              setTo(toLocalInput(end));
            }}
          >
            {t("dateRange.today") || "Today"}
          </button>
          <button
            type="button"
            className="chip"
            onClick={() => {
              const start = new Date();
              start.setDate(start.getDate() - 1);
              start.setHours(0, 0, 0, 0);
              const end = new Date();
              end.setDate(end.getDate() - 1);
              end.setHours(23, 59, 59, 999);
              setFrom(toLocalInput(start));
              setTo(toLocalInput(end));
            }}
          >
            {t("dateRange.yesterday") || "Yesterday"}
          </button>
          <button
            type="button"
            className="chip"
            onClick={() => {
              const now = new Date();
              const day = now.getDay();
              const subtract = (day + 2) % 7;
              const fri = new Date(now);
              fri.setDate(now.getDate() - subtract);
              fri.setHours(12, 0, 0, 0);
              const sun = new Date(fri);
              sun.setDate(fri.getDate() + 2);
              sun.setHours(23, 59, 59, 999);
              setFrom(toLocalInput(fri));
              setTo(toLocalInput(sun));
            }}
          >
            {t("dateRange.lastWeekend") || "Last Weekend"}
          </button>
          <button
            type="button"
            className="chip"
            onClick={() => {
              const start = new Date();
              start.setDate(start.getDate() - 7);
              setFrom(toLocalInput(start));
              setTo(toLocalInput(new Date()));
            }}
          >
            {t("dateRange.7d") || "Last 7 Days"}
          </button>
        </div>
      </div>
      <div className="row gap responsive-row">
        <Field label={t("trips.fields.from")}>
          <input
            type="datetime-local"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </Field>
        {!ongoing && (
          <Field label={t("trips.fields.to")}>
            <input
              type="datetime-local"
              value={to}
              onChange={(e) => setTo(e.target.value)}
            />
          </Field>
        )}
      </div>
      <label className="row gap small">
        <input
          type="checkbox"
          checked={ongoing}
          onChange={(e) => setOngoing(e.target.checked)}
        />
        <span>{t("trips.fields.ongoing")}</span>
      </label>
      <div className="muted small">
        {t("trips.fields.device", { name: device.name })}
      </div>
    </Modal>
  );
}
