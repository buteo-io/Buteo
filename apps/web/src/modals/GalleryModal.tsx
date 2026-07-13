import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, MediaItem } from "../api";

type Props = {
  media: MediaItem[];
  initialIdx?: number | null;
  getMediaUrl?: (id: string) => string;
  onClose: () => void;
};

export function GalleryModal({
  media,
  initialIdx = null,
  getMediaUrl = (id) => api.serveMedia(id),
  onClose,
}: Props) {
  const { t } = useTranslation();
  const [idx, setIdx] = useState<number | null>(initialIdx);

  const prev = () =>
    setIdx((i) => (i !== null && i > 0 ? i - 1 : media.length - 1));
  const next = () =>
    setIdx((i) => (i !== null && i < media.length - 1 ? i + 1 : 0));

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (idx !== null) {
        if (e.key === "ArrowLeft") prev();
        else if (e.key === "ArrowRight") next();
        else if (e.key === "Escape") setIdx(null);
      } else {
        if (e.key === "Escape") onClose();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [media.length, onClose, idx]); // eslint-disable-line react-hooks/exhaustive-deps

  if (media.length === 0) return null;

  if (idx === null) {
    return (
      <div className="gallery-overlay" onClick={onClose}>
        <div className="gallery-grid-wrap" onClick={(e) => e.stopPropagation()}>
          <div className="gallery-grid-header">
            <span>{t("entityModal.media")}</span>
            <button className="gallery-close-inline" onClick={onClose}>
              ×
            </button>
          </div>
          <div className="gallery-grid">
            {media.map((m, i) => (
              <div
                key={m.id}
                className="gallery-grid-item"
                onClick={() => setIdx(i)}
              >
                {m.media_type === "image" ? (
                  <img src={getMediaUrl(m.id)} alt={m.filename_original} />
                ) : m.media_type === "video" ? (
                  <div className="gallery-grid-video-preview">
                    <video src={getMediaUrl(m.id)} />
                    <div className="play-icon">▶</div>
                  </div>
                ) : (
                  <div className="gallery-grid-audio-preview">🎵</div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const curr = media[idx];
  const isVideo = curr.media_type === "video";

  return (
    <div className="gallery-overlay" onClick={() => setIdx(null)}>
      <button
        className="gallery-close"
        onClick={() => setIdx(null)}
        aria-label={t("gallery.backToGrid")}
      >
        ×
      </button>
      <div className="gallery-content" onClick={(e) => e.stopPropagation()}>
        {isVideo ? (
          <video src={getMediaUrl(curr.id)} controls autoPlay />
        ) : (
          <img src={getMediaUrl(curr.id)} alt={curr.filename_original} />
        )}
        <div className="gallery-info">
          <div className="gallery-filename">
            {curr.filename_original ||
              (curr as { entityName?: string }).entityName}
          </div>
          {media.length > 1 && (
            <div className="gallery-counter">
              {idx + 1} / {media.length}
            </div>
          )}
        </div>
        {media.length > 1 && (
          <>
            <button
              className="gallery-nav gallery-prev"
              onClick={(e) => {
                e.stopPropagation();
                prev();
              }}
              aria-label={t("gallery.prev")}
            >
              ‹
            </button>
            <button
              className="gallery-nav gallery-next"
              onClick={(e) => {
                e.stopPropagation();
                next();
              }}
              aria-label={t("gallery.next")}
            >
              ›
            </button>
          </>
        )}
      </div>
    </div>
  );
}
