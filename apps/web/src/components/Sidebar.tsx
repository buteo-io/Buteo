// Bottom navigation bar + slide-up panel.
//
// Layout (all screen sizes):
//   - Bottom bar: horizontally scrollable tab strip (map | devices | trips | …)
//   - "map" pseudo-tab: closes the panel so the map fills the screen
//   - Other tabs: open a slide-up panel above the bar
//   - Desktop (>=1024px): panel is pinned as a left column instead of a sheet

import { ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";
import { pluginRegistry } from "../plugins/registry";
import { Modal } from "./Modal";

export type Tab =
  | "map"
  | "devices"
  | "trips"
  | "places"
  | "alarms"
  | "share"
  | "export"
  | "settings"
  | string;

// eslint-disable-next-line react-refresh/only-export-components
export const TAB_ORDER: Tab[] = ["map", "trips", "places"];

type Props = {
  tab: Tab;
  setTab: (t: Tab) => void;
  open: boolean;
  onClose: () => void;
  email?: string | null;
  onLogout: () => void;
  headerAction?: ReactNode;
  children: ReactNode;
};

export function Sidebar({
  tab,
  setTab,
  open,
  onClose,
  email: _email,
  onLogout,
  headerAction,
  children,
}: Props) {
  const { t } = useTranslation();
  const [moreModalOpen, setMoreModalOpen] = useState(false);
  const registeredTabs = pluginRegistry.getTabs();
  const registeredTab = registeredTabs.find((t) => t.id === tab);
  const getTabLabel = (id: string) => {
    const labels: Record<string, string> = {
      map: t("nav.map"),
      devices: t("devices.title"),
      trips: t("trips.title"),
      places: t("places.title"),
      alarms: t("alarms.title"),
      share: t("share.title"),
      export: t("export.title"),
      settings: t("settings.title"),
    };
    return labels[id] || id;
  };
  const panelLabel =
    tab !== "map"
      ? registeredTab
        ? registeredTab.label
        : getTabLabel(tab)
      : "";

  const isMoreTab = [
    "alarms",
    "share",
    "export",
    "settings",
    ...registeredTabs.map((t) => t.id),
  ].includes(tab);

  const panelElement = (
    <section
      className={`panel ${isMoreTab ? "panel-modal" : ""} ${open ? "is-open" : ""}`}
      aria-label={panelLabel}
      onClick={isMoreTab ? (e) => e.stopPropagation() : undefined}
    >
      <header className="panel-head">
        <h2>{panelLabel}</h2>
        {headerAction && (
          <div className="panel-head-action">{headerAction}</div>
        )}
        {isMoreTab ? (
          <button
            type="button"
            className="panel-back-btn"
            onClick={() => {
              setTab("map");
              setTimeout(() => setMoreModalOpen(true), 0);
            }}
            aria-label="Go back"
          >
            <ArrowLeftIcon />
          </button>
        ) : (
          <button
            type="button"
            className="panel-close"
            onClick={onClose}
            aria-label="Close panel"
          >
            <CloseIcon />
          </button>
        )}
      </header>
      <div className="panel-body">{children}</div>
    </section>
  );

  return (
    <>
      {/* slide-up / pinned panel / centered modal */}
      {tab !== "map" &&
        (isMoreTab ? (
          <div
            className={`panel-backdrop ${open ? "is-open" : ""}`}
            onClick={onClose}
          >
            {panelElement}
          </div>
        ) : (
          panelElement
        ))}

      {/* bottom navigation bar */}
      <nav className="bottom-nav" aria-label="Primary">
        <div className="bottom-nav-inner">
          {TAB_ORDER.map((id) => {
            const label = getTabLabel(id);
            return (
              <button
                key={id}
                type="button"
                className={`bnav-btn ${tab === id ? "active" : ""}`}
                onClick={() => setTab(id)}
                aria-label={label}
              >
                <span className="bnav-icon">
                  <TabIcon id={id} />
                </span>
                <span className="bnav-label">{label}</span>
              </button>
            );
          })}

          {/* More (burger) button */}
          <button
            type="button"
            className={`bnav-btn ${["alarms", "share", "export", "settings", ...registeredTabs.map((t) => t.id)].includes(tab) ? "active" : ""}`}
            onClick={() => setMoreModalOpen(true)}
            aria-label={t("nav.more")}
          >
            <span className="bnav-icon">
              <BurgerIcon />
            </span>
            <span className="bnav-label">{t("nav.more")}</span>
          </button>
        </div>
      </nav>

      {/* More Options Modal */}
      <Modal
        open={moreModalOpen}
        title={t("nav.more")}
        onClose={() => setMoreModalOpen(false)}
        width={360}
      >
        <div className="burger-options-list">
          <button
            type="button"
            className={`burger-option-btn ${tab === "alarms" ? "active" : ""}`}
            onClick={() => {
              setTab("alarms");
              setMoreModalOpen(false);
            }}
          >
            <span className="burger-option-icon">
              <TabIcon id="alarms" />
            </span>
            <span>{getTabLabel("alarms")}</span>
          </button>

          <button
            type="button"
            className={`burger-option-btn ${tab === "share" ? "active" : ""}`}
            onClick={() => {
              setTab("share");
              setMoreModalOpen(false);
            }}
          >
            <span className="burger-option-icon">
              <TabIcon id="share" />
            </span>
            <span>{getTabLabel("share")}</span>
          </button>

          <button
            type="button"
            className={`burger-option-btn ${tab === "export" ? "active" : ""}`}
            onClick={() => {
              setTab("export");
              setMoreModalOpen(false);
            }}
          >
            <span className="burger-option-icon">
              <TabIcon id="export" />
            </span>
            <span>{getTabLabel("export")}</span>
          </button>

          <button
            type="button"
            className={`burger-option-btn ${tab === "settings" ? "active" : ""}`}
            onClick={() => {
              setTab("settings");
              setMoreModalOpen(false);
            }}
          >
            <span className="burger-option-icon">
              <TabIcon id="settings" />
            </span>
            <span>{getTabLabel("settings")}</span>
          </button>

          {registeredTabs.map((plugin) => (
            <button
              key={plugin.id}
              type="button"
              className={`burger-option-btn ${tab === plugin.id ? "active" : ""}`}
              onClick={() => {
                setTab(plugin.id);
                setMoreModalOpen(false);
              }}
            >
              <span className="burger-option-icon">{plugin.icon}</span>
              <span>{plugin.label}</span>
            </button>
          ))}

          <button
            type="button"
            className="burger-option-btn signout"
            onClick={() => {
              setMoreModalOpen(false);
              onLogout();
            }}
          >
            <span className="burger-option-icon">
              <SignOutIcon />
            </span>
            <span>{t("auth.logout")}</span>
          </button>
        </div>
      </Modal>
    </>
  );
}

/* ---- icons -------------------------------------------------------------- */

function TabIcon({ id }: { id: Tab }) {
  switch (id) {
    case "map":
      return <MapIcon />;
    case "trips":
      return <RouteIcon />;
    case "places":
      return <PinIcon />;
    case "alarms":
      return <BellIcon />;
    case "share":
      return <ShareIcon />;
    case "export":
      return <DownloadIcon />;
    case "settings":
      return <GearIcon />;
  }
}

function DownloadIcon() {
  return (
    <svg {...svgProps}>
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

const svgProps = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

function BurgerIcon() {
  return (
    <svg {...svgProps}>
      <line x1="4" y1="12" x2="20" y2="12" />
      <line x1="4" y1="6" x2="20" y2="6" />
      <line x1="4" y1="18" x2="20" y2="18" />
    </svg>
  );
}

function MapIcon() {
  return (
    <svg {...svgProps}>
      <path d="M9 4L3 7v13l6-3 6 3 6-3V4l-6 3-6-3z" />
      <path d="M9 4v13" />
      <path d="M15 7v13" />
    </svg>
  );
}
function RouteIcon() {
  return (
    <svg {...svgProps}>
      <circle cx="6" cy="5" r="2.2" />
      <circle cx="18" cy="19" r="2.2" />
      <path d="M8 5h6a4 4 0 0 1 0 8h-4a4 4 0 0 0 0 8h6" />
    </svg>
  );
}
function PinIcon() {
  return (
    <svg {...svgProps}>
      <path d="M12 22s7-7.2 7-12a7 7 0 0 0-14 0c0 4.8 7 12 7 12z" />
      <circle cx="12" cy="10" r="2.5" />
    </svg>
  );
}
function BellIcon() {
  return (
    <svg {...svgProps}>
      <path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2.5h-15z" />
      <path d="M10 20a2 2 0 0 0 4 0" />
    </svg>
  );
}
function ShareIcon() {
  return (
    <svg {...svgProps}>
      <circle cx="6" cy="12" r="2.4" />
      <circle cx="18" cy="6" r="2.4" />
      <circle cx="18" cy="18" r="2.4" />
      <path d="M8 11l8-4" />
      <path d="M8 13l8 4" />
    </svg>
  );
}
function GearIcon() {
  return (
    <svg {...svgProps}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </svg>
  );
}
function SignOutIcon() {
  return (
    <svg {...svgProps}>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
      <path d="M10 17l-5-5 5-5" />
      <path d="M15 12H5" />
    </svg>
  );
}
function CloseIcon() {
  return (
    <svg {...svgProps}>
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </svg>
  );
}
function ArrowLeftIcon() {
  return (
    <svg {...svgProps}>
      <path d="M15 18l-6-6 6-6" />
    </svg>
  );
}
