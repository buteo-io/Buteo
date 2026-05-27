import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trip } from "../api";
import { Select } from "../components/Select";

type Props = {
  trips: Trip[];
  onExport: (tripId: string, includeMetadata: boolean) => Promise<void>;
};

export function ExportPanel({ trips, onExport }: Props) {
  const { t } = useTranslation();
  const [tripId, setTripId] = useState(trips[0]?.id || "");
  const [includeMetadata, setIncludeMetadata] = useState(true);
  const [exporting, setExporting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!tripId) return;
    setExporting(true);
    try {
      await onExport(tripId, includeMetadata);
    } finally {
      setExporting(false);
    }
  };

  if (trips.length === 0) {
    return (
      <div className="share-panel">
        <div className="empty">{t("export.noTrips")}</div>
      </div>
    );
  }

  return (
    <div className="share-panel">
      <form onSubmit={handleSubmit} className="share-form">
        <p className="muted small" style={{ marginBottom: "1.5rem" }}>
          {t("export.exportHistorical")}
        </p>

        <div className="field">
          <label className="field-label">
            {t("export.selectTrip")} <span style={{ color: "var(--bad)" }}>*</span>
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
              checked={includeMetadata}
              onChange={(e) => setIncludeMetadata(e.target.checked)}
            />
            <span>{t("export.includeMetadata")}</span>
          </label>
          <p className="field-hint" style={{ marginTop: "0.5rem" }}>
            {t("export.includeMetadataHint")}
          </p>
        </div>

        <div className="share-form-actions" style={{ marginTop: "2rem" }}>
          <button type="submit" className="primary" disabled={exporting}>
            {exporting ? t("common.saving") : t("export.exportButton")}
          </button>
        </div>
      </form>
    </div>
  );
}
