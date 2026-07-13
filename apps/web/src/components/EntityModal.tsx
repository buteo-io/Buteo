import { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { api, Place, OvernightSpot, MediaItem } from "../api";
import { Field, Modal } from "./Modal";
import { useEntityForm } from "../hooks/useEntityForm";

type Props<T extends Place | OvernightSpot, M extends MediaItem> = {
  mode: "create" | "edit";
  entityType: "place" | "overnight-spot";
  entity?: T;
  lat: number;
  lon: number;
  onClose: () => void;
  onSubmit: (data: { name: string; notes: string }) => Promise<void>;
  fetchMedia?: (id: string) => Promise<M[]>;
  uploadMedia?: (id: string, file: File) => Promise<M>;
  deleteMedia?: (id: string, mediaId: string) => Promise<void>;
  onMediaClick?: (media: M[], initialIdx: number) => void;
  onMediaChange?: (media: M[]) => void;
  extraFields?: ReactNode;
  submitButtonText?: string;
  savingButtonText?: string;
};

export function EntityModal<
  T extends Place | OvernightSpot,
  M extends MediaItem,
>({
  mode,
  entityType,
  entity,
  lat: _lat,
  lon: _lon,
  onClose,
  onSubmit,
  fetchMedia,
  uploadMedia,
  deleteMedia,
  onMediaClick,
  onMediaChange,
  extraFields,
  submitButtonText,
  savingButtonText,
}: Props<T, M>) {
  const { t } = useTranslation();
  const {
    name,
    setName,
    notes,
    setNotes,
    media,
    saving,
    uploading,
    error,
    fileInputRef,
    handleSubmit,
    handleUpload,
    handleDeleteMedia,
  } = useEntityForm<M>({
    initialName: entity?.name ?? "",
    initialNotes: entity?.notes ?? "",
    entityId: entity?.id,
    fetchMedia,
    uploadMedia,
    deleteMedia,
    onSubmit,
    onMediaChange,
  });

  const title = t(
    `entityModal.title${mode === "create" ? "New" : "Edit"}_${entityType}`,
  );
  const defaultSubmitText =
    mode === "create" ? t("places.create") : t("common.saveChanges");
  const activeSavingButtonText = savingButtonText || t("common.saving");

  return (
    <Modal
      open
      onClose={onClose}
      title={title}
      error={error}
      footer={
        <>
          <button className="ghost" onClick={onClose}>
            {t("common.cancel")}
          </button>
          <button
            className="primary"
            onClick={handleSubmit}
            disabled={saving || uploading || !name.trim()}
          >
            {saving
              ? activeSavingButtonText
              : uploading
                ? t("common.uploading")
                : submitButtonText || defaultSubmitText}
          </button>
        </>
      }
    >
      <Field label={t("share.name")}>
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t(`entityModal.placeholderName_${entityType}`)}
        />
      </Field>

      {extraFields}

      <Field label={t("entityModal.comments")}>
        <textarea
          rows={3}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={t("entityModal.commentsPlaceholder")}
        />
      </Field>

      {mode === "edit" && (
        <Field label={t("entityModal.media")}>
          <div className="media-grid">
            {media.map((m, i) => (
              <div
                key={m.id}
                className="media-item"
                style={{ cursor: onMediaClick ? "pointer" : "default" }}
                onClick={() => onMediaClick?.(media, i)}
              >
                {m.media_type === "image" ? (
                  <img src={api.serveMedia(m.id)} alt={m.filename_original} />
                ) : (
                  <video src={api.serveMedia(m.id)} />
                )}
                <button
                  type="button"
                  className="media-delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteMedia(m.id);
                  }}
                  title={t("common.delete")}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          <div
            className="file-upload"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              marginTop: "8px",
            }}
          >
            <button
              type="button"
              className="ghost small"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {t("entityModal.chooseFile")}
            </button>
            <span className="muted small">
              {uploading
                ? t("common.uploading")
                : t("entityModal.noFileChosen")}
            </span>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,video/*"
            onChange={handleUpload}
            disabled={uploading}
            style={{ display: "none" }}
          />
        </Field>
      )}
    </Modal>
  );
}
