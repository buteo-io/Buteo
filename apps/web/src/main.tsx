import React from "react";
import ReactDOM from "react-dom/client";
import { AuthProvider, useAuth } from "./auth";
import Login from "./pages/Login";
import App from "./App";
import PublicShare from "./pages/PublicShare";
import { DateRangeProvider } from "./contexts/DateRangeContext";
import { EntityProvider } from "./contexts/EntityContext";
import { MapStateProvider } from "./contexts/MapStateContext";
import { initDummyPlugin } from "./plugins/dummy";
import "./i18n";
import "./styles.css";

// Initialize plugins
initDummyPlugin();

function AuthenticatedRoot() {
  const { me, loading } = useAuth();
  if (loading) return <div style={{ padding: 24 }}>...</div>;
  return me ? (
    <DateRangeProvider>
      <EntityProvider>
        <MapStateProvider>
          <App />
        </MapStateProvider>
      </EntityProvider>
    </DateRangeProvider>
  ) : (
    <Login />
  );
}

function Root() {
  const path = window.location.pathname;
  const shareMatch = path.match(/^\/share\/([^/]+)$/);
  
  if (shareMatch) {
    const token = shareMatch[1];
    return <PublicShare token={token} />;
  }
  
  return (
    <AuthProvider>
      <AuthenticatedRoot />
    </AuthProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>,
);

// Register the PWA service worker in production builds. In dev, unregister any
// stale worker so HMR isn't intercepted.
if ("serviceWorker" in navigator) {
  if (import.meta.env.PROD) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
    });
  } else {
    navigator.serviceWorker
      .getRegistrations()
      .then((rs) => rs.forEach((r) => r.unregister()))
      .catch(() => undefined);
  }
}
