import { ReactNode } from "react";
import type { Map as MLMap } from "maplibre-gl";

export interface RegisteredTab {
  id: string;
  label: string;
  icon: ReactNode;
  panel: ReactNode;
}

export type MapLoadCallback = (map: MLMap) => void;

class FeatureRegistry {
  private tabs: RegisteredTab[] = [];
  private mapCallbacks: MapLoadCallback[] = [];

  /**
   * Register a custom sidebar tab/panel.
   */
  registerTab(tab: RegisteredTab): void {
    if (this.tabs.some((t) => t.id === tab.id)) {
      console.warn(
        `Plugin registry: Tab with ID "${tab.id}" is already registered.`,
      );
      return;
    }
    this.tabs.push(tab);
    console.log(`Plugin registry: Registered tab "${tab.label}" (${tab.id})`);
  }

  /**
   * Register a callback to run when the map is instantiated.
   */
  registerMapLoad(callback: MapLoadCallback): void {
    this.mapCallbacks.push(callback);
  }

  /**
   * Get all registered sidebar tabs.
   */
  getTabs(): RegisteredTab[] {
    return this.tabs;
  }

  /**
   * Trigger all registered map load callbacks with the given map handle.
   */
  triggerMapLoad(mapInstance: MLMap): void {
    this.mapCallbacks.forEach((cb) => {
      try {
        cb(mapInstance);
      } catch (err) {
        console.error("Plugin registry: Map load callback failed", err);
      }
    });
  }
}

export const pluginRegistry = new FeatureRegistry();
