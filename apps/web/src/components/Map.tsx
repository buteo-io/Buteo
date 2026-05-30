import { useEffect, useRef } from "react";
import maplibregl, { LngLatLike, Map as MLMap, Marker, Popup } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { api, OvernightSpot, Place, Position } from "../api";
import { tPlaceCategory, tPopupLabel } from "../i18n";

// NOTE: tiles come from openstreetmap.org. Two licensing constraints apply:
//   1. OSM data is under ODbL -- attribution `© OpenStreetMap contributors`
//      MUST remain visible to end users (we render it via a compact
//      AttributionControl below). Do not remove.
//   2. OSMF's tile usage policy disallows heavy production traffic on this
//      endpoint. Before going commercial / high-volume, switch to a proper
//      tile provider (MapTiler, Stadia, Protomaps, self-hosted, ...).
// MapLibre GL JS itself (BSD-3-Clause) does NOT require runtime attribution,
// so we omit it from the on-map credit.
const OSM_ATTRIBUTION =
  '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors';

const STYLE = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: OSM_ATTRIBUTION,
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
} as any;

export type DevicePopupInfo = {
  name: string;
  // Optional: hidden in public share view (M2 — IMEI is a credential).
  imei?: string;
  position: Position;
};

export type Overnight = { lon: number; lat: number; started_at: string; duration_s: number };

export type ColorMode = "none" | "speed" | "altitude" | "weekday";

type PlaceMarkerOptions = {
  readOnly?: boolean;
};

export type MapHandle = {
  setDevice: (info: DevicePopupInfo | null) => void;
  setHistory: (positions: Position[]) => void;
  clearHistory: () => void;
  // Switch how the history track is colored. The cached positions re-render
  // in place so toggling does not require re-fetching from the server.
  setColorMode: (mode: ColorMode) => void;
  setPlaces: (places: Place[], options?: PlaceMarkerOptions) => void;
  setOvernights: (stops: Overnight[]) => void;
  setOvernightSpots: (spots: OvernightSpot[], options?: PlaceMarkerOptions) => void;
  setGeofence: (lon: number | null, lat: number | null, radius_m: number | null) => void;
  flyTo: (lon: number, lat: number, zoom?: number) => void;
  fitTo: (coords: [number, number][]) => void;
  openDevicePopup: () => void;
  setSelectedMarker: (type: "place" | "overnight-spot" | null, id: string | null) => void;
  // events
  onMapClick: (cb: ((lon: number, lat: number) => void) | null) => void;
  onHistoryClick: (cb: HistoryClickCb | null) => void;
  onPlaceAction: (cb: PlaceActionCb | null) => void;
  onOvernightAction: (cb: OvernightActionCb | null) => void;
  onMapMove: (cb: (() => void) | null) => void;
  project: (lon: number, lat: number) => { x: number; y: number };
  getMap: () => MLMap | null;
};

type Cb = ((lon: number, lat: number) => void) | null;
type HistoryClickCb = (position: Position | null) => void;
type PlaceActionCb = ((action: "edit" | "delete" | "view", place: Place | null) => void) | null;
type OvernightActionCb = ((action: "edit" | "view", spot: OvernightSpot | null) => void) | null;

const NEUTRAL_TRACK_COLOR = "#1d4ed8";

function speedToColor(kmh: number | null | undefined): string {
  const v = kmh ?? 0;
  if (v <= 0) return "#1e3a8a";
  if (v < 30) return "#1d4ed8";
  if (v < 60) return "#0891b2";
  if (v < 90) return "#16a34a";
  if (v < 120) return "#ca8a04";
  return "#dc2626";
}

function altitudeToColor(meters: number | null | undefined): string {
  if (meters == null) return NEUTRAL_TRACK_COLOR;
  if (meters < 100) return "#0284c7";
  if (meters < 300) return "#16a34a";
  if (meters < 700) return "#ca8a04";
  if (meters < 1200) return "#ea580c";
  if (meters < 1800) return "#dc2626";
  return "#78716c";
}

const WEEKDAY_COLORS = [
  "#e63946", // Mon - crimson
  "#457b9d", // Tue - steel blue
  "#2a9d8f", // Wed - teal
  "#e9c46a", // Thu - sand/gold
  "#9b5de5", // Fri - purple
  "#d62828", // Sat - deep red
  "#1d3557", // Sun - navy
];

function weekdayToColor(timeId: string): string {
  const d = new Date(timeId);
  return WEEKDAY_COLORS[d.getUTCDay()];
}

export function useTrackMap(
  container: React.RefObject<HTMLDivElement>,
  mediaUrlFn?: (mediaId: string) => string,
): React.MutableRefObject<MapHandle | null> {
  const handleRef = useRef<MapHandle | null>(null);
  const mapRef = useRef<MLMap | null>(null);
  const deviceMarkerRef = useRef<Marker | null>(null);
  const devicePopupRef = useRef<Popup | null>(null);
  const placeMarkersRef = useRef<Marker[]>([]);
  const overnightMarkersRef = useRef<Marker[]>([]);
  const overnightSpotMarkersRef = useRef<Marker[]>([]);
  const clickCbRef = useRef<Cb>(null);
  const histClickCbRef = useRef<HistoryClickCb | null>(null);
  const placeActionCbRef = useRef<PlaceActionCb | null>(null);
  const overnightActionCbRef = useRef<OvernightActionCb | null>(null);
  const moveCbRef = useRef<(() => void) | null>(null);
  const positionsRef = useRef<Position[]>([]);
  const colorModeRef = useRef<ColorMode>("none");
  const mediaUrlFnRef = useRef(mediaUrlFn);
  const selectedMarkerTypeRef = useRef<"place" | "overnight-spot" | null>(null);
  const selectedMarkerIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: STYLE,
      center: [13.405, 52.52],
      zoom: 5,
      // Suppress the default attribution so we can control its content (drop
      // the MapLibre credit, keep only the OSM line that the data license
      // requires).
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl(), "bottom-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
    map.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution: OSM_ATTRIBUTION,
      }),
      "bottom-right",
    );
    mapRef.current = map;

    let loaded = false;
    const pending: Array<() => void> = [];
    const whenReady = (fn: () => void) => {
      if (loaded) fn();
      else pending.push(fn);
    };

    const ensureLayers = () => {
      if (!map.getSource("track")) {
        map.addSource("track", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "track-line",
          type: "line",
          source: "track",
          paint: {
            "line-color": ["coalesce", ["get", "color"], "#1d4ed8"],
            "line-width": 2,
            "line-opacity": 0.95,
          },
        });
      }
      if (!map.getSource("track-dots")) {
        map.addSource("track-dots", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "track-dots",
          type: "circle",
          source: "track-dots",
          paint: {
            "circle-radius": 2,
            "circle-color": ["coalesce", ["get", "color"], "#1d4ed8"],
            "circle-opacity": 0.8,
            "circle-stroke-width": 1,
            "circle-stroke-color": ["coalesce", ["get", "color"], "#1d4ed8"],
            "circle-stroke-opacity": 0.9,
          },
        });
      }
      if (!map.getSource("geofence")) {
        map.addSource("geofence", {
          type: "geojson",
          data: { type: "FeatureCollection", features: [] },
        });
        map.addLayer({
          id: "geofence-fill",
          type: "fill",
          source: "geofence",
          paint: { "fill-color": "#ef4444", "fill-opacity": 0.08 },
        });
        map.addLayer({
          id: "geofence-line",
          type: "line",
          source: "geofence",
          paint: { "line-color": "#ef4444", "line-width": 2, "line-dasharray": [2, 2] },
        });
      }
    };

    map.on("load", () => {
      ensureLayers();
      loaded = true;
      while (pending.length) {
        const fn = pending.shift();
        try { fn?.(); } catch (e) { console.error(e); }
      }
    });

    map.on("click", (e) => {
      const clickTarget = e.originalEvent.target;
      if (clickTarget instanceof Element && (clickTarget.closest(".overnight-spot-marker") || clickTarget.closest(".place-marker"))) {
        return;
      }

      // Clear marker selection
      setSelectedMarker(null, null);
      placeActionCbRef.current?.("view", null);
      overnightActionCbRef.current?.("view", null);

      // pick-place mode wins
      if (clickCbRef.current) {
        clickCbRef.current(e.lngLat.lng, e.lngLat.lat);
        return;
      }
      // history mode: pin if hitting the track, dismiss if missing
      const cb = histClickCbRef.current;
      if (!cb) return;
      const pts = positionsRef.current;
      // Expand hit box for touch — 20px covers a fat finger
      const hitBox: [maplibregl.PointLike, maplibregl.PointLike] = [
        [e.point.x - 20, e.point.y - 20],
        [e.point.x + 20, e.point.y + 20],
      ];
      // Only dots are clickable — exact index, no segment math
      const dotHits = map.queryRenderedFeatures(hitBox, { layers: ["track-dots"] });
      if (dotHits.length > 0) {
        const idx = dotHits[0].properties?.idx;
        if (idx != null && pts[idx]) { cb(pts[idx]); return; }
      }
      cb(null);
    });

    const setHistory = (positions: Position[]) => {
      whenReady(() => doSetHistory(positions));
    };
    const setColorMode = (mode: ColorMode) => {
      colorModeRef.current = mode;
      whenReady(() => doSetHistory(positionsRef.current));
    };
    const doSetHistory = (positions: Position[]) => {
      ensureLayers();
      positionsRef.current = positions;
      // Bucket consecutive same-color segments into one LineString each.
      // Shipping ~26K one-segment Features triggers MapLibre's per-feature
      // tile simplification to drop every segment at low zoom (tracks vanish).
      // Long polylines survive simplification and also render much faster.
      // In 'none' mode every segment shares the same neutral color so the
      // whole track collapses into a single feature -- ideal for perf and
      // for the simplifier.
      const features: any[] = [];
      const colorOf = (p: Position) => {
        switch (colorModeRef.current) {
          case "speed":
            return speedToColor(p.speed);
          case "altitude":
            return altitudeToColor(p.altitude);
          case "weekday":
            return weekdayToColor(p.time_id);
          default:
            return NEUTRAL_TRACK_COLOR;
        }
      };
      if (positions.length >= 2) {
        let curColor = colorOf(positions[1]);
        let coords: [number, number][] = [
          [positions[0].lon, positions[0].lat],
          [positions[1].lon, positions[1].lat],
        ];
        const flush = () => {
          if (coords.length >= 2) {
            features.push({
              type: "Feature",
              geometry: { type: "LineString", coordinates: coords },
              properties: { color: curColor },
            });
          }
        };
        for (let i = 2; i < positions.length; i++) {
          const c = colorOf(positions[i]);
          const pt: [number, number] = [positions[i].lon, positions[i].lat];
          if (c === curColor) {
            coords.push(pt);
          } else {
            flush();
            // start the next run anchored on the previous point so segments
            // visually connect across color changes (no gap on transitions).
            const last = coords[coords.length - 1];
            curColor = c;
            coords = [last, pt];
          }
        }
        flush();
      }
      const src = map.getSource("track") as any;
      if (src) src.setData({ type: "FeatureCollection", features });

      // Render position dots
      const dotFeatures: any[] = positions.map((p, idx) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [p.lon, p.lat] },
        properties: { color: colorOf(p), idx },
      }));
      const dotSrc = map.getSource("track-dots") as any;
      if (dotSrc) dotSrc.setData({ type: "FeatureCollection", features: dotFeatures });
    };

    // cursor hint when hovering a dot
    map.on("mouseenter", "track-dots", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "track-dots", () => {
      map.getCanvas().style.cursor = "";
    });

    // re-position click-tip when map moves/zooms
    map.on("move", () => moveCbRef.current?.());

    const clearMarkers = (arr: Marker[]) => {
      for (const m of arr) m.remove();
      arr.length = 0;
    };

    const buildPopupHtml = (info: DevicePopupInfo): string => {
      const { name, position: p } = info;
      const time = new Date(p.time_id).toLocaleString();
      const speed = p.speed != null ? `${p.speed.toFixed(1)} km/h` : "—";
      const alt = p.altitude != null ? `${Math.round(p.altitude)} m` : "—";
      const satellites = p.satellites != null ? p.satellites : "—";
      return `
        <div class="popup">
          <div class="popup-title">${escapeHtml(name)}</div>
          <table class="popup-table">
            <tr><th>${tPopupLabel("time")}</th><td>${escapeHtml(time)}</td></tr>
            <tr><th>${tPopupLabel("speed")}</th><td>${speed}</td></tr>
            <tr><th>${tPopupLabel("altitude")}</th><td>${alt}</td></tr>
            <tr><th>${tPopupLabel("satellites")}</th><td>${satellites}</td></tr>
          </table>
        </div>
      `;
    };

    const setDevice = (info: DevicePopupInfo | null) => {
      if (!info) {
        deviceMarkerRef.current?.remove();
        deviceMarkerRef.current = null;
        devicePopupRef.current?.remove();
        devicePopupRef.current = null;
        return;
      }
      const lngLat: LngLatLike = [info.position.lon, info.position.lat];
      const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000);
      const positionTime = new Date(info.position.time_id);
      const isStale = positionTime < twoHoursAgo;
      if (!devicePopupRef.current) {
        devicePopupRef.current = new maplibregl.Popup({
          offset: 24,
          maxWidth: "400px",
          className: "device-popup",
        });
      }
      devicePopupRef.current.setHTML(buildPopupHtml(info));
      if (!deviceMarkerRef.current) {
        const el = document.createElement("div");
        el.className = `device-marker${isStale ? " stale" : ""}`;
        el.setAttribute("aria-label", info.name);
        deviceMarkerRef.current = new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat(lngLat)
          .setPopup(devicePopupRef.current)
          .addTo(map);
      } else {
        deviceMarkerRef.current.setLngLat(lngLat);
        const el = deviceMarkerRef.current.getElement();
        if (el) {
          el.className = `device-marker${isStale ? " stale" : ""}`;
        }
      }
    };

    const openDevicePopup = () => {
      if (!deviceMarkerRef.current) return;
      const lngLat = deviceMarkerRef.current.getLngLat();
      map.flyTo({ center: lngLat, zoom: 14, duration: 500 });
      if (!deviceMarkerRef.current.getPopup()?.isOpen()) {
        deviceMarkerRef.current.togglePopup();
      }
    };

    const buildMediaHtml = (media: any[], getMediaUrl: (id: string) => string): string => {
      if (media.length === 0) return "";
      return `
        <div class="popup-media">
          ${media.slice(0, 4).map((m, i) =>
            `<div class="popup-media-thumb${media.length > 4 && i === 3 ? ' more' : ''}" data-media-index="${i}">` +
            (m.media_type === "image"
              ? `<img src="${getMediaUrl(m.id)}" alt="" />`
              : m.media_type === "video"
                ? `<video src="${getMediaUrl(m.id)}"></video>`
                : `<div class="popup-media-audio"><span>🎵</span></div>`) +
            (media.length > 4 && i === 3 ? `<span>+${media.length - 4}</span>` : "") +
            `</div>`
          ).join("")}
        </div>
      `;
    };

    const setMediaClickHandlers = (root: HTMLElement, pl: Place | OvernightSpot, type: "place" | "overnight") => {
      root.querySelectorAll(".popup-media-thumb").forEach((thumb) => {
        thumb.addEventListener("click", (e) => {
          e.stopPropagation();
          if (type === "place") {
            placeActionCbRef.current?.("view", pl as Place);
          } else {
            overnightActionCbRef.current?.("view", pl as OvernightSpot);
          }
        });
      });
    };

    const buildPlacePopup = (pl: Place, readOnly = false): HTMLElement => {
      const root = document.createElement("div");
      root.className = "popup place-popup";
      const placeCategoryHtml = pl.place_category
        ? `<div class="popup-cat">${escapeHtml(tPlaceCategory(pl.place_category))}</div>`
        : "";
      const notesHtml = pl.notes
        ? `<div class="popup-notes">${escapeHtml(pl.notes)}</div>`
        : "";
      const getMediaUrl = (id: string) => mediaUrlFnRef.current ? mediaUrlFnRef.current(id) : api.serveMedia(id);
      const mediaHtml = buildMediaHtml(pl.media ?? [], getMediaUrl);
      root.innerHTML = `
        <div class="popup-title">${escapeHtml(pl.name)}</div>
        ${placeCategoryHtml}
        ${notesHtml}
        ${mediaHtml}
      `;
      setMediaClickHandlers(root, pl, "place");
      if (!readOnly) {
        const actions = document.createElement("div");
        actions.className = "popup-actions";
        const editBtn = document.createElement("button");
        editBtn.className = "primary small";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          placeActionCbRef.current?.("edit", pl);
        });
        const delBtn = document.createElement("button");
        delBtn.className = "danger small";
        delBtn.textContent = "Delete";
        delBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          placeActionCbRef.current?.("delete", pl);
        });
        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
        root.appendChild(actions);
      }
      return root;
    };

    const buildOvernightSpotPopup = (spot: OvernightSpot, readOnly = false): HTMLElement => {
      const root = document.createElement("div");
      root.className = "popup overnight-popup";
      const notesHtml = spot.notes
        ? `<div class="popup-notes">${escapeHtml(spot.notes)}</div>`
        : "";
      const getMediaUrl = (id: string) => mediaUrlFnRef.current ? mediaUrlFnRef.current(id) : api.serveMedia(id);
      const mediaHtml = buildMediaHtml(spot.media ?? [], getMediaUrl);
      root.innerHTML = `
        <div class="popup-title">${escapeHtml(spot.name)}</div>
        <div class="popup-cat">${spot.nights_count} night${spot.nights_count > 1 ? "s" : ""}</div>
        ${notesHtml}
        ${mediaHtml}
      `;
      setMediaClickHandlers(root, spot, "overnight");
      if (!readOnly) {
        const actions = document.createElement("div");
        actions.className = "popup-actions";
        const editBtn = document.createElement("button");
        editBtn.className = "primary small";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          overnightActionCbRef.current?.("edit", spot);
        });
        actions.appendChild(editBtn);
        root.appendChild(actions);
      }
      return root;
    };

    const placeTypeClass = (type: string | undefined): string => {
      switch (type) {
        case "POI": return "type-poi";
        case "Drinking Water": return "type-drinking-water";
        case "Camping": return "type-camping";
        case "Parking": return "type-parking";
        default: return "";
      }
    };

    const placeTypeIconSvg = (type: string | undefined): string => {
      switch (type) {
        case "POI":
          return `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2C8.134 2 5 5.134 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.866-3.134-7-7-7zm0 9.5a2.5 2.5 0 1 1 0-5 2.5 2.5 0 0 1 0 5z"/></svg>`;
        case "Drinking Water":
          return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a5 5 0 0 1 5 5c0 4-5 10-5 10S7 11 7 7a5 5 0 0 1 5-5z"/><path d="M6 17a4 4 0 0 0 4 4M18 17a4 4 0 0 1-4 4" stroke-dasharray="2 1"/><line x1="12" y1="21" x2="12" y2="23"/></svg>`;
        case "Camping":
          return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 21l9-16 9 16H3z"/><line x1="7.5" y1="21" x2="12" y2="13"/><line x1="16.5" y1="21" x2="12" y2="13"/></svg>`;
        case "Parking":
          return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M9 17V7h5a3 3 0 0 1 0 6H9"/></svg>`;
        default:
          return `<svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="12" r="6"/></svg>`;
      }
    };

    const setSelectedMarker = (type: "place" | "overnight-spot" | null, id: string | null) => {
      // No-op - we don't highlight selected markers on map anymore
    };

    const setPlaces = (places: Place[], options: PlaceMarkerOptions = {}) => {
      clearMarkers(placeMarkersRef.current);
      for (const pl of places) {
        const category = pl.place_category ?? undefined;
        const el = document.createElement("div");
        const typeClass = placeTypeClass(category);
        el.className = `place-marker${typeClass ? ` ${typeClass}` : ""}`;
        el.title = pl.name;
        el.innerHTML = placeTypeIconSvg(category);
        el.dataset.id = pl.id;
        el.dataset.type = "place";

        el.addEventListener("click", (e) => {
          e.stopPropagation();
          placeActionCbRef.current?.("view", pl);
        });

        const anchor = category === "POI" ? "bottom-left" : "center";
        const m = new maplibregl.Marker({ element: el, anchor })
          .setLngLat([pl.lon, pl.lat])
          .addTo(map);
        placeMarkersRef.current.push(m);
      }
    };

    const setOvernights = (stops: Overnight[]) => {
      clearMarkers(overnightMarkersRef.current);
      for (const s of stops) {
        const el = document.createElement("div");
        el.className = "overnight-marker";
        const hours = (s.duration_s / 3600).toFixed(1);
        const popup = new maplibregl.Popup({ offset: 18, maxWidth: "400px" }).setHTML(
          `<div class="popup">
            <div class="popup-title">Overnight stay</div>
            <div class="popup-cat">${new Date(s.started_at).toLocaleString()}</div>
            <div class="popup-notes">${hours} h</div>
          </div>`,
        );
        const m = new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat([s.lon, s.lat])
          .setPopup(popup)
          .addTo(map);
        overnightMarkersRef.current.push(m);
      }
    };

    const setOvernightSpots = (spots: OvernightSpot[], options: PlaceMarkerOptions = {}) => {
      clearMarkers(overnightSpotMarkersRef.current);
      for (const spot of spots) {
        const el = document.createElement("div");
        el.className = "overnight-spot-marker";
        el.dataset.id = spot.id;
        el.dataset.type = "overnight-spot";
        
        // Circle with moon icon
        const circle = document.createElement("div");
        circle.className = "marker-circle";
        circle.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
        
        // Night count badge inside circle so outer el needs no position:relative
        const badge = document.createElement("div");
        badge.className = "overnight-badge";
        badge.textContent = String(spot.nights_count);
        circle.appendChild(badge);
        
        el.appendChild(circle);

        el.addEventListener("click", (e) => {
          e.stopPropagation();
          overnightActionCbRef.current?.("view", spot);
        });
        
        const m = new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat([spot.lon, spot.lat])
          .addTo(map);
        overnightSpotMarkersRef.current.push(m);
      }
    };

    const setGeofence = (lon: number | null, lat: number | null, radius_m: number | null) => {
      whenReady(() => doSetGeofence(lon, lat, radius_m));
    };
    const doSetGeofence = (lon: number | null, lat: number | null, radius_m: number | null) => {
      ensureLayers();
      const src = map.getSource("geofence") as any;
      if (!src) return;
      if (lon == null || lat == null || !radius_m) {
        src.setData({ type: "FeatureCollection", features: [] });
        return;
      }
      // build a ~circular polygon
      const points: [number, number][] = [];
      const steps = 64;
      const R = 6371000;
      const latRad = (lat * Math.PI) / 180;
      for (let i = 0; i <= steps; i++) {
        const brng = (i / steps) * 2 * Math.PI;
        const dLat = (radius_m * Math.cos(brng)) / R;
        const dLon = (radius_m * Math.sin(brng)) / (R * Math.cos(latRad));
        points.push([lon + (dLon * 180) / Math.PI, lat + (dLat * 180) / Math.PI]);
      }
      src.setData({
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [points] },
        properties: {},
      });
    };

    handleRef.current = {
      setDevice,
      setHistory,
      clearHistory: () => {
        setHistory([]);
        const dotSrc = map.getSource("track-dots") as any;
        if (dotSrc) dotSrc.setData({ type: "FeatureCollection", features: [] });
      },
      setColorMode,
      setPlaces,
      setOvernights,
      setOvernightSpots,
      setGeofence,
      flyTo: (lon, lat, zoom = 13) => map.flyTo({ center: [lon, lat], zoom, duration: 700 }),
      fitTo: (coords) => {
        if (coords.length === 0) return;
        const b = new maplibregl.LngLatBounds(coords[0], coords[0]);
        for (const c of coords) b.extend(c);
        map.fitBounds(b, { padding: 80, duration: 600, maxZoom: 14 });
      },
      openDevicePopup,
      setSelectedMarker,
      onMapClick: (cb) => {
        clickCbRef.current = cb;
      },
      onHistoryClick: (cb) => {
        histClickCbRef.current = cb;
      },
      onPlaceAction: (cb) => {
        placeActionCbRef.current = cb;
      },
      onOvernightAction: (cb) => {
        overnightActionCbRef.current = cb;
      },
      onMapMove: (cb) => {
        moveCbRef.current = cb;
      },
      project: (lon, lat) => {
        const p = map.project([lon, lat]);
        return { x: p.x, y: p.y };
      },
      getMap: () => mapRef.current,
    };

    return () => {
      map.remove();
      mapRef.current = null;
      deviceMarkerRef.current = null;
      devicePopupRef.current = null;
      placeMarkersRef.current = [];
      overnightMarkersRef.current = [];
      overnightSpotMarkersRef.current = [];
      handleRef.current = null;
      clickCbRef.current = null;
    };
  }, [container]);

  return handleRef;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
