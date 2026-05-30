import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useTrackMap(mapContainer, (id) => `/api/share/${token}/media/${id}`);
  const [data, setData] = useState<PublicShareData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [galleryMedia, setGalleryMedia] = useState<MediaItem[] | null>(null);
  const [detailsModal, setDetailsModal] = useState<EntityDetailsModalState>(null);
  const [passwordRequired, setPasswordRequired] = useState(false);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  const getMediaUrl = (mediaId: string) => `/api/share/${token}/media/${mediaId}`;

  const loadShareData = () => {
    fetch(`/api/share/${token}`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) {
          let errorDetail: string | null = null;
          try {
            const errorPayload = await response.json();
            if (typeof errorPayload?.detail === "string") {
              errorDetail = errorPayload.detail;
            }
          } catch {
            const rawText = await response.text();
            errorDetail = rawText || null;
          }

          if (response.status === 429) {
            throw new Error(t("share.errors.rateLimit"));
          }
          if (response.status === 401 && errorDetail === "PASSWORD_REQUIRED") {
            setPasswordRequired(true);
            return null;
          }

          if (response.status === 404) {
            throw new Error("This share link does not exist or is no longer active.");
          }
          throw new Error(errorDetail || response.statusText || "Could not load shared trip.");
        }
        return response.json();
      })
      .then((shareData: PublicShareData | null) => {
        if (shareData) {
          setData(shareData);
        }
        setLoading(false);
      })
      .catch((fetchError) => {
        setError(fetchError.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadShareData();
  }, [token]);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setVerifying(true);
    setVerifyError(null);
    try {
      const response = await fetch(`/api/share/${token}/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
        credentials: "include",
      });
      if (!response.ok) {
        if (response.status === 429) {
          throw new Error(t("share.errors.rateLimit"));
        }
        let errorDetail = "Incorrect password";
        try {
          const errorPayload = await response.json();
          if (errorPayload?.detail) {
            errorDetail = errorPayload.detail;
          }
        } catch {}
        throw new Error(errorDetail);
      }
      setPasswordRequired(false);
      setLoading(true);
      loadShareData();
    } catch (err: any) {
      setVerifyError(err.message);
    } finally {
      setVerifying(false);
    }
  };

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
              {data.ended_at ? new Date(data.ended_at).toLocaleDateString() : "Ongoing"}
              {data.places.length > 0 && ` • ${data.places.length} place${data.places.length > 1 ? "s" : ""}`}
              {data.overnight_spots.length > 0 && ` • ${data.overnight_spots.length} overnight spot${data.overnight_spots.length > 1 ? "s" : ""}`}
            </span>
          </div>
        </header>
      )}
      <div style={{ flex: 1, position: "relative" }}>
        <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />
        
        {loading && !passwordRequired && !error && (
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

        {error && !passwordRequired && (
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
            padding: "1.5rem"
          }}>
            <div className="card" style={{
              maxWidth: "400px",
              width: "100%",
              padding: "2.5rem 2rem",
              textAlign: "center",
              boxShadow: "0 8px 24px rgba(0, 0, 0, 0.2)",
              borderRadius: "12px",
              border: "1px solid var(--line)",
              background: "var(--bg-1)"
            }}>
              <div style={{ position: "relative", marginBottom: "1.5rem", display: "inline-block" }}>
                <img 
                  src="/buteo-eagle-logo-lg.svg" 
                  alt="TrackMy Buteo Logo" 
                  style={{ width: "80px", height: "80px" }} 
                />
                <span style={{
                  position: "absolute",
                  bottom: "-5px",
                  right: "-5px",
                  fontSize: "1.5rem",
                  background: "var(--bg-1)",
                  borderRadius: "50%",
                  padding: "2px",
                  boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "36px",
                  height: "36px",
                  lineHeight: "1"
                }}>
                  ⚠️
                </span>
              </div>
              <h2 style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.5rem 0 0.25rem 0" }}>
                Error Loading Trip
              </h2>
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0 }}>
                {error}
              </p>
            </div>
          </div>
        )}

        {passwordRequired && (
          <div style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            zIndex: 10000,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "var(--bg-0)",
            padding: "1.5rem"
          }}>
            <div className="card" style={{
              maxWidth: "400px",
              width: "100%",
              padding: "2.5rem 2rem",
              textAlign: "center",
              boxShadow: "0 8px 24px rgba(0, 0, 0, 0.2)",
              borderRadius: "12px",
              border: "1px solid var(--line)",
              background: "var(--bg-1)"
            }}>
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: "1.5rem" }}>
                <div style={{ position: "relative", marginBottom: "1rem" }}>
                  <img 
                    src="/buteo-eagle-logo-lg.svg" 
                    alt="TrackMy Buteo Logo" 
                    style={{ width: "80px", height: "80px" }} 
                  />
                  <span style={{
                    position: "absolute",
                    bottom: "-5px",
                    right: "-5px",
                    fontSize: "1.5rem",
                    background: "var(--bg-1)",
                    borderRadius: "50%",
                    padding: "2px",
                    boxShadow: "0 2px 6px rgba(0,0,0,0.15)",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: "36px",
                    height: "36px",
                    lineHeight: "1"
                  }}>
                    🔒
                  </span>
                </div>
                <h2 style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.5rem 0 0.25rem 0" }}>
                  Password Required
                </h2>
                <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0 }}>
                  This shared trip is password protected. Please enter the password to view it.
                </p>
              </div>

              <form onSubmit={handleVerify} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div className="field" style={{ textAlign: "left" }}>
                  <div className="password-input-wrapper">
                    <input
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Enter password"
                      required
                      autoFocus
                      style={{
                        width: "100%",
                        padding: "0.75rem",
                        paddingRight: "2.5rem",
                        fontSize: "1rem",
                        borderRadius: "4px",
                        border: "1px solid var(--line)",
                        background: "var(--bg-0)"
                      }}
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
                </div>
                
                {verifyError && (
                  <div style={{
                    color: "var(--bad)",
                    fontSize: "0.875rem",
                    textAlign: "left",
                    padding: "0.5rem",
                    borderRadius: "4px",
                    backgroundColor: "rgba(239, 68, 68, 0.1)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem"
                  }}>
                    <span>⚠️</span>{" "}<span>{verifyError}</span>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={verifying}
                  className="btn primary"
                  style={{
                    padding: "0.75rem",
                    fontSize: "1rem",
                    fontWeight: "bold",
                    borderRadius: "4px",
                    cursor: "pointer",
                    width: "100%"
                  }}
                >
                  {verifying ? "Verifying..." : "View Shared Trip"}
                </button>
              </form>
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

const iconProps = {
  viewBox: "0 0 24 24",
  width: 20,
  height: 20,
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

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
