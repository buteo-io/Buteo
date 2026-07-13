import React, { createContext, useContext, useState, useRef } from "react";
import { Position } from "../api";
import { ColorMode, useTrackMap, MapHandle } from "../components/Map";

type MapStateContextType = {
  mapContainerRef: React.RefObject<HTMLDivElement>;
  map: React.MutableRefObject<MapHandle | null>;
  mode: "live" | "history";
  setMode: React.Dispatch<React.SetStateAction<"live" | "history">>;
  colorMode: ColorMode;
  setColorMode: React.Dispatch<React.SetStateAction<ColorMode>>;
  hiddenCategories: Set<string>;
  setHiddenCategories: React.Dispatch<React.SetStateAction<Set<string>>>;
  hideUncategorized: boolean;
  setHideUncategorized: React.Dispatch<React.SetStateAction<boolean>>;
  pinned: Position | null;
  setPinned: React.Dispatch<React.SetStateAction<Position | null>>;
  pinnedXY: { x: number; y: number } | null;
  setPinnedXY: React.Dispatch<
    React.SetStateAction<{ x: number; y: number } | null>
  >;
  detailsPos: Position | null;
  setDetailsPos: React.Dispatch<React.SetStateAction<Position | null>>;
};

const MapStateContext = createContext<MapStateContextType | null>(null);

export function MapStateProvider({ children }: { children: React.ReactNode }) {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const map = useTrackMap(mapContainerRef);

  const [mode, setMode] = useState<"live" | "history">("live");
  const [colorMode, setColorMode] = useState<ColorMode>("none");
  const [hiddenCategories, setHiddenCategories] = useState<Set<string>>(
    new Set(),
  );
  const [hideUncategorized, setHideUncategorized] = useState(false);
  const [pinned, setPinned] = useState<Position | null>(null);
  const [pinnedXY, setPinnedXY] = useState<{ x: number; y: number } | null>(
    null,
  );
  const [detailsPos, setDetailsPos] = useState<Position | null>(null);

  return (
    <MapStateContext.Provider
      value={{
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
      }}
    >
      {children}
    </MapStateContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useMapState() {
  const context = useContext(MapStateContext);
  if (!context) {
    throw new Error("useMapState must be used within a MapStateProvider");
  }
  return context;
}
