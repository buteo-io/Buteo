import { useTranslation } from "react-i18next";
import { api, OvernightSpot, OvernightSpotMedia } from "../api";
import { EntityModal } from "../components/EntityModal";

export type OvernightSpotModalState = null | { spot: OvernightSpot };

type Props = {
  state: OvernightSpotModalState;
  onClose: () => void;
  onSubmit: (body: { name: string; notes: string | null }, id: string) => Promise<void> | void;
  onMediaClick?: (media: OvernightSpotMedia[], initialIdx: number) => void;
  onMediaChange?: (spotId: string, media: OvernightSpotMedia[]) => void;
};

export function OvernightSpotModal({ state, onClose, onSubmit, onMediaClick, onMediaChange }: Props) {
  const { t } = useTranslation();
  if (!state) return null;

  const handleEntitySubmit = async (data: { name: string; notes: string }) => {
    await onSubmit(
      { name: data.name, notes: data.notes || null },
      state.spot.id
    );
  };

  const extraFields = (
    <div className="popup-cat" style={{ marginTop: "-8px", marginBottom: "16px", fontSize: "12px", opacity: 0.7 }}>
      {t("overnightSpot.nights", { count: state.spot.nights_count })}
    </div>
  );

  return (
    <EntityModal<OvernightSpot, OvernightSpotMedia>
      mode="edit"
      entityType="overnight-spot"
      entity={state.spot}
      lat={state.spot.lat}
      lon={state.spot.lon}
      onClose={onClose}
      onSubmit={handleEntitySubmit}
      fetchMedia={api.overnightSpotMedia}
      uploadMedia={api.uploadOvernightSpotMedia}
      deleteMedia={api.deleteOvernightSpotMedia}
      onMediaClick={onMediaClick}
      onMediaChange={(media) => {
        onMediaChange?.(state.spot.id, media);
      }}
      extraFields={extraFields}
      submitButtonText={t("common.saveChanges")}
      savingButtonText={t("common.saving")}
    />
  );
}

