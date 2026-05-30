// Top-level orchestrator. Owns global app state and wires children together.
// All UI lives in components/ and panels/.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  api,
  Device,
  Place,
  CategoryEntry,
  Position,
  ShareLink,
  Trip,
  TripStats,
  OvernightSpot,
  MAX_ANALYTICS_POINTS,
} from "./api";
import { useAuth } from "./auth";
import { useTheme } from "./hooks/useTheme";
import { ColorMode } from "./components/Map";
import { useDateRange } from "./contexts/DateRangeContext";
import { useEntity } from "./contexts/EntityContext";
import { useMapState } from "./contexts/MapStateContext";
import { Sidebar, Tab } from "./components/Sidebar";
import { pluginRegistry } from "./plugins/registry";
import { PinnedTip } from "./components/PinnedTip";
import { useLivePoll } from "./hooks/useLivePoll";
import { DetailsModal } from "./modals/DetailsModal";
import { GalleryModal } from "./modals/GalleryModal";
import { OvernightSpotModal, OvernightSpotModalState } from "./modals/OvernightSpotModal";
import { PlaceModal, PlaceModalState } from "./modals/PlaceModal";
import { TripModal, TripModalState } from "./modals/TripModal";
import { EntityDetailsModal, EntityDetailsModalState } from "./modals/EntityDetailsModal";
import { Modal } from "./components/Modal";
import { MapGearIcon } from "./components/MapGearIcon";
import { DevicesPanel } from "./panels/DevicesPanel";
import { ExportPanel } from "./panels/ExportPanel";
import { PlacesPanel } from "./panels/PlacesPanel";
import { SettingsPanel } from "./panels/SettingsPanel";
import { SharePanel } from "./panels/SharePanel";
import { TripsPanel } from "./panels/TripsPanel";
import { defaultRange, getRangePresets, Range, toIsoZ, toLocalInput } from "./utils/time";


type Mode = "live" | "history";

export default function App() {
  useTheme(); // Initialize global theme
  const { t } = useTranslation();
  const { me, logout } = useAuth();
  const { range, setRange, fromIso, toIso } = useDateRange();
  const { entities, devices, device, setDevice, activeEntity, refreshEntities } = useEntity();
  const {
    mapContainerRef,
    map,
    mode,
    setMode,
    colorMode,
    setColorMode,
    hiddenCategories,
    setHiddenCategories,
    hideUncategorized,
    setHideUncategorized,
    pinned,
    setPinned,
    pinnedXY,
    setPinnedXY,
    detailsPos,
    setDetailsPos,
  } = useMapState();

  // server data
  const [historyPts, setHistoryPts] = useState<Position[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [userTrips, setUserTrips] = useState<Trip[]>([]);
  const [tripStats, setTripStats] = useState<Record<string, TripStats>>({});
  const [shareLinks, setShareLinks] = useState<ShareLink[]>([]);

  // ui state
  const [tab, setTab] = useState<Tab>("map");
  const [pickPlace, setPickPlace] = useState(false);
  const [placeModal, setPlaceModal] = useState<PlaceModalState>(null);
  const [deviceModalOpen, setDeviceModalOpen] = useState(false);
  const [dateRangeModalOpen, setDateRangeModalOpen] = useState(false);
  const [colorDropdownOpen, setColorDropdownOpen] = useState(false);
  const [galleryMedia, setGalleryMedia] = useState<import("./api").MediaItem[] | null>(null);
  const [galleryIdx, setGalleryIdx] = useState<number | null>(null);
  const [tripModal, setTripModal] = useState<TripModalState>(null);
  const [tripModalOvernightSpots, setTripModalOvernightSpots] = useState<OvernightSpot[]>([]);
  const [overnightSpotModal, setOvernightSpotModal] = useState<OvernightSpotModalState>(null);
  const [detailsModal, setDetailsModal] = useState<EntityDetailsModalState>(null);
  // Selected trip drives the optional "only places linked to this trip"
  // filter on the Places panel + map.
  const [selectedTripId, setSelectedTripId] = useState<string | null>(null);
  const [expandedTripId, setExpandedTripId] = useState<string | null>(null);
  const [prefilledTripId, setPrefilledTripId] = useState<string | null>(null);
  const [prefilledShareLinkId, setPrefilledShareLinkId] = useState<string | null>(null);
  const [placesFilterByTrip, setPlacesFilterByTrip] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  // panel open/close.
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2200);
  }, []);

  const closeOverlay = useCallback(() => {
    setTab("map");
    setSidebarOpen(false);
  }, []);

  // ---- initial loads --------------------------------------------------------

  const refreshPlaces = useCallback(
    () => api.places().then(setPlaces).catch((e) => setErr(e.message)),
    [],
  );
  const refreshShareLinks = useCallback(
    () => api.shareLinks().then(setShareLinks).catch((e) => setErr(e.message)),
    [],
  );
  const refreshTrips = useCallback(async () => {
    try {
      const ts = await api.trips();
      setUserTrips(ts);
      const stats = await Promise.all(
        ts.map((t) => api.tripStats(t.id).then((s) => [t.id, s] as const).catch(() => null)),
      );
      const next: Record<string, TripStats> = {};
      for (const r of stats) if (r) next[r[0]] = r[1];
      setTripStats(next);
    } catch (e: any) {
      setErr(e.message);
    }
  }, []);

  useEffect(() => {
    void refreshPlaces();
    void refreshTrips();
    void refreshShareLinks();
  }, [
    refreshPlaces,
    refreshTrips,
    refreshShareLinks,
  ]);

  // ---- derived data ---------------------------------------------------------


  const selectedTrip = useMemo(
    () => userTrips.find((t) => t.id === selectedTripId) ?? null,
    [userTrips, selectedTripId],
  );

  const activeSegment = selectedTripId ? "trip" : mode;

  // Places shown in the side list: only the trip filter applies. Hidden tags
  // still appear so the user can un-hide them.
  const listPlaces = useMemo(() => {
    return places.filter((p) => {
      if (placesFilterByTrip && selectedTripId) {
        if (!p.trip_ids.includes(selectedTripId)) return false;
      }
      return true;
    });
  }, [places, placesFilterByTrip, selectedTripId]);

  // Places shown on the map: also filter out hidden categories / uncategorized.
  const visiblePlaces = listPlaces;

  // ---- device-scoped fetches ------------------------------------------------

  const loadHistory = useCallback(async () => {
    if (!device) return;
    setBusy(true);
    setErr(null);
    try {
      const pts = await api.history(device.id, fromIso, toIso);
      setHistoryPts(pts);
      if (mode === "history" && pts.length && map.current) {
        map.current.fitTo(pts.map((p) => [p.lon, p.lat] as [number, number]));
      }
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }, [device, fromIso, toIso, mode, map]);

  useEffect(() => {
    if (!device) return;
    setSelectedTripId(null);
    setExpandedTripId(null);
    setPlacesFilterByTrip(false);
    map.current?.setOvernightSpots([]);
    map.current?.clearHistory();
    void loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [device?.id]);

  const latest = useLivePoll({
    deviceId: device?.id ?? null,
    deviceName: device?.name ?? null,
    imei: device?.imei,
    enabled: mode === "live",
    map,
    onError: setErr,
  });

  // ---- map effects ----------------------------------------------------------

  useEffect(() => {
    map.current?.setPlaces(visiblePlaces);
  }, [visiblePlaces, map]);

  useEffect(() => {
    if (!map.current) return;
    if (mode === "history") {
      map.current.setHistory(historyPts);
      if (historyPts.length) {
        map.current.fitTo(historyPts.map((p) => [p.lon, p.lat] as [number, number]));
      }
    } else {
      map.current.clearHistory();
    }
  }, [historyPts, mode, map]);

  // Live device marker is only meaningful in live mode. Drop it when the user
  // switches to history (which includes opening a trip) so the stale "current
  // position" doesn't bleed into past-route views.
  useEffect(() => {
    if (mode !== "live") {
      map.current?.setDevice(null);
    } else {
      setSelectedTripId(null);
      setExpandedTripId(null);
      setPlacesFilterByTrip(false);
      map.current?.setOvernightSpots([]);
    }
  }, [mode, map]);

  useEffect(() => {
    map.current?.setColorMode(colorMode);
  }, [colorMode, map]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    m.onHistoryClick((pos) => {
      setPinned(pos);
      setPinnedXY(pos ? m.project(pos.lon, pos.lat) : null);
    });
    return () => map.current?.onHistoryClick(null);
  }, [map, historyPts]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    m.onPlaceAction(async (action, place) => {
      if (action === "view") {
        if (!place) {
          setDetailsModal(null);
        } else {
          setDetailsModal({ type: "place", place });
        }
      } else if (place) {
        if (action === "edit") {
          setPlaceModal({ mode: "edit", place });
        } else if (action === "delete" && confirm(t("places.confirmDelete", { name: place.name }))) {
          try {
            await api.deletePlace(place.id);
            setPlaces((cur) => cur.filter((p) => p.id !== place.id));
            showToast(t("toasts.placeDeleted", { name: place.name }));
            setDetailsModal(null);
            map.current?.setSelectedMarker(null, null);
          } catch (e: any) {
            setErr(e.message);
          }
        }
      }
    });
    return () => map.current?.onPlaceAction(null);
  }, [map, showToast, places]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    m.onOvernightAction((action, spot) => {
      if (action === "view") {
        if (!spot) {
          setDetailsModal(null);
        } else {
          setDetailsModal({ type: "overnight-spot", spot });
        }
      } else if (spot) {
        if (action === "edit") {
          setOvernightSpotModal({ spot });
        }
      }
    });
    return () => map.current?.onOvernightAction(null);
  }, [map, userTrips]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    if (!pinned) {
      m.onMapMove(null);
      return;
    }
    m.onMapMove(() => setPinnedXY(m.project(pinned.lon, pinned.lat)));
    return () => map.current?.onMapMove(null);
  }, [pinned, map]);

  useEffect(() => {
    if (mode !== "history") {
      setPinned(null);
      setPinnedXY(null);
    }
  }, [mode]);

  useEffect(() => {
    if (!map.current) return;
    if (!pickPlace) {
      map.current.onMapClick(null);
      return;
    }
    map.current.onMapClick((lon, lat) => {
      setPickPlace(false);
      setPlaceModal({ mode: "create", lon, lat });
    });
  }, [pickPlace, map]);

  // ---- handlers -------------------------------------------------------------

  const onApplyRange = async () => {
    setSelectedTripId(null);
    setExpandedTripId(null);
    setPlacesFilterByTrip(false);
    map.current?.setOvernightSpots([]);
    setMode("history");
    closeOverlay();
    setDateRangeModalOpen(false);
    await loadHistory();
  };

  const onDownloadTrip = async (trip: Trip, fmt: "gpx" | "csv") => {
    try {
      const from = new Date(trip.started_at).toISOString();
      const to = new Date(trip.ended_at ?? new Date()).toISOString();
      const blob = await api.download(trip.device_id, fmt, from, to);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${trip.name}.${fmt}`;
      // Firefox needs the element in the document tree for `click()` to
      // trigger a download (Chrome is more forgiving). Defer revoke until
      // after the click event has had a chance to start the download —
      // synchronous revoke can race and produce empty files.
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const onExportTripGpx = async (tripId: string, includeMetadata: boolean) => {
    try {
      const trip = userTrips.find((t) => t.id === tripId);
      if (!trip) return;
      const blob = await api.exportTripGpx(tripId, includeMetadata);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${trip.name}_export.gpx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch (e: any) {
      setErr(e.message);
    }
  };

  // ---- render ---------------------------------------------------------------

  return (
    <div className={`app ${tab === "map" ? "no-panel" : ""}`}>
      <Sidebar
        tab={tab}
        setTab={(t) => {
          setPickPlace(false);
          if (t === "map") {
            setTab("map");
            setSidebarOpen(false);
          } else {
            setTab(t);
            setSidebarOpen(true);
          }
        }}
        open={sidebarOpen}
        onClose={() => { setTab("map"); setSidebarOpen(false); }}
        email={me?.email}
        onLogout={logout}
        headerAction={
          tab === "trips" ? (
            <button className="primary small" onClick={() => setTripModal({ mode: "create", from: range.from, to: range.to })}>
              + {t("places.create")}
            </button>
          ) : tab === "places" ? (
            <button className="primary small" onClick={() => { setPickPlace(true); closeOverlay(); }}>
              + {t("places.add")}
            </button>
          ) : undefined
        }
      >
        {tab === "devices" && (
          <DevicesPanel
            devices={devices}
            device={device}
            onPickDevice={setDevice}
            latest={latest}
            mode={mode}
            setMode={setMode}
            range={range}
            setRange={setRange}
            busy={busy}
            onApplyRange={onApplyRange}
          />
        )}
        {tab === "places" && (
          <PlacesPanel
            places={places}
            onFly={(p) => {
              map.current?.flyTo(p.lon, p.lat, 14);
              setDetailsModal({ type: "place", place: p });
              closeOverlay();
            }}
            onEdit={(p) => setPlaceModal({ mode: "edit", place: p })}
            onDelete={async (id) => {
              await api.deletePlace(id);
              setPlaces((cur) => cur.filter((p) => p.id !== id));
            }}
          />
        )}
        {tab === "trips" && (
          <TripsPanel
            trips={userTrips}
            stats={tripStats}
            devices={devices}
            places={places}
            shareLinks={shareLinks}
            selectedTripId={expandedTripId}
            filterByTrip={placesFilterByTrip}
            onToggleFilterByTrip={() => setPlacesFilterByTrip((v) => !v)}
            onClose={() => {
              setExpandedTripId(null);
            }}
            onFlyToPlace={(p) => {
              map.current?.flyTo(p.lon, p.lat, 14);
              closeOverlay();
            }}
            onToggleExpand={(trip) => {
              setExpandedTripId((prev) => (prev === trip.id ? null : trip.id));
            }}
            onOpen={async (trip) => {
              try {
                setSelectedTripId(trip.id);
                setPlacesFilterByTrip(true);
                setMode("history");
                setRange({
                  from: toLocalInput(new Date(trip.started_at)),
                  to: toLocalInput(trip.ended_at ? new Date(trip.ended_at) : new Date()),
                });

                const detection = await api.detectTripOvernightSpots(trip.id);
                if (detection.status === "updated" && detection.created > 0) {
                  showToast(t("toasts.overnightSpotsDetected", { count: detection.created }));
                } else if (detection.status === "cooldown") {
                  showToast(t("toasts.cooldown"));
                } else if (detection.status === "race_lost") {
                  showToast(t("toasts.raceLost"));
                }

                const pts = await api.tripPositions(trip.id);
                setHistoryPts(pts);

                const spots = await api.tripOvernightSpots(trip.id);
                if (map.current) {
                  map.current.setOvernightSpots(spots);
                }

                if (pts.length && map.current) {
                  map.current.fitTo(pts.map((p) => [p.lon, p.lat] as [number, number]));
                }
                closeOverlay();
              } catch (e: any) {
                setErr(e.message);
              }
            }}
            onDelete={async (id) => {
              try {
                await api.deleteTrip(id);
                if (selectedTripId === id) {
                  setSelectedTripId(null);
                  setPlacesFilterByTrip(false);
                  setHistoryPts([]);
                  map.current?.setOvernightSpots([]);
                  map.current?.clearHistory();
                }
                if (expandedTripId === id) {
                  setExpandedTripId(null);
                }
                void refreshTrips();
              } catch (e: any) {
                setErr(e.message);
              }
            }}
            onEnd={async (tTrip) => {
              try {
                await api.endTrip(tTrip.id);
                showToast(t("toasts.tripEnded", { name: tTrip.name }));
                void refreshTrips();
                if (selectedTripId === tTrip.id && mode === "history") {
                  try {
                    setHistoryPts([]);
                    map.current?.setOvernightSpots([]);
                    const detection = await api.detectTripOvernightSpots(tTrip.id);
                    if (detection.status === "updated" && detection.created > 0) {
                      showToast(t("toasts.overnightSpotsDetected", { count: detection.created }));
                    }
                    const pts = await api.tripPositions(tTrip.id);
                    setHistoryPts(pts);
                    const spots = await api.tripOvernightSpots(tTrip.id);
                    if (map.current) {
                      map.current.setOvernightSpots(spots);
                    }
                    setRange({
                      from: toLocalInput(new Date(tTrip.started_at)),
                      to: toLocalInput(new Date()),
                    });
                  } catch (e: any) {
                    setErr(e.message);
                  }
                }
              } catch (e: any) {
                setErr(e.message);
              }
            }}
            onEdit={async (t) => {
              setTripModalOvernightSpots([]);
              setTripModal({ mode: "edit", trip: t });
              try {
                const spots = await api.tripOvernightSpots(t.id);
                setTripModalOvernightSpots(spots);
              } catch (_) {}
            }}
            onDownload={onDownloadTrip}
            onShare={(trip, shareLinkId) => {
              if (shareLinkId) {
                setPrefilledShareLinkId(shareLinkId);
              } else {
                setPrefilledTripId(trip.id);
              }
              setTab("share");
            }}
            onCopyShare={async (linkId) => {
              try {
                const rotated = await api.rotateShareLink(linkId);
                const url = `${window.location.origin}/share/${rotated.token}`;
                await navigator.clipboard.writeText(url);
                showToast(t("share.linkCopied"));
                void refreshShareLinks();
              } catch (e: any) {
                showToast(t("share.copyFailed"));
              }
            }}
          />
        )}
        {tab === "alarms" && (
          <div style={{ padding: "2rem 1.5rem", textAlign: "center", color: "var(--text-muted, #888)" }}>
            <p style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>🔔</p>
            <p style={{ fontWeight: 600, marginBottom: "0.25rem" }}>Alarms — coming soon</p>
            <p style={{ fontSize: "0.875rem" }}>
              Geofence, motion, and power alerts will appear here.
            </p>
          </div>
        )}
        {tab === "share" && (
          <SharePanel
            shareLinks={shareLinks}
            trips={userTrips}
            onRefresh={refreshShareLinks}
            onToast={showToast}
            prefilledTripId={prefilledTripId}
            onClearPrefill={() => {
              setPrefilledTripId(null);
              setPrefilledShareLinkId(null);
            }}
            prefilledShareLinkId={prefilledShareLinkId}
          />
        )}
        {tab === "export" && (
          <ExportPanel
            trips={userTrips}
            onExport={onExportTripGpx}
          />
        )}
        {tab === "settings" && (
          <SettingsPanel
            email={me?.email}
          />
        )}
        {/* Render dynamic plugin panels */}
        {pluginRegistry.getTabs().map((plugin) => (
          tab === plugin.id && <div key={plugin.id}>{plugin.panel}</div>
        ))}
      </Sidebar>

      <main className={`map-wrap ${pickPlace ? "picking" : ""}`}>
        <div className="map" ref={mapContainerRef} />

        {device && (
          <div className="map-device-control-group">
            <button
              type="button"
              className="map-device-badge"
              onClick={() => setDeviceModalOpen((prev) => !prev)}
            >
              {device.name}
              <span className="dropdown-arrow">▼</span>
            </button>
            {deviceModalOpen && (
              <>
                <div className="dropdown-backdrop" onClick={() => setDeviceModalOpen(false)} />
                <div className="map-device-dropdown">
                  <div className="map-device-dropdown-subtitle">
                    {t("devices.availableDevices")}
                  </div>
                  <div className="map-device-dropdown-list">
                    {devices.length > 0 ? (
                      devices.map((d) => (
                        <button
                          key={d.id}
                          type="button"
                          className={`map-device-dropdown-item ${device?.id === d.id ? "active" : ""}`}
                          onClick={() => {
                            setDevice(d);
                            setDeviceModalOpen(false);
                          }}
                        >
                          <span className="name">{d.name}</span>
                          <span className="imei">{d.imei}</span>
                        </button>
                      ))
                    ) : (
                      <div className="empty" style={{ textAlign: "center", padding: "12px 0", fontSize: "12px" }}>{t("devices.noDevices")}</div>
                    )}
                  </div>
                </div>
              </>
            )}
            <div className="map-mode-buttons">
              <button
                type="button"
                className={`map-mode-btn live ${activeSegment === "live" ? "active" : ""}`}
                onClick={async () => {
                  if (mode !== "live") {
                    setMode("live");
                  } else {
                    map.current?.openDevicePopup();
                  }
                  if (tab === "trips") {
                    setTab("map");
                    setSidebarOpen(false);
                  }
                }}
              >
                <span
                  className="dot"
                  style={
                    latest && (Date.now() - new Date(latest.time_id).getTime()) > 2 * 60 * 60 * 1000
                      ? { background: "var(--bad)", boxShadow: "0 0 0 0 rgba(239,68,68,0.6)", animationName: "pulse-red" }
                      : undefined
                  }
                />
                {t("devices.live")}
              </button>
              <button
                type="button"
                className={`map-mode-btn historic ${activeSegment === "history" ? "active" : ""}`}
                onClick={() => {
                  setDateRangeModalOpen(true);
                  if (tab === "trips") {
                    setTab("map");
                    setSidebarOpen(false);
                  }
                }}
              >
                {t("devices.history")}
              </button>
              <button
                type="button"
                className={`map-mode-btn historic ${activeSegment === "trip" ? "active" : ""}`}
                onClick={() => {
                  setTab("trips");
                  setSidebarOpen(true);
                }}
              >
                {t("trip.title")}
              </button>
            </div>
            {selectedTrip && (
              <div className="map-active-trip-name">
                {selectedTrip.name}
              </div>
            )}
          </div>
        )}

        {mode === "history" && historyPts.length > 0 && (
          <div className="map-settings-container">
            <button
              type="button"
              className={`map-settings-btn ${colorDropdownOpen ? "active" : ""}`}
              onClick={() => setColorDropdownOpen((prev) => !prev)}
              aria-label="Map Settings"
            >
              <MapGearIcon />
            </button>
            {colorDropdownOpen && (
              <div className="map-settings-dropdown">
                <div className="map-settings-dropdown-header">
                  {t("map.colorBy")}
                </div>
                <div className="map-settings-dropdown-list">
                  {(["none", "speed", "altitude", "weekday"] as ColorMode[]).map((id) => (
                    <button
                      key={id}
                      type="button"
                      className={`map-settings-dropdown-item ${colorMode === id ? "active" : ""}`}
                      onClick={() => {
                        setColorMode(id);
                        setColorDropdownOpen(false);
                      }}
                    >
                      {t(`map.${id}`)}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {mode === "history" && historyPts.length > 0 && colorMode === "speed" && (
          <Legend
            title={t("map.speedUnit")}
            stops={[
              ["#1e3a8a", "0"],
              ["#1d4ed8", "<30"],
              ["#0891b2", "<60"],
              ["#16a34a", "<90"],
              ["#ca8a04", "<120"],
              ["#dc2626", "120+"],
            ]}
          />
        )}
        {mode === "history" && historyPts.length > 0 && colorMode === "altitude" && (
          <Legend
            title={t("map.altitudeUnit")}
            stops={[
              ["#0284c7", "<100"],
              ["#16a34a", "<300"],
              ["#ca8a04", "<700"],
              ["#ea580c", "<1200"],
              ["#dc2626", "<1800"],
              ["#78716c", "1800+"],
            ]}
          />
        )}
        {mode === "history" && historyPts.length > 0 && colorMode === "weekday" && (
          <Legend
            title={t("map.dayOfWeek")}
            stops={[
              ["#e63946", "Mon"],
              ["#457b9d", "Tue"],
              ["#2a9d8f", "Wed"],
              ["#e9c46a", "Thu"],
              ["#9b5de5", "Fri"],
              ["#d62828", "Sat"],
              ["#1d3557", "Sun"],
            ]}
          />
        )}

        {pinned && pinnedXY && mode === "history" && (
          <PinnedTip
            position={pinned}
            xy={pinnedXY}
            onMore={() => {
              setDetailsPos(pinned);
              setPinned(null);
              setPinnedXY(null);
            }}
            onClose={() => {
              setPinned(null);
              setPinnedXY(null);
            }}
          />
        )}

        {toast && <div className="toast">{toast}</div>}
        {err && (
          <div className="toast toast-err" role="alert">
            <span>{err}</span>
            <button
              className="modal-close"
              onClick={() => setErr(null)}
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        )}
      </main>

      <EntityDetailsModal
        state={detailsModal}
        trips={userTrips}
        onClose={() => setDetailsModal(null)}
        onEdit={(entity, type) => {
          setDetailsModal(null);
          if (type === "place") {
            setPlaceModal({ mode: "edit", place: entity as Place });
          } else {
            setOvernightSpotModal({ spot: entity as OvernightSpot });
          }
        }}
        onDelete={async (id) => {
          try {
            await api.deletePlace(id);
            setPlaces((cur) => cur.filter((p) => p.id !== id));
            showToast(t("toasts.placeDeleted", { name: places.find((p) => p.id === id)?.name ?? "" }));
            setDetailsModal(null);
            map.current?.setSelectedMarker(null, null);
          } catch (e: any) {
            setErr(e.message);
          }
        }}
        onMediaClick={(media, i) => {
          setGalleryMedia(media);
          setGalleryIdx(i);
        }}
      />

      <PlaceModal
        state={placeModal}
        trips={userTrips}
        onClose={() => setPlaceModal(null)}
        onMediaClick={(media, i) => {
          setGalleryMedia(media);
          setGalleryIdx(i);
        }}
        onMediaChange={(placeId, media) => {
          setPlaces((cur) => cur.map((p) => (p.id === placeId ? { ...p, media } : p)));
        }}
        onSubmit={async (body, id) => {
          if (id == null) {
            const created = await api.createPlace(body);
            setPlaces((cur) => [created, ...cur]);
            showToast(t("toasts.placeSaved", { name: created.name }));
            setPlaceModal({ mode: "edit", place: created });
          } else {
            const updated = await api.updatePlace(id, body);
            setPlaces((cur) => cur.map((p) => (p.id === id ? updated : p)));
            showToast(t("toasts.placeUpdated", { name: updated.name }));
            setPlaceModal(null);
          }
        }}
      />

      {galleryMedia && (
        <GalleryModal
          media={galleryMedia}
          initialIdx={galleryIdx}
          onClose={() => {
            setGalleryMedia(null);
            setGalleryIdx(null);
          }}
        />
      )}

      <OvernightSpotModal
        state={overnightSpotModal}
        onClose={() => setOvernightSpotModal(null)}
        onMediaClick={(media, i) => {
          setGalleryMedia(media);
          setGalleryIdx(i);
        }}
        onMediaChange={async () => {
          if (selectedTripId && map.current) {
            const spots = await api.tripOvernightSpots(selectedTripId);
            map.current.setOvernightSpots(spots);
          }
        }}
        onSubmit={async (body, id) => {
          const updated = await api.updateOvernightSpot(id, body);
          showToast(t("toasts.overnightSpotUpdated", { name: updated.name }));
          setOvernightSpotModal(null);
          // Refresh overnight spots on map if trip is open
          if (selectedTripId && map.current) {
            const spots = await api.tripOvernightSpots(selectedTripId);
            map.current.setOvernightSpots(spots);
          }
        }}
      />

      <DetailsModal position={detailsPos} onClose={() => setDetailsPos(null)} />

      <TripModal
        state={tripModal}
        device={device}
        overnightSpots={tripModalOvernightSpots}
        onClose={() => setTripModal(null)}
        onSubmit={async (body, id) => {
          if (id == null) {
            await api.createTrip(body);
            setTripModal(null);
            setTab("trips");
            void refreshTrips();
            showToast(t("toasts.tripCreated"));
          } else {
            await api.updateTrip(id, body);
            setTripModal(null);
            void refreshTrips();
            // Refresh the map track if the edited trip is currently open;
            // its time range (and therefore its positions) may have changed.
            if (selectedTripId === id && mode === "history") {
              try {
                setHistoryPts([]);
                map.current?.setOvernightSpots([]);
                const detection = await api.detectTripOvernightSpots(id);
                if (detection.status === "updated" && detection.created > 0) {
                  showToast(t("toasts.overnightSpotsDetected", { count: detection.created }));
                } else if (detection.status === "cooldown") {
                  showToast(t("toasts.cooldown"));
                } else if (detection.status === "race_lost") {
                  showToast(t("toasts.raceLost"));
                }
                const pts = await api.tripPositions(id);
                setHistoryPts(pts);
                const spots = await api.tripOvernightSpots(id);
                if (map.current) {
                  map.current.setOvernightSpots(spots);
                }
                setRange({
                  from: toLocalInput(new Date(body.started_at)),
                  to: toLocalInput(body.ended_at ? new Date(body.ended_at) : new Date()),
                });
              } catch (e: any) {
                setErr(e.message);
              }
            }
            showToast(t("toasts.tripUpdated"));
          }
        }}
      />


      <Modal
        open={dateRangeModalOpen}
        title={t("devices.history")}
        onClose={() => setDateRangeModalOpen(false)}
        width={360}
      >
        <div className="range">
          <div className="presets" style={{ display: "flex", gap: "8px", marginBottom: "12px", flexWrap: "wrap" }}>
            {getRangePresets(t).map((preset) => (
              <button
                key={preset.label}
                type="button"
                className="chip"
                style={{ padding: "4px 10px", fontSize: "12px", borderRadius: "999px" }}
                onClick={() => setRange(preset.calc())}
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "8px", marginBottom: "16px" }}>
            <label style={{ fontWeight: 600, fontSize: "13px" }}>{t("devices.from")}</label>
            <input
              type="datetime-local"
              value={range.from}
              onChange={(e) =>
                setRange((r) => ({ ...r, from: e.target.value }))
              }
              style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid var(--line)", background: "var(--bg-1)", color: "var(--text)" }}
            />
            <label style={{ fontWeight: 600, fontSize: "13px" }}>{t("devices.to")}</label>
            <input
              type="datetime-local"
              value={range.to}
              onChange={(e) =>
                setRange((r) => ({ ...r, to: e.target.value }))
              }
              style={{ width: "100%", padding: "8px", borderRadius: "6px", border: "1px solid var(--line)", background: "var(--bg-1)", color: "var(--text)" }}
            />
          </div>
          <button
            className="primary"
            onClick={onApplyRange}
            disabled={busy}
            style={{ width: "100%", padding: "10px", borderRadius: "6px", fontWeight: 600 }}
          >
            {busy ? t("common.loading") : t("devices.apply")}
          </button>
          <p className="muted small" style={{ marginTop: "12px", fontSize: "11px", lineHeight: "1.4" }}>
            Analytics + exports cap at {MAX_ANALYTICS_POINTS.toLocaleString()} positions per request.
            Pick a smaller window if you hit the limit.
          </p>
        </div>
      </Modal>
    </div>
  );
}

function Legend({
  title,
  stops,
}: {
  title: string;
  stops: [string, string][];
}) {
  return (
    <div className="legend">
      <span className="legend-title">{title}</span>
      {stops.map(([color, label]) => (
        <div key={label} className="legend-row">
          <i style={{ background: color }} />
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}
