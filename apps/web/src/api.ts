// Cookie-based auth: backend sets an httpOnly Secure SameSite=Strict cookie
// at /auth/login. Browser auto-attaches it on subsequent requests via
// `credentials: 'include'`. We never read or store the token in JS.
//
// Resource IDs in the public API are UUID strings (public_id), not integers.

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  const r = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  if (!r.ok) throw new Error(await readError(r));
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

// Hard ceiling enforced by the backend on analytics + export endpoints
// (see backend/api/queries.py MAX_ANALYTICS_POINTS). Re-exported so panels
// can mention it in helper text without having to know the magic number.
export const MAX_ANALYTICS_POINTS = 200_000;

// FastAPI errors come in two shapes:
//   - HTTPException:  {"detail": "string"}
//   - Pydantic 422:   {"detail": [{loc, msg, type, ...}, ...]}
// Either way, we want a single human-readable line, not raw JSON.
async function readError(r: Response): Promise<string> {
  const text = await r.text();
  if (!text) return r.statusText || `HTTP ${r.status}`;
  try {
    const j = JSON.parse(text);
    const d = j?.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d.length > 0) {
      // Drop the "body."/"query." prefix from loc; keep just the field name.
      // Also strip Pydantic's "Value error, " prefix that wraps custom messages.
      return d
        .map((e: any) => {
          const field = Array.isArray(e?.loc) ? e.loc.slice(1).join(".") : "";
          const msg = String(e.msg || "").replace(/^Value error,\s*/i, "");
          return field ? `${field}: ${msg}` : msg;
        })
        .join("; ");
    }
  } catch {
    // not JSON — fall through to raw
  }
  return text;
}

export type Me = { id: string; email: string; features: string[] };
export type Device = {
  id: string;
  imei: string;
  name: string;
  last_seen_at?: string | null;
};
export type Entity = {
  id: string;
  type: string;
  name: string;
  avatar_icon?: string | null;
  metadata?: Record<string, any> | null;
  devices: Device[];
};
export type Position = {
  time_id: string;
  lon: number;
  lat: number;
  altitude: number | null;
  speed: number | null;
  satellites: number | null;
};

export type Place = {
  id: string;
  name: string;
  lon: number;
  lat: number;
  notes: string | null;
  place_category: "POI" | "Drinking Water" | "Camping" | "Parking";
  // public ids of trips this place is linked to (many-to-many)
  trip_ids: string[];
  // media attached to this place
  media?: PlaceMedia[];
};

export type PlaceMedia = {
  id: string;
  filename_original: string;
  media_type: "image" | "video";
  mime_type: string;
  size_bytes: number;
  created_at: string;
};

export type OvernightSpotMedia = {
  id: string;
  filename_original: string;
  media_type: "image" | "video";
  mime_type: string;
  size_bytes: number;
  created_at: string;
};

export type MediaItem = PlaceMedia | OvernightSpotMedia;

export type Overnight = {
  started_at: string;
  ended_at: string;
  lon: number;
  lat: number;
  duration_s: number;
};

export type OvernightSpot = {
  id: string;
  trip_id: string;
  name: string;
  notes: string | null;
  lon: number;
  lat: number;
  nights_count: number;
  last_stay_at?: string;
  created_at?: string;
  // media attached to this overnight spot
  media?: OvernightSpotMedia[];
};

export type OvernightSpotDetect = {
  status: string;
  created: number;
  updated: number;
  last_checked_position_time: string | null;
};

export type AutoTrip = {
  started_at: string;
  ended_at: string;
  distance_km: number;
  duration_s: number;
  max_speed_kmh: number;
  avg_speed_kmh: number;
  start_lon: number;
  start_lat: number;
  end_lon: number;
  end_lat: number;
  points: number;
};

export type Trip = {
  id: string;
  device_id: string;
  name: string;
  description: string | null;
  started_at: string;
  // null = ongoing trip (effective end is "now" until closed via /end)
  ended_at: string | null;
};

export type TripStats = {
  distance_km: number;
  duration_s: number;
  moving_s: number;
  max_speed_kmh: number;
  avg_speed_kmh: number;
  moving_avg_speed_kmh: number;
  overnights: number;
  points: number;
};

export type Summary = {
  trips: number;
  distance_km: number;
  duration_s: number;
  max_speed_kmh: number;
  avg_speed_kmh: number;
  overnights: number;
  points: number;
};

export type Mileage = {
  granularity: "day" | "month" | "year";
  total_km: number;
  buckets: { label: string; km: number }[];
};

export type CategoryEntry = {
  id: string;
  name: string;
};

export type ShareLink = {
  id: string;
  trip_id: string;
  name: string;
  description: string | null;
  share_started_at: string | null;
  share_ended_at: string | null;
  delay_hours: number;
  blur_meters: number;
  is_active: boolean;
  has_password?: boolean;
  place_ids: string[];
  overnight_spot_ids: string[];
  created_at: string;
  updated_at: string;
};

export type ShareLinkSecret = ShareLink & {
  token: string;
};

function qs(params: Record<string, string | number | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export const api = {
  login: (email: string, password: string) =>
    http<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  logout: () => http<void>("/auth/logout", { method: "POST" }),
  me: () => http<Me>("/me"),
  devices: () => http<Device[]>("/devices"),
  entities: () => http<Entity[]>("/entities"),
  latest: (id: string) =>
    http<Position | null>(`/devices/${id}/positions/latest`),
  history: (id: string, from?: string, to?: string, limit = 50000) =>
    http<Position[]>(`/devices/${id}/positions${qs({ from, to, limit })}`),
  autoTrips: (id: string, from?: string, to?: string) =>
    http<AutoTrip[]>(`/devices/${id}/trips${qs({ from, to })}`),
  overnights: (id: string, from?: string, to?: string) =>
    http<Overnight[]>(`/devices/${id}/overnights${qs({ from, to })}`),
  summary: (id: string, from?: string, to?: string) =>
    http<Summary>(`/devices/${id}/summary${qs({ from, to })}`),
  mileage: (
    id: string,
    granularity: "day" | "month" | "year",
    from?: string,
    to?: string,
  ) => http<Mileage>(`/devices/${id}/mileage${qs({ granularity, from, to })}`),
  download: async (
    id: string,
    fmt: "gpx" | "csv",
    from?: string,
    to?: string,
  ) => {
    const r = await fetch(
      `/api/devices/${id}/export.${fmt}${qs({ from, to })}`,
      {
        credentials: "include",
      },
    );
    if (!r.ok) throw new Error(await readError(r));
    return await r.blob();
  },

  trips: () => http<Trip[]>("/trips"),
  createTrip: (body: Omit<Trip, "id">) =>
    http<Trip>("/trips", { method: "POST", body: JSON.stringify(body) }),
  updateTrip: (id: string, body: Omit<Trip, "id">) =>
    http<Trip>(`/trips/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteTrip: (id: string) => http<void>(`/trips/${id}`, { method: "DELETE" }),
  endTrip: (id: string, ended_at?: string) =>
    http<Trip>(`/trips/${id}/end`, {
      method: "POST",
      body: JSON.stringify(ended_at ? { ended_at } : {}),
    }),
  tripStats: (id: string) => http<TripStats>(`/trips/${id}/stats`),
  tripPositions: (id: string) => http<Position[]>(`/trips/${id}/positions`),
  tripPlaces: (id: string) => http<Place[]>(`/trips/${id}/places`),
  tripOvernightSpots: (id: string) =>
    http<OvernightSpot[]>(`/trips/${id}/overnight-spots`),
  detectTripOvernightSpots: (id: string) =>
    http<OvernightSpotDetect>(`/trips/${id}/overnight-spots/detect`, {
      method: "POST",
    }),
  exportTripGpx: async (tripId: string, includeMetadata: boolean) => {
    const r = await fetch(
      `/api/trips/${tripId}/export.gpx${qs({ include_metadata: includeMetadata ? "true" : "false" })}`,
      {
        credentials: "include",
      },
    );
    if (!r.ok) throw new Error(await readError(r));
    return await r.blob();
  },

  places: () => http<Place[]>("/places"),
  createPlace: (body: Omit<Place, "id">) =>
    http<Place>("/places", { method: "POST", body: JSON.stringify(body) }),
  updatePlace: (id: string, body: Omit<Place, "id">) =>
    http<Place>(`/places/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deletePlace: (id: string) =>
    http<void>(`/places/${id}`, { method: "DELETE" }),

  placeMedia: (placeId: string) =>
    http<PlaceMedia[]>(`/places/${placeId}/media`),
  uploadPlaceMedia: async (
    placeId: string,
    file: File,
  ): Promise<PlaceMedia> => {
    const formData = new FormData();
    formData.append("file", file);
    const r = await fetch(`/api/places/${placeId}/media`, {
      method: "POST",
      body: formData,
      credentials: "include",
    });
    if (!r.ok) throw new Error(await readError(r));
    return r.json();
  },
  deletePlaceMedia: (placeId: string, mediaId: string) =>
    http<void>(`/places/${placeId}/media/${mediaId}`, { method: "DELETE" }),
  serveMedia: (mediaId: string) => `/api/media/${mediaId}/serve`,

  updateOvernightSpot: (
    id: string,
    body: { name: string; notes: string | null },
  ) =>
    http<OvernightSpot>(`/overnight-spots/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  overnightSpotMedia: (spotId: string) =>
    http<OvernightSpotMedia[]>(`/overnight-spots/${spotId}/media`),
  uploadOvernightSpotMedia: async (
    spotId: string,
    file: File,
  ): Promise<OvernightSpotMedia> => {
    const formData = new FormData();
    formData.append("file", file);
    const r = await fetch(`/api/overnight-spots/${spotId}/media`, {
      method: "POST",
      body: formData,
      credentials: "include",
    });
    if (!r.ok) throw new Error(await readError(r));
    return r.json();
  },
  deleteOvernightSpotMedia: (spotId: string, mediaId: string) =>
    http<void>(`/overnight-spots/${spotId}/media/${mediaId}`, {
      method: "DELETE",
    }),

  shareLinks: () => http<ShareLink[]>("/share-links"),
  createShareLink: (
    body: Omit<ShareLink, "id" | "created_at" | "updated_at">,
  ) =>
    http<ShareLinkSecret>("/share-links", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateShareLink: (
    id: string,
    body: Partial<Omit<ShareLink, "id" | "created_at" | "updated_at">>,
  ) =>
    http<ShareLink>(`/share-links/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  rotateShareLink: (id: string) =>
    http<ShareLinkSecret>(`/share-links/${id}/rotate`, { method: "POST" }),
  revokeShareLink: (id: string) =>
    http<void>(`/share-links/${id}/revoke`, { method: "POST" }),
  deleteShareLink: (id: string) =>
    http<void>(`/share-links/${id}`, { method: "DELETE" }),
};
