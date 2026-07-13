import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Place } from "../api";
import { EditDeleteActions } from "../components/RowActions";
import { PlaceTypeIcon } from "../components/PlaceTypeIcon";

type Props = {
  places: Place[];
  onFly: (p: Place) => void;
  onEdit: (p: Place) => void;
  onDelete: (id: string) => void;
};

const CATEGORY_ORDER = ["POI", "Drinking Water", "Camping", "Parking"];

export function PlacesPanel({ places, onFly, onEdit, onDelete }: Props) {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const groupedPlaces = useMemo(() => {
    const groups: Record<string, Place[]> = {};
    places.forEach((p) => {
      const cat = p.place_category || "POI";
      if (!groups[cat]) {
        groups[cat] = [];
      }
      groups[cat].push(p);
    });
    return groups;
  }, [places]);

  const categoriesToRender = useMemo(() => {
    const existingCats = Object.keys(groupedPlaces);
    return [...existingCats].sort((a, b) => {
      const idxA = CATEGORY_ORDER.indexOf(a);
      const idxB = CATEGORY_ORDER.indexOf(b);
      if (idxA !== -1 && idxB !== -1) return idxA - idxB;
      if (idxA !== -1) return -1;
      if (idxB !== -1) return 1;
      return a.localeCompare(b);
    });
  }, [groupedPlaces]);

  const toggleCategory = (cat: string) => {
    setCollapsed((prev) => ({
      ...prev,
      [cat]: !prev[cat],
    }));
  };

  if (places.length === 0) {
    return <div className="empty">{t("places.noPlacesAdd")}</div>;
  }

  return (
    <div className="places-panel">
      {categoriesToRender.map((cat) => {
        const catPlaces = groupedPlaces[cat] || [];
        if (catPlaces.length === 0) return null;
        const isCollapsed = !!collapsed[cat];

        return (
          <div key={cat} className="category-group">
            <button
              type="button"
              className="category-header-btn"
              onClick={() => toggleCategory(cat)}
            >
              <div
                className="row gap small"
                style={{ alignItems: "center", width: "100%" }}
              >
                <span
                  className={`chevron ${isCollapsed ? "collapsed" : ""}`}
                  aria-hidden="true"
                >
                  ▸
                </span>
                <PlaceTypeIcon type={cat} size={14} className="muted" />
                <span className="category-title">
                  {t(`places.categories.${cat}`, { defaultValue: cat })}
                </span>
                <span className="muted count">({catPlaces.length})</span>
              </div>
            </button>
            {!isCollapsed && (
              <ul className="list">
                {catPlaces.map((p) => (
                  <PlaceItem
                    key={p.id}
                    p={p}
                    onFly={onFly}
                    onEdit={onEdit}
                    onDelete={onDelete}
                  />
                ))}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}

function PlaceItem({
  p,
  onFly,
  onEdit,
  onDelete,
}: {
  p: Place;
  onFly: (p: Place) => void;
  onEdit: (p: Place) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <li className="list-item">
      <div className="list-main" onClick={() => onFly(p)}>
        <div className="row gap small" style={{ alignItems: "center" }}>
          <PlaceTypeIcon type={p.place_category} size={14} className="muted" />
          <div className="list-title">{p.name}</div>
        </div>
        {p.notes && <div className="muted small">{p.notes}</div>}
      </div>
      <EditDeleteActions
        onEdit={() => onEdit(p)}
        onDelete={() => onDelete(p.id)}
        confirmDelete={`Delete "${p.name}"?`}
      />
    </li>
  );
}
