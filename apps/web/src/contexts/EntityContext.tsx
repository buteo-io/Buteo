import React, { createContext, useContext, useState, useEffect, useMemo, useCallback } from "react";
import { api, Entity, Device } from "../api";

type EntityContextType = {
  entities: Entity[];
  devices: Device[];
  device: Device | null;
  activeEntity: Entity | null;
  loading: boolean;
  error: string | null;
  setDevice: (device: Device | null) => void;
  setActiveEntity: (entity: Entity | null) => void;
  refreshEntities: () => Promise<void>;
};

const EntityContext = createContext<EntityContextType | null>(null);

export function EntityProvider({ children }: { children: React.ReactNode }) {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [device, setDevice] = useState<Device | null>(null);
  const [activeEntity, setActiveEntity] = useState<Entity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const devices = useMemo(() => {
    return entities.flatMap((ent) => ent.devices);
  }, [entities]);

  const refreshEntities = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.entities();
      setEntities(data);
      if (data.length > 0) {
        // If there is no active entity selected yet, set to the first one
        if (!activeEntity) {
          setActiveEntity(data[0]);
          if (data[0].devices.length > 0 && !device) {
            setDevice(data[0].devices[0]);
          }
        } else {
          // Sync existing activeEntity and device in case names/fields updated
          const updatedEntity = data.find((e) => e.id === activeEntity.id);
          if (updatedEntity) {
            setActiveEntity(updatedEntity);
            if (device) {
              const updatedDevice = updatedEntity.devices.find((d) => d.id === device.id) || 
                                    devices.find((d) => d.id === device.id);
              if (updatedDevice) setDevice(updatedDevice);
            }
          }
        }
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [activeEntity, device, devices]);

  useEffect(() => {
    void refreshEntities();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSetDevice = useCallback((dev: Device | null) => {
    setDevice(dev);
    if (dev) {
      // Find parent entity and update activeEntity
      const parent = entities.find((ent) => ent.devices.some((d) => d.id === dev.id));
      if (parent) {
        setActiveEntity(parent);
      }
    }
  }, [entities]);

  const handleSetActiveEntity = useCallback((ent: Entity | null) => {
    setActiveEntity(ent);
    if (ent && ent.devices.length > 0) {
      // Select first device of the entity
      setDevice(ent.devices[0]);
    } else {
      setDevice(null);
    }
  }, []);

  return (
    <EntityContext.Provider
      value={{
        entities,
        devices,
        device,
        activeEntity,
        loading,
        error,
        setDevice: handleSetDevice,
        setActiveEntity: handleSetActiveEntity,
        refreshEntities,
      }}
    >
      {children}
    </EntityContext.Provider>
  );
}

export function useEntity() {
  const context = useContext(EntityContext);
  if (!context) {
    throw new Error("useEntity must be used within an EntityProvider");
  }
  return context;
}
