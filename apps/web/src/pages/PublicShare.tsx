import { useEffect, useRef, useState } from "react";
import { Place, MediaItem } from "../api";
import { useTrackMap } from "../components/Map";
import { GalleryModal } from "../modals/GalleryModal";
import { EntityDetailsModal, EntityDetailsModalState } from "../modals/EntityDetailsModal";

type PublicShareMedia = {
  id: string;
  media_type: string;
  mime_type: string;
};

type PublicSharePlace = {
  id: string;
  name: string;
  notes: string | null;
  lon: number;
  lat: number;
  place_category: string | null;
  media: PublicShareMedia[];
};

type PublicShareOvernightSpot = {
  id: string;
  name: string;
  notes: string | null;
  lon: number;
  lat: number;
  nights_count: number;
  media: PublicShareMedia[];
};

type PublicShareData = {
  trip_name: string;
  trip_description: string | null;
  started_at: string;
  ended_at: string | null;
  blur_meters: number;
  positions: Array<{ time_id: string; lon: number; lat: number }>;
  places: PublicSharePlace[];
  overnight_spots: PublicShareOvernightSpot[];
};

type Props = {
  token: string;
};

export default function PublicShare({ token }: Props) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useTrackMap(mapContainer, (id) => `/api/share/${token}/media/${id}`);
  const [data, setData] = useState<PublicShareData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [galleryMedia, setGalleryMedia] = useState<MediaItem[] | null>(null);
  const [detailsModal, setDetailsModal] = useState<EntityDetailsModalState>(null);

  const getMediaUrl = (mediaId: string) => `/api/share/${token}/media/${mediaId}`;

  useEffect(() => {
    fetch(`/api/share/${token}`, { credentials: "omit" })
      .then(async (r) => {
        if (!r.ok) {
          let detail: string | null = null;
          try {
            const payload = await r.json();
            if (typeof payload?.detail === "string") detail = payload.detail;
          } catch {
            const text = await r.text();
            detail = text || null;
          }

          if (r.status === 404) {
            throw new Error("This share link does not exist or is no longer active.");
          }
          throw new Error(detail || r.statusText || "Could not load shared trip.");
        }
        return r.json();
      })
      .then((d: PublicShareData) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(e.message);
        setLoading(false);
      });
  }, [token]);

  useEffect(() => {
    if (!data || !map.current) return;

    const positions = data.positions.map((p) => ({
      time_id: p.time_id,
      lon: p.lon,
      lat: p.lat,
      altitude: null,
      speed: null,
      satellites: null,
    }));

    map.current.setHistory(positions);

    if (positions.length > 0) {
      const coords: [number, number][] = positions.map((p) => [p.lon, p.lat]);
      map.current.fitTo(coords);
    }
  }, [data, map]);

  const allPlaces =
    data?.places.map<Place>((place) => ({
      id: place.id,
      name: place.name,
      notes: place.notes,
      lon: place.lon,
      lat: place.lat,
      place_category: place.place_category as Place["place_category"],
      place_category_id: null,
      trip_ids: [],
      media: place.media.map((m) => ({
        id: m.id,
        filename_original: "",
        media_type: m.media_type as "image" | "video",
        mime_type: m.mime_type,
        size_bytes: 0,
        created_at: "",
      })),
    })) ?? [];

  useEffect(() => {
    if (!map.current) return;
    map.current.setPlaces(allPlaces, { readOnly: true });
  }, [map, allPlaces]);

  const allOvernightSpots =
    data?.overnight_spots.map<import("../api").OvernightSpot>((spot) => ({
      id: spot.id,
      trip_id: "", // not needed for public share
      name: spot.name,
      notes: spot.notes,
      lon: spot.lon,
      lat: spot.lat,
      nights_count: spot.nights_count,
      media: spot.media.map((m) => ({
        id: m.id,
        filename_original: "",
        media_type: m.media_type as "image" | "video",
        mime_type: m.mime_type,
        size_bytes: 0,
        created_at: "",
      })),
    })) ?? [];

  useEffect(() => {
    if (!map.current) return;
    map.current.setOvernightSpots(allOvernightSpots, { readOnly: true });
  }, [map, allOvernightSpots]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    m.onPlaceAction((action, place) => {
      if (action === "view") {
        if (!place) {
          setDetailsModal(null);
        } else {
          setDetailsModal({ type: "place", place });
        }
      }
    });
    m.onOvernightAction((action, spot) => {
      if (action === "view") {
        if (!spot) {
          setDetailsModal(null);
        } else {
          setDetailsModal({ type: "overnight-spot", spot });
        }
      }
    });
    return () => {
      m.onPlaceAction(null);
      m.onOvernightAction(null);
    };
  }, [map]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {data && (
        <header
          style={{
            padding: "1rem 1.5rem",
            borderBottom: "1px solid var(--line)",
            background: "var(--bg-1)",
          }}
        >
          <h1 style={{ margin: 0, fontSize: "1.25rem", fontWeight: 600 }}>{data.trip_name}</h1>
          {data.trip_description && (
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.875rem", color: "var(--text-muted)" }}>
              {data.trip_description}
            </p>
          )}
          <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: "1rem" }}>
            <span>
              {new Date(data.started_at).toLocaleDateString()} -{" "}
              {data.ended_at ? new Date(data.ended_at).toLocaleDateString() : "Ongoing"} •{" "}
              {data.positions.length} points
              {data.places.length > 0 && ` • ${data.places.length} place${data.places.length > 1 ? "s" : ""}`}
              {data.overnight_spots.length > 0 && ` • ${data.overnight_spots.length} overnight spot${data.overnight_spots.length > 1 ? "s" : ""}`}
            </span>
          </div>
        </header>
      )}
      <div style={{ flex: 1, position: "relative" }}>
        <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />
        
        {loading && (
          <div style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--bg-0)",
            zIndex: 1000,
          }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: "2rem", marginBottom: "1rem" }}>🗺️</div>
              <div>Loading shared trip...</div>
            </div>
          </div>
        )}

        {galleryMedia && (
          <GalleryModal
            media={galleryMedia}
            getMediaUrl={getMediaUrl}
            onClose={() => setGalleryMedia(null)}
          />
        )}

        <EntityDetailsModal
          state={detailsModal}
          trips={data ? [{
            id: "",
            name: data.trip_name,
            description: data.trip_description,
            started_at: data.started_at,
            ended_at: data.ended_at,
            device_id: "",
          }] : []}
          onClose={() => setDetailsModal(null)}
          onMediaClick={(media, i) => {
            setGalleryMedia(media);
          }}
        />
      </div>
    </div>
  );
}
