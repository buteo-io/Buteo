import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Device, Trip } from "../api";
import { Field, Modal } from "../components/Modal";
import { toLocalInput } from "../utils/time";

export type TripModalState =
  | null
  | { mode: "create"; from: string; to: string }
  | { mode: "edit"; trip: Trip };

type Props = {
  state: TripModalState;
  device: Device | null;
  onClose: () => void;
  onSubmit: (body: Omit<Trip, "id">, id?: string) => Promise<void> | void;
};

export function TripModal({ state, device, onClose, onSubmit }: Props) {
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
    if (!name.trim()) return;
    const fromIso = new Date(from).toISOString();
    let endedAt: string | null = null;
    if (!ongoing) {
      const toIso = new Date(to).toISOString();
      if (new Date(toIso) <= new Date(fromIso)) {
        alert(t("trips.errors.toAfterFrom"));
        return;
      }
      endedAt = toIso;
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
    } catch (e: any) {
      setSubmitError(e?.message || t("trips.errors.saveFailed"));
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
          <button className="ghost" onClick={onClose}>{t("common.cancel")}</button>
          <button className="primary" onClick={submit} disabled={saving || !name.trim()}>
            {saving ? t("common.saving") : isEdit ? t("common.saveChanges") : t("trips.new")}
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
        <span className="muted small" style={{ display: "block", marginBottom: "6px" }}>
          {t("dateRange.custom") ? "Quick Presets" : "Quick Presets"}:
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
          <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} />
        </Field>
        {!ongoing && (
          <Field label={t("trips.fields.to")}>
            <input type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} />
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
      <div className="muted small">{t("trips.fields.device", { name: device.name })}</div>
    </Modal>
  );
}
