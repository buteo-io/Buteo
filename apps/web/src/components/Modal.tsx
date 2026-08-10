import { ReactNode, useEffect, useRef } from "react";

type Props = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
  // Inline error banner shown above the body. Lets a modal surface a failed
  // submission (e.g. 409 from the server) without losing form state.
  error?: string | null;
};

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  width = 640,
  error,
}: Props) {
  // Track where the pointer went down so the backdrop only closes on a click
  // that genuinely started on the backdrop itself. On mobile, opening the
  // keyboard (e.g. via an autofocused input) resizes the viewport and the
  // fixed-position modal repositions, which can dispatch a synthesized "ghost"
  // click on the backdrop at the original tap coordinates. Ghost clicks carry
  // no preceding pointerdown on the backdrop, so this guard drops them while
  // still allowing real outside clicks (and ignoring drag-from-inside).
  const downOnBackdrop = useRef(false);

  useEffect(() => {
    if (!open) return;
    downOnBackdrop.current = false;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="modal-backdrop"
      onPointerDown={(e) => {
        downOnBackdrop.current = e.target === e.currentTarget;
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && downOnBackdrop.current) {
          downOnBackdrop.current = false;
          onClose();
        }
      }}
    >
      <div
        className="modal"
        style={{ width }}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <header className="modal-header">
          <h3>{title}</h3>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>
        <div className="modal-body">
          {error && (
            <div className="err small" role="alert">
              {error}
            </div>
          )}
          {children}
        </div>
        {footer && <footer className="modal-footer">{footer}</footer>}
      </div>
    </div>
  );
}

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <div className="field">
      <span className="field-label">{label}</span>
      {hint && <span className="field-hint">{hint}</span>}
      {children}
    </div>
  );
}
