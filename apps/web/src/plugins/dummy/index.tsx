import { useEffect, useState } from "react";
import { pluginRegistry } from "../registry";

// Icon for the Dummy Plugin (rendered as SVG)
function DummyIcon() {
  return (
    <svg
      width={20}
      height={20}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4" />
      <path d="M12 8h.01" />
    </svg>
  );
}

// Panel Body for the Dummy Plugin
function DummyPanel() {
  const [msg, setMsg] = useState<string>("Loading from backend...");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetch("/api/plugins/dummy", { credentials: "include" })
      .then((r) => {
        if (!r.ok) {
          throw new Error(`HTTP error ${r.status}`);
        }
        return r.json();
      })
      .then((data) => {
        if (active) {
          setMsg(data.message || JSON.stringify(data));
        }
      })
      .catch((err) => {
        if (active) {
          setError(err.message || String(err));
        }
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <div style={{ padding: "1.5rem" }}>
      <div
        style={{
          background: "rgba(96,165,250,0.1)",
          border: "1px solid var(--accent, #3b82f6)",
          borderRadius: "8px",
          padding: "1rem",
          marginBottom: "1rem",
        }}
      >
        <p style={{ fontWeight: 600, fontSize: "1.1rem", marginBottom: "0.25rem" }}>
          🔌 Lightweight Plugin
        </p>
        <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
          This tab was registered dynamically by the frontend feature registry!
        </p>
      </div>

      {error ? (
        <div style={{ color: "var(--bad, #ef4444)", fontSize: "0.875rem" }}>
          <strong>Error loading from backend:</strong>
          <p>{error}</p>
        </div>
      ) : (
        <div>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "0.5rem" }}>
            Response from backend plugin:
          </p>
          <pre
            style={{
              background: "var(--bg-2, #273848)",
              color: "var(--text)",
              padding: "0.75rem",
              borderRadius: "4px",
              fontFamily: "monospace",
              fontSize: "0.875rem",
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {msg}
          </pre>
        </div>
      )}
    </div>
  );
}

// Auto-register this plugin when imported
export function initDummyPlugin() {
  pluginRegistry.registerTab({
    id: "dummy",
    label: "Dummy Plugin",
    icon: <DummyIcon />,
    panel: <DummyPanel />,
  });
}
