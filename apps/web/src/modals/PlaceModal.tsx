import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { api, Place, PlaceMedia, Trip } from "../api";
import { Field } from "../components/Modal";
import { EntityModal } from "../components/EntityModal";
import { PlaceTypeIcon } from "../components/PlaceTypeIcon";

export type PlaceModalState =
  | null
  | { mode: "create"; lon: number; lat: number }
  | { mode: "edit"; place: Place };

type Props = {
  state: PlaceModalState;
  trips: Trip[];
  onClose: () => void;
  onSubmit: (body: Omit<Place, "id">, id?: string) => Promise<void> | void;
  onMediaClick?: (media: PlaceMedia[], initialIdx: number) => void;
  onMediaChange?: (placeId: string, media: PlaceMedia[]) => void;
};

const CATEGORIES = ["POI", "Drinking Water", "Camping", "Parking"] as const;

export function PlaceModal({ state, trips, onClose, onSubmit, onMediaClick, onMediaChange }: Props) {
  const { t } = useTranslation();
  const [chosenCategory, setChosenCategory] = useState<"POI" | "Drinking Water" | "Camping" | "Parking">("POI");
  const [chosenTrips, setChosenTrips] = useState<string[]>([]);

  useEffect(() => {
    if (state) {
      if (state.mode === "edit") {
        setChosenCategory(state.place.place_category);
        setChosenTrips(state.place.trip_ids);
      } else {
        setChosenCategory("POI");
        setChosenTrips([]);
      }
    }
  }, [state]);

  if (!state) return null;

  const handleEntitySubmit = async (data: { name: string; notes: string }) => {
    await onSubmit(
      {
        name: data.name,
        notes: data.notes || null,
        lon: state.mode === "create" ? state.lon : state.place.lon,
        lat: state.mode === "create" ? state.lat : state.place.lat,
        place_category: chosenCategory,
        trip_ids: chosenTrips,
      },
      state.mode === "edit" ? state.place.id : undefined
    );
  };

  const toggleTrip = (tid: string) => {
    setChosenTrips((current) =>
      current.includes(tid) ? current.filter((x) => x !== tid) : [...current, tid]
    );
  };

  const extraFields = (
    <>
      <Field label={t("places.fields.category")}>
        <div className="type-picker">
          {CATEGORIES.map((cat) => (
            <button
              type="button"
              key={cat}
              className={`type-chip ${chosenCategory === cat ? "active" : ""}`}
              onClick={() => {
                setChosenCategory(cat);
              }}
            >
              <PlaceTypeIcon type={cat} size={16} />
              {t(`places.categories.${cat}`)}
            </button>
          ))}
        </div>
      </Field>
      <Field label={t("places.fields.trips")} hint={t("places.fields.tripsHint")}>
        {trips.length === 0 ? (
          <div className="muted small">{t("trips.noTrips")}</div>
        ) : (
          <div className="tag-picker">
            {trips.map((tItem) => {
              const active = chosenTrips.includes(tItem.id);
              return (
                <button
                  type="button"
                  key={tItem.id}
                  className={`chip ${active ? "active" : ""}`}
                  onClick={() => toggleTrip(tItem.id)}
                  title={`${new Date(tItem.started_at).toLocaleDateString()} → ${
                    tItem.ended_at ? new Date(tItem.ended_at).toLocaleDateString() : t("common.now")
                  }`}
                >
                  {tItem.name}
                </button>
              );
            })}
          </div>
        )}
      </Field>
    </>
  );

  return (
    <EntityModal<Place, PlaceMedia>
      mode={state.mode}
      entityType="place"
      entity={state.mode === "edit" ? state.place : undefined}
      lat={state.mode === "create" ? state.lat : state.place.lat}
      lon={state.mode === "create" ? state.lon : state.place.lon}
      onClose={onClose}
      onSubmit={handleEntitySubmit}
      fetchMedia={api.placeMedia}
      uploadMedia={api.uploadPlaceMedia}
      deleteMedia={api.deletePlaceMedia}
      onMediaClick={onMediaClick}
      onMediaChange={(media) => {
        if (state.mode === "edit") {
          onMediaChange?.(state.place.id, media);
        }
      }}
      extraFields={extraFields}
      submitButtonText={state.mode === "create" ? t("places.create") : t("common.saveChanges")}
      savingButtonText={t("common.saving")}
    />
  );
}

